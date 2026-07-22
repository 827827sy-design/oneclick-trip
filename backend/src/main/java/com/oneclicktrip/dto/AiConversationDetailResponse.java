package com.oneclicktrip.dto;

import java.util.List;

public record AiConversationDetailResponse(
        AiConversationSummaryResponse conversation,
        List<AiMessageResponse> messages
) {
}
