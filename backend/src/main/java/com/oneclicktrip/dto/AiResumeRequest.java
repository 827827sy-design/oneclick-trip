package com.oneclicktrip.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record AiResumeRequest(
        Long userId,
        @NotBlank String conversationId,
        @NotNull Boolean confirmed
) {
}
