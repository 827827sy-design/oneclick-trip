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
    private AiAssistantService service;

    @BeforeEach
    void setUp() {
        agentClient = mock(FastApiAgentClient.class);
        logMapper = mock(AiCallLogMapper.class);
        conversationService = mock(AiConversationService.class);
        service = new AiAssistantService(agentClient, logMapper, conversationService);
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
        when(agentClient.resume("conversation-2", "demo-user", true)).thenReturn(state);

        AiChatResponse response = service.resume(
                new AiResumeRequest(null, "conversation-2", true),
                null
        );

        assertThat(response.status()).isEqualTo("WAITING_CONFIRMATION");
        assertThat(response.interrupted()).isTrue();
        assertThat(response.message()).contains("预订草稿");
    }
}
