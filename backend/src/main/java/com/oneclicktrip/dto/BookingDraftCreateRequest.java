package com.oneclicktrip.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

import java.util.List;

public record BookingDraftCreateRequest(
        @JsonProperty("user_id") @NotBlank String userId,
        @JsonProperty("conversation_id") @NotBlank String conversationId,
        @JsonProperty("plan_id") @NotBlank String planId,
        @JsonProperty("plan_version") @NotNull @Positive Integer planVersion,
        @JsonProperty("booking_types") @NotEmpty List<String> bookingTypes,
        @JsonProperty("selected_option_ids") @NotEmpty List<String> selectedOptionIds
) {
}
