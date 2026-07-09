package com.oneclicktrip.dto;

public record UserProfileResponse(
        Long userId,
        String username,
        String nickname,
        String avatarUrl,
        String role
) {
}
