package com.oneclicktrip.client;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.oneclicktrip.common.AiServiceException;
import com.oneclicktrip.common.BusinessException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;


@Component
public class FastApiAgentClient {
    private final RestClient restClient;
    private final ObjectMapper objectMapper;

    public FastApiAgentClient(
            @Qualifier("aiRestClient") RestClient restClient,
            ObjectMapper objectMapper
    ) {
        this.restClient = restClient;
        this.objectMapper = objectMapper;
    }

    public JsonNode run(String conversationId, String userId, String message) {
        return post(
                "/v1/agent/runs",
                new AgentRunRequest(conversationId, userId, message),
                "执行 AI 会话"
        );
    }

    public JsonNode startRun(String conversationId, String userId, String message) {
        return post(
                "/v1/agent/runs/async",
                new AgentRunRequest(conversationId, userId, message),
                "创建 AI 后台任务"
        );
    }

    public JsonNode runJob(String runId, String userId) {
        return get(
                "/v1/agent/runs/jobs/{runId}?user_id={userId}",
                "查询 AI 任务进度",
                runId,
                userId
        );
    }

    public JsonNode resume(String conversationId, String userId, boolean confirmed) {
        return post(
                "/v1/agent/runs/resume",
                new AgentResumeRequest(conversationId, userId, confirmed),
                "恢复 AI 会话"
        );
    }

    public JsonNode knowledgeStats() {
        return get("/v1/internal/knowledge/stats", "查询知识库统计");
    }

    public JsonNode rebuildKnowledgeIndex() {
        return post(
                "/v1/internal/knowledge/rebuild",
                objectMapper.createObjectNode(),
                "重建知识库索引"
        );
    }


    public JsonNode knowledgeBatches() {
        return get("/v1/internal/knowledge/batches", "查询知识更新批次");
    }

    public JsonNode knowledgeBatch(String batchId) {
        return get("/v1/internal/knowledge/batches/" + batchId, "查询知识更新批次");
    }

    public JsonNode previewKnowledge(JsonNode payload) {
        return post("/v1/internal/knowledge/batches/preview", payload, "清洗知识资料");
    }

    public JsonNode collectKnowledge(JsonNode payload) {
        return post("/v1/internal/knowledge/collect", payload, "采集知识资料");
    }

    public JsonNode reviewKnowledgeRecord(
            String batchId,
            String recordId,
            JsonNode payload,
            String reviewer
    ) {
        return post(
                "/v1/internal/knowledge/batches/" + batchId + "/records/" + recordId + "/review",
                withReviewer(payload, reviewer),
                "审核知识资料"
        );
    }

    public JsonNode deleteApprovedKnowledgeRecord(
            String batchId,
            String recordId,
            JsonNode payload,
            String reviewer
    ) {
        return delete(
                "/v1/internal/knowledge/batches/" + batchId + "/records/" + recordId,
                withReviewer(payload, reviewer),
                "删除已通过知识资料"
        );
    }

    public JsonNode rejectKnowledgeBatch(String batchId, JsonNode payload, String reviewer) {
        return post(
                "/v1/internal/knowledge/batches/" + batchId + "/reject",
                withReviewer(payload, reviewer),
                "驳回知识批次"
        );
    }

    public JsonNode reopenKnowledgeBatch(String batchId, String reviewer) {
        ObjectNode payload = objectMapper.createObjectNode();
        payload.put("reviewer", reviewer);
        return post(
                "/v1/internal/knowledge/batches/" + batchId + "/reopen",
                payload,
                "恢复知识批次审核"
        );
    }

    public JsonNode publishKnowledge(String batchId, String reviewer) {
        ObjectNode payload = objectMapper.createObjectNode();
        payload.put("reviewer", reviewer);
        return post(
                "/v1/internal/knowledge/batches/" + batchId + "/publish",
                payload,
                "发布知识批次"
        );
    }

    private ObjectNode withReviewer(JsonNode payload, String reviewer) {
        ObjectNode forwarded = payload != null && payload.isObject()
                ? (ObjectNode) payload.deepCopy()
                : objectMapper.createObjectNode();
        forwarded.put("reviewer", reviewer);
        return forwarded;
    }

    private JsonNode get(String path, String action, Object... uriVariables) {
        try {
            JsonNode response = restClient.get()
                    .uri(path, uriVariables)
                    .accept(MediaType.APPLICATION_JSON)
                    .retrieve()
                    .body(JsonNode.class);
            if (response == null) {
                throw new AiServiceException(action + "失败：FastAPI 返回了空响应");
            }
            return response;
        } catch (RestClientResponseException ex) {
            throw responseException(action, ex);
        } catch (ResourceAccessException ex) {
            throw unavailableException(ex);
        }
    }

    private JsonNode post(String path, Object body, String action) {
        try {
            JsonNode response = restClient.post()
                    .uri(path)
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .body(body)
                    .retrieve()
                    .body(JsonNode.class);
            if (response == null) {
                throw new AiServiceException(action + "失败：FastAPI 返回了空响应");
            }
            return response;
        } catch (RestClientResponseException ex) {
            throw responseException(action, ex);
        } catch (ResourceAccessException ex) {
            throw unavailableException(ex);
        }
    }

    private JsonNode delete(String path, Object body, String action) {
        try {
            JsonNode response = restClient.method(HttpMethod.DELETE)
                    .uri(path)
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .body(body)
                    .retrieve()
                    .body(JsonNode.class);
            if (response == null) {
                throw new AiServiceException(action + "失败：FastAPI 返回了空响应");
            }
            return response;
        } catch (RestClientResponseException ex) {
            throw responseException(action, ex);
        } catch (ResourceAccessException ex) {
            throw unavailableException(ex);
        }
    }

    private RuntimeException responseException(String action, RestClientResponseException ex) {
        String detail = extractDetail(ex.getResponseBodyAsString());
        if (ex.getStatusCode() == HttpStatus.CONFLICT) {
            return new BusinessException(detail);
        }
        return new AiServiceException(
                action + "失败（HTTP " + ex.getStatusCode().value() + "）：" + detail,
                ex
        );
    }

    private AiServiceException unavailableException(ResourceAccessException ex) {
        return new AiServiceException(
                "无法连接 FastAPI AI 服务，请确认它已在配置地址启动",
                ex
        );
    }

    private String extractDetail(String responseBody) {
        try {
            JsonNode body = objectMapper.readTree(responseBody);
            String detail = body.path("detail").asText();
            return detail.isBlank() ? responseBody : detail;
        } catch (Exception ignored) {
            return responseBody == null || responseBody.isBlank() ? "未知错误" : responseBody;
        }
    }

    private record AgentRunRequest(
            @JsonProperty("conversation_id") String conversationId,
            @JsonProperty("user_id") String userId,
            String message
    ) {
    }

    private record AgentResumeRequest(
            @JsonProperty("conversation_id") String conversationId,
            @JsonProperty("user_id") String userId,
            boolean confirmed
    ) {
    }
}
