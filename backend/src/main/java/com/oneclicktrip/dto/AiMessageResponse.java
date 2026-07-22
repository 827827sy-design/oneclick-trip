package com.oneclicktrip.dto;

import com.fasterxml.jackson.databind.JsonNode;

import java.time.LocalDateTime;

public record AiMessageResponse(
        Long id,
        String role,
        String content,
        String status,
        String intent,
        JsonNode agentState,
        LocalDateTime createTime
) {
}
