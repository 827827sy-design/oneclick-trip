package com.oneclicktrip.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.JsonNode;
import jakarta.validation.constraints.NotNull;

public record InternalPreferenceRequest(
        @NotNull JsonNode preferences,
        @JsonProperty("source_version") Integer sourceVersion
) {
}
