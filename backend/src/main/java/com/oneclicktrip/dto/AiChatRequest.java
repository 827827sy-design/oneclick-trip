package com.oneclicktrip.dto;

import jakarta.validation.constraints.NotBlank;

public record AiChatRequest(
        Long userId,
        String conversationId,
        @NotBlank String message
) {
}
