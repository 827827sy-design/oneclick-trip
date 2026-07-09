package com.oneclicktrip.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record RegisterRequest(
        @NotBlank @Size(min = 3, max = 32) String username,
        @NotBlank @Size(min = 6, max = 32) String password,
        @NotBlank @Size(max = 32) String nickname,
        String mobile
) {
}

