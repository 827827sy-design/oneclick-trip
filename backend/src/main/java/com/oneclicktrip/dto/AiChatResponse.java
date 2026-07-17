package com.oneclicktrip.dto;

import com.fasterxml.jackson.databind.JsonNode;

public record AiChatResponse(
        String status,
        String message,
        String nextStep,
        String conversationId,
        String intent,
        boolean interrupted,
        JsonNode agentState
) {
}
