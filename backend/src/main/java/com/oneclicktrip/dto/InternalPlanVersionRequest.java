package com.oneclicktrip.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.JsonNode;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record InternalPlanVersionRequest(
        @JsonProperty("user_id") @NotBlank String userId,
        @JsonProperty("conversation_id") @NotBlank String conversationId,
        @JsonProperty("plan_state") @NotNull JsonNode planState
) {
}
