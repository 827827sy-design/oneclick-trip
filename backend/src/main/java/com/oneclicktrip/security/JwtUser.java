package com.oneclicktrip.security;

public record JwtUser(Long userId, String username, String role) {
}

