package com.oneclicktrip.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.oneclicktrip.client.FastApiAgentClient;
import com.oneclicktrip.dto.AiChatRequest;
import com.oneclicktrip.dto.AiChatResponse;
import com.oneclicktrip.dto.AiResumeRequest;
import com.oneclicktrip.entity.AiCallLog;
import com.oneclicktrip.entity.AiConversation;
import com.oneclicktrip.mapper.AiCallLogMapper;
import org.springframework.stereotype.Service;

import java.util.UUID;

@Service
public class AiAssistantService {
    private final FastApiAgentClient agentClient;
    private final AiCallLogMapper aiCallLogMapper;
    private final AiConversationService conversationService;

    public AiAssistantService(
            FastApiAgentClient agentClient,
            AiCallLogMapper aiCallLogMapper,
            AiConversationService conversationService
    ) {
        this.agentClient = agentClient;
        this.aiCallLogMapper = aiCallLogMapper;
        this.conversationService = conversationService;
    }

    public AiChatResponse chat(AiChatRequest request, Long authenticatedUserId) {
        // userId 只信任 JWT 解析结果；公开演示请求统一映射到 demo-user。
        Long userId = authenticatedUserId;
        String conversationId = hasText(request.conversationId())
                ? request.conversationId()
                : UUID.randomUUID().toString();
        AiConversation conversation = userId == null
                ? null
                : conversationService.findOrCreate(userId, conversationId, request.message());
        if (conversation != null) {
            conversationService.recordUserMessage(conversation, request.message());
        }

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
        Long userId = authenticatedUserId;
        String requestText = request.confirmed() ? "确认预订" : "取消预订";
        AiConversation conversation = userId == null
                ? null
                : conversationService.findOrCreate(userId, request.conversationId(), requestText);
        if (conversation != null) {
            conversationService.recordUserMessage(conversation, requestText);
        }

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
        return userId == null ? "demo-user" : String.valueOf(userId);
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
}
