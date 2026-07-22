package com.oneclicktrip.controller;

import com.fasterxml.jackson.databind.JsonNode;
import com.oneclicktrip.common.ApiResponse;
import com.oneclicktrip.dto.AiChatRequest;
import com.oneclicktrip.dto.AiChatResponse;
import com.oneclicktrip.dto.AiResumeRequest;
import com.oneclicktrip.security.JwtUser;
import com.oneclicktrip.service.AiAssistantService;
import jakarta.validation.Valid;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/ai")
public class AiAssistantController {
    private final AiAssistantService aiAssistantService;

    public AiAssistantController(AiAssistantService aiAssistantService) {
        this.aiAssistantService = aiAssistantService;
    }

    @PostMapping("/chat")
    public ApiResponse<AiChatResponse> chat(
            @Valid @RequestBody AiChatRequest request,
            @AuthenticationPrincipal JwtUser currentUser
    ) {
        Long authenticatedUserId = currentUser == null ? null : currentUser.userId();
        return ApiResponse.ok(aiAssistantService.chat(request, authenticatedUserId));
    }

    @PostMapping("/chat/async")
    public ApiResponse<JsonNode> startChat(
            @Valid @RequestBody AiChatRequest request,
            @AuthenticationPrincipal JwtUser currentUser
    ) {
        Long authenticatedUserId = currentUser == null ? null : currentUser.userId();
        return ApiResponse.ok(aiAssistantService.startChat(request, authenticatedUserId));
    }

    @GetMapping("/jobs/{runId}")
    public ApiResponse<JsonNode> job(
            @PathVariable String runId,
            @AuthenticationPrincipal JwtUser currentUser
    ) {
        Long authenticatedUserId = currentUser == null ? null : currentUser.userId();
        return ApiResponse.ok(aiAssistantService.job(runId, authenticatedUserId));
    }

    @PostMapping("/resume")
    public ApiResponse<AiChatResponse> resume(
            @Valid @RequestBody AiResumeRequest request,
            @AuthenticationPrincipal JwtUser currentUser
    ) {
        Long authenticatedUserId = currentUser == null ? null : currentUser.userId();
        return ApiResponse.ok(aiAssistantService.resume(request, authenticatedUserId));
    }
}
