package com.oneclicktrip.dto;

public record AiChatResponse(
        String status,
        String message,
        String nextStep
) {
}

