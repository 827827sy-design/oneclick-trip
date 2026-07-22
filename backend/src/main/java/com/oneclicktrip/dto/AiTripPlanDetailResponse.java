package com.oneclicktrip.dto;

import com.fasterxml.jackson.databind.JsonNode;

public record AiTripPlanDetailResponse(
        Long recordId,
        String conversationId,
        String planId,
        Integer version,
        JsonNode plan,
        JsonNode entities,
        JsonNode selectedOptions
) {
}
