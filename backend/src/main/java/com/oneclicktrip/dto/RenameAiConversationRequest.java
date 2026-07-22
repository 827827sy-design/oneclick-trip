package com.oneclicktrip.dto;

import jakarta.validation.constraints.NotBlank;

public record RenameAiConversationRequest(@NotBlank(message = "会话标题不能为空") String title) {
}
