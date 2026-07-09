package com.oneclicktrip.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record UpdateUserProfileRequest(
        @NotBlank @Size(max = 64) String nickname,
        @NotBlank @Size(max = 64) String avatarUrl
) {
}
