package com.oneclicktrip.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.oneclicktrip.client.FastApiAgentClient;
import com.oneclicktrip.dto.AiChatRequest;
import com.oneclicktrip.dto.AiChatResponse;
import com.oneclicktrip.dto.AiResumeRequest;
import com.oneclicktrip.entity.AiCallLog;
import com.oneclicktrip.mapper.AiCallLogMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class AiAssistantServiceTest {
    private final ObjectMapper objectMapper = new ObjectMapper();
    private FastApiAgentClient agentClient;
    private AiCallLogMapper logMapper;
    private AiConversationService conversationService;
    private AgentRunLogService agentRunLogService;
    private AiAssistantService service;

    @BeforeEach
    void setUp() {
        agentClient = mock(FastApiAgentClient.class);
        logMapper = mock(AiCallLogMapper.class);
        conversationService = mock(AiConversationService.class);
        agentRunLogService = mock(AgentRunLogService.class);
        service = new AiAssistantService(
                agentClient,
                logMapper,
                conversationService,
                agentRunLogService,
                objectMapper
        );
    }

    @Test
    void chatForwardsConversationAndUsesAuthenticatedUser() throws Exception {
        JsonNode state = objectMapper.readTree("""
                {
                  "conversation_id": "conversation-1",
                  "intent": "weather_query",
                  "next_action": "query_flow",
                  "reply": "成都明天多云，18-27 摄氏度。",
                  "interrupted": false
                }
                """);
        when(agentClient.run("conversation-1", "42", "成都明天天气怎么样？"))
                .thenReturn(state);

        AiChatResponse response = service.chat(
                new AiChatRequest(99L, "conversation-1", "成都明天天气怎么样？"),
                42L
        );

        assertThat(response.status()).isEqualTo("COMPLETED");
        assertThat(response.message()).contains("成都明天多云");
        assertThat(response.conversationId()).isEqualTo("conversation-1");
        assertThat(response.intent()).isEqualTo("weather_query");
        verify(agentClient).run("conversation-1", "42", "成都明天天气怎么样？");

        ArgumentCaptor<AiCallLog> logCaptor = ArgumentCaptor.forClass(AiCallLog.class);
        verify(logMapper).insert(logCaptor.capture());
        assertThat(logCaptor.getValue().getUserId()).isEqualTo(42L);
        assertThat(logCaptor.getValue().getStatus()).isEqualTo("COMPLETED");
    }

    @Test
    void resumeKeepsBookingInterruptVisible() throws Exception {
        JsonNode state = objectMapper.readTree("""
                {
                  "conversation_id": "conversation-2",
                  "intent": "booking",
                  "next_action": "booking_flow",
                  "reply": null,
                  "interrupted": true
                }
                """);
        when(agentClient.resume("conversation-2", "42", true)).thenReturn(state);

        AiChatResponse response = service.resume(
                new AiResumeRequest(null, "conversation-2", true),
                42L
        );

        assertThat(response.status()).isEqualTo("WAITING_CONFIRMATION");
        assertThat(response.interrupted()).isTrue();
        assertThat(response.message()).contains("预订草稿");
    }

    @Test
    void anonymousAiRequestIsRejectedBeforeCallingFastApi() {
        org.assertj.core.api.Assertions.assertThatThrownBy(() -> service.chat(
                        new AiChatRequest(99L, "conversation-private", "成都天气"),
                        null
                ))
                .isInstanceOf(org.springframework.security.access.AccessDeniedException.class)
                .hasMessageContaining("需要登录");
    }

    @Test
    void asyncJobCannotBeReadByAnotherAuthenticatedUser() throws Exception {
        JsonNode accepted = objectMapper.readTree("""
                {"run_id":"run-private","conversation_id":"conversation-private","status":"QUEUED"}
                """);
        when(agentClient.startRun("conversation-private", "42", "成都天气"))
                .thenReturn(accepted);
        service.startChat(
                new AiChatRequest(99L, "conversation-private", "成都天气"),
                42L
        );

        org.assertj.core.api.Assertions.assertThatThrownBy(() -> service.job("run-private", 43L))
                .isInstanceOf(org.springframework.security.access.AccessDeniedException.class)
                .hasMessageContaining("无权查看");
    }

    @Test
    void asyncChatReturnsImmediatelyAndPersistsTheCompletedResultOnce() throws Exception {
        JsonNode accepted = objectMapper.readTree("""
                {
                  "run_id": "run-async-1",
                  "conversation_id": "conversation-async-1",
                  "status": "QUEUED"
                }
                """);
        JsonNode completed = objectMapper.readTree("""
                {
                  "run_id": "run-async-1",
                  "conversation_id": "conversation-async-1",
                  "status": "COMPLETED",
                  "progress": 100,
                  "result": {
                    "conversation_id": "conversation-async-1",
                    "intent": "weather_query",
                    "next_action": "complete",
                    "reply": "成都明天多云。",
                    "interrupted": false
                  }
                }
                """);
        when(agentClient.startRun("conversation-async-1", "42", "成都明天天气怎么样？"))
                .thenReturn(accepted);
        when(agentClient.runJob("run-async-1", "42")).thenReturn(completed);

        JsonNode started = service.startChat(
                new AiChatRequest(null, "conversation-async-1", "成都明天天气怎么样？"),
                42L
        );
        JsonNode firstPoll = service.job("run-async-1", 42L);
        JsonNode secondPoll = service.job("run-async-1", 42L);

        assertThat(started.path("run_id").asText()).isEqualTo("run-async-1");
        assertThat(firstPoll.path("response").path("message").asText()).contains("成都明天多云");
        assertThat(secondPoll.path("response").path("status").asText()).isEqualTo("COMPLETED");
        verify(agentClient).startRun("conversation-async-1", "42", "成都明天天气怎么样？");
        verify(logMapper).insert(org.mockito.ArgumentMatchers.any(AiCallLog.class));
    }
}
