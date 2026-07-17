package com.oneclicktrip.client;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.oneclicktrip.common.AiServiceException;
import com.oneclicktrip.common.BusinessException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatus;
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

    public JsonNode resume(String conversationId, String userId, boolean confirmed) {
        return post(
                "/v1/agent/runs/resume",
                new AgentResumeRequest(conversationId, userId, confirmed),
                "恢复 AI 会话"
        );
    }

    private JsonNode post(String path, Object body, String action) {
        try {
            JsonNode response = restClient.post()
                    .uri(path)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(body)
                    .retrieve()
                    .body(JsonNode.class);
            if (response == null) {
                throw new AiServiceException(action + "失败：FastAPI 返回了空响应");
            }
            return response;
        } catch (RestClientResponseException ex) {
            String detail = extractDetail(ex.getResponseBodyAsString());
            if (ex.getStatusCode() == HttpStatus.CONFLICT) {
                throw new BusinessException(detail);
            }
            throw new AiServiceException(
                    action + "失败（HTTP " + ex.getStatusCode().value() + "）：" + detail,
                    ex
            );
        } catch (ResourceAccessException ex) {
            throw new AiServiceException(
                    "无法连接 FastAPI AI 服务，请确认它已在配置地址启动",
                    ex
            );
        }
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
