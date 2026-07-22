package com.oneclicktrip.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.JsonNode;

import java.time.LocalDateTime;

public record InternalPreferenceResponse(
        @JsonProperty("user_id") String userId,
        JsonNode preferences,
        @JsonProperty("source_version") int sourceVersion,
        @JsonProperty("updated_at") LocalDateTime updatedAt
) {
}
