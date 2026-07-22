package com.oneclicktrip.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

public record BookingDraftActionRequest(
        @JsonProperty("user_id") @NotBlank String userId,
        @JsonProperty("conversation_id") @NotBlank String conversationId,
        @JsonProperty("plan_id") @NotBlank String planId,
        @JsonProperty("plan_version") @NotNull @Positive Integer planVersion,
        @JsonProperty("confirmation_token") @NotBlank String confirmationToken,
        @JsonProperty("idempotency_key") @NotBlank String idempotencyKey
) {
}
