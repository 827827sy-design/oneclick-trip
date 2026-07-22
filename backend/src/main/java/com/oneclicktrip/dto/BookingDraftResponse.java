package com.oneclicktrip.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.time.LocalDateTime;
import java.util.List;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record BookingDraftResponse(
        @JsonProperty("draft_id") String draftId,
        String status,
        @JsonProperty("conversation_id") String conversationId,
        @JsonProperty("user_id") String userId,
        @JsonProperty("plan_id") String planId,
        @JsonProperty("plan_version") int planVersion,
        @JsonProperty("booking_types") List<String> bookingTypes,
        @JsonProperty("selected_option_ids") List<String> selectedOptionIds,
        @JsonProperty("created_at") LocalDateTime createdAt,
        @JsonProperty("expires_at") LocalDateTime expiresAt,
        @JsonProperty("confirmation_token") String confirmationToken
) {
}
