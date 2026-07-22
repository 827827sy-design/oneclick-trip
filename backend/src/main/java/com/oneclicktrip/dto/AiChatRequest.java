package com.oneclicktrip.dto;

import jakarta.validation.constraints.NotBlank;

public record AiChatRequest(
        Long userId,
        String conversationId,
        @NotBlank String message,
        Boolean ignoreUserPreferences
) {
    public AiChatRequest(Long userId, String conversationId, String message) {
        this(userId, conversationId, message, false);
    }
}
