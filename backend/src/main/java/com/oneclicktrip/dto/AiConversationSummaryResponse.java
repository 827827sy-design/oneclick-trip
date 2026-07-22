package com.oneclicktrip.dto;

import java.time.LocalDateTime;

public record AiConversationSummaryResponse(
        Long id,
        String conversationId,
        String title,
        String status,
        String lastMessagePreview,
        Integer messageCount,
        LocalDateTime createTime,
        LocalDateTime updateTime
) {
}
