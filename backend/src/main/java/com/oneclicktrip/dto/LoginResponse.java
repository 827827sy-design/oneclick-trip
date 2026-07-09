package com.oneclicktrip.dto;

public record LoginResponse(
        String token,
        Long userId,
        String username,
        String nickname,
        String avatarUrl,
        String role
) {
}
