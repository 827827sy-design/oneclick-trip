package com.oneclicktrip.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.oneclicktrip.client.FastApiAgentClient;
import com.oneclicktrip.dto.AiChatRequest;
import com.oneclicktrip.dto.AiChatResponse;
import com.oneclicktrip.dto.AiResumeRequest;
import com.oneclicktrip.entity.AiCallLog;
import com.oneclicktrip.entity.AiConversation;
import com.oneclicktrip.mapper.AiCallLogMapper;
import org.springframework.stereotype.Service;
import org.springframework.security.access.AccessDeniedException;

import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

@Service
public class AiAssistantService {
    private final FastApiAgentClient agentClient;
    private final AiCallLogMapper aiCallLogMapper;
    private final AiConversationService conversationService;
    private final AgentRunLogService agentRunLogService;
    private final ObjectMapper objectMapper;
    private final ConcurrentMap<String, AsyncCallContext> pendingRuns = new ConcurrentHashMap<>();

    public AiAssistantService(
            FastApiAgentClient agentClient,
            AiCallLogMapper aiCallLogMapper,
            AiConversationService conversationService,
            AgentRunLogService agentRunLogService,
            ObjectMapper objectMapper
    ) {
        this.agentClient = agentClient;
        this.aiCallLogMapper = aiCallLogMapper;
        this.conversationService = conversationService;
        this.agentRunLogService = agentRunLogService;
        this.objectMapper = objectMapper;
    }

    public JsonNode startChat(AiChatRequest request, Long authenticatedUserId) {
        Long userId = requireAuthenticatedUser(authenticatedUserId);
        String conversationId = hasText(request.conversationId())
                ? request.conversationId()
                : UUID.randomUUID().toString();
        AiConversation conversation = conversationService.findOrCreate(userId, conversationId, request.message());
        conversationService.recordUserMessage(conversation, request.message());
        try {
            JsonNode accepted = agentClient.startRun(
                    conversationId,
                    agentUserId(userId),
                    request.message()
            );
            String runId = accepted.path("run_id").asText();
            if (runId.isBlank()) {
                throw new IllegalStateException("FastAPI 未返回 run_id");
            }
            pendingRuns.put(
                    runId,
                    new AsyncCallContext(userId, conversationId, request.message(), conversation)
            );
            return accepted;
        } catch (RuntimeException ex) {
            saveLog(userId, request.message(), ex.getMessage(), "FAILED");
            if (conversation != null) {
                conversationService.recordFailure(conversation, ex.getMessage());
            }
            throw ex;
        }
    }

    public JsonNode job(String runId, Long authenticatedUserId) {
        Long requestingUserId = requireAuthenticatedUser(authenticatedUserId);
        AsyncCallContext context = pendingRuns.get(runId);
        if (context != null && !requestingUserId.equals(context.userId())) {
            throw new AccessDeniedException("无权查看该 Agent 任务");
        }
        Long userId = context == null ? requestingUserId : context.userId();
        JsonNode job = agentClient.runJob(runId, agentUserId(userId));
        String status = job.path("status").asText();
        ObjectNode response = job.deepCopy();
        if ("COMPLETED".equals(status) && job.path("result").isObject()) {
            AiChatResponse chatResponse = toResponse(job.path("result"));
            response.set("response", objectMapper.valueToTree(chatResponse));
            AsyncCallContext completed = pendingRuns.remove(runId);
            if (completed != null) {
                agentRunLogService.record(
                        runId,
                        completed.userId(),
                        completed.conversationId(),
                        job
                );
                saveLog(completed.userId(), completed.requestText(), chatResponse.message(), chatResponse.status());
                if (completed.conversation() != null) {
                    conversationService.recordAssistantMessage(completed.conversation(), chatResponse);
                }
            }
        } else if ("FAILED".equals(status)) {
            AsyncCallContext failed = pendingRuns.remove(runId);
            if (failed != null) {
                agentRunLogService.record(
                        runId,
                        failed.userId(),
                        failed.conversationId(),
                        job
                );
                String error = job.path("error").asText("AI Agent 执行失败");
                saveLog(failed.userId(), failed.requestText(), error, "FAILED");
                if (failed.conversation() != null) {
                    conversationService.recordFailure(failed.conversation(), error);
                }
            }
        }
        return response;
    }

    public AiChatResponse chat(AiChatRequest request, Long authenticatedUserId) {
        // 请求体中的 userId 仅为旧版兼容字段，身份始终来自 JWT。
        Long userId = requireAuthenticatedUser(authenticatedUserId);
        String conversationId = hasText(request.conversationId())
                ? request.conversationId()
                : UUID.randomUUID().toString();
        AiConversation conversation = conversationService.findOrCreate(userId, conversationId, request.message());
        conversationService.recordUserMessage(conversation, request.message());

        try {
            JsonNode state = agentClient.run(conversationId, agentUserId(userId), request.message());
            AiChatResponse response = toResponse(state);
            saveLog(userId, request.message(), response.message(), response.status());
            if (conversation != null) {
                conversationService.recordAssistantMessage(conversation, response);
            }
            return response;
        } catch (RuntimeException ex) {
            saveLog(userId, request.message(), ex.getMessage(), "FAILED");
            if (conversation != null) {
                conversationService.recordFailure(conversation, ex.getMessage());
            }
            throw ex;
        }
    }

    public AiChatResponse resume(AiResumeRequest request, Long authenticatedUserId) {
        Long userId = requireAuthenticatedUser(authenticatedUserId);
        String requestText = request.confirmed() ? "确认预订" : "取消预订";
        AiConversation conversation = conversationService.findOrCreate(
                userId,
                request.conversationId(),
                requestText
        );
        conversationService.recordUserMessage(conversation, requestText);

        try {
            JsonNode state = agentClient.resume(
                    request.conversationId(),
                    agentUserId(userId),
                    request.confirmed()
            );
            AiChatResponse response = toResponse(state);
            saveLog(userId, requestText, response.message(), response.status());
            if (conversation != null) {
                conversationService.recordAssistantMessage(conversation, response);
            }
            return response;
        } catch (RuntimeException ex) {
            saveLog(userId, requestText, ex.getMessage(), "FAILED");
            if (conversation != null) {
                conversationService.recordFailure(conversation, ex.getMessage());
            }
            throw ex;
        }
    }

    private AiChatResponse toResponse(JsonNode state) {
        boolean interrupted = state.path("interrupted").asBoolean(false);
        boolean planSaved = state.path("plan_saved").asBoolean(false);
        boolean bookingCompleted = state.path("booking_completed").asBoolean(false);
        String status = interrupted
                ? "WAITING_CONFIRMATION"
                : bookingCompleted ? "BOOKING_COMPLETED" : planSaved ? "PLAN_SAVED" : "COMPLETED";
        JsonNode reply = state.get("reply");
        String message = reply == null || reply.isNull() ? "" : reply.asText();
        if (message.isBlank()) {
            message = fallbackMessage(state, interrupted, planSaved, bookingCompleted);
        }

        return new AiChatResponse(
                status,
                message,
                state.path("next_action").asText("complete"),
                state.path("conversation_id").asText(),
                state.path("intent").asText("unknown"),
                interrupted,
                state
        );
    }

    private String fallbackMessage(
            JsonNode state,
            boolean interrupted,
            boolean planSaved,
            boolean bookingCompleted
    ) {
        if (interrupted) {
            return "预订草稿已经创建，请确认后再提交。";
        }
        if (bookingCompleted) {
            return "预订请求已经提交，当前为后端 Mock 结果。";
        }
        if (planSaved) {
            String title = state.path("current_plan").path("title").asText("新的旅行方案");
            return title + "已经生成并保存，可以继续告诉我需要修改的地方。";
        }
        return "AI Agent 已完成本次处理。";
    }

    private void saveLog(Long userId, String requestText, String responseText, String status) {
        AiCallLog log = new AiCallLog();
        log.setUserId(userId);
        log.setRequestText(limit(requestText, 1024));
        log.setResponseText(limit(responseText, 2048));
        log.setStatus(status);
        aiCallLogMapper.insert(log);
    }

    private String agentUserId(Long userId) {
        return String.valueOf(userId);
    }

    private Long requireAuthenticatedUser(Long userId) {
        if (userId == null) {
            throw new AccessDeniedException("AI 接口需要登录后使用");
        }
        return userId;
    }

    private boolean hasText(String value) {
        return value != null && !value.isBlank();
    }

    private String limit(String value, int maxLength) {
        if (value == null) {
            return "";
        }
        return value.length() <= maxLength ? value : value.substring(0, maxLength);
    }

    private record AsyncCallContext(
            Long userId,
            String conversationId,
            String requestText,
            AiConversation conversation
    ) {
    }
}
