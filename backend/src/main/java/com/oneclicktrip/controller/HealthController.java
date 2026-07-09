package com.oneclicktrip.controller;

import com.oneclicktrip.common.ApiResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDateTime;
import java.util.Map;

@RestController
public class HealthController {
    @GetMapping("/api/health")
    public ApiResponse<Map<String, Object>> health() {
        return ApiResponse.ok(Map.of(
                "service", "oneclick-trip-backend",
                "status", "UP",
                "time", LocalDateTime.now().toString()
        ));
    }
}

