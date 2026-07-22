package com.oneclicktrip.controller;

import com.oneclicktrip.common.ApiResponse;
import com.oneclicktrip.dto.AiConversationDetailResponse;
import com.oneclicktrip.dto.AiConversationSummaryResponse;
import com.oneclicktrip.dto.CreateAiConversationRequest;
import com.oneclicktrip.dto.RenameAiConversationRequest;
import com.oneclicktrip.security.JwtUser;
import com.oneclicktrip.service.AiConversationService;
import jakarta.validation.Valid;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/ai/conversations")
public class AiConversationController {
    private final AiConversationService conversationService;

    public AiConversationController(AiConversationService conversationService) {
        this.conversationService = conversationService;
    }

    @GetMapping
    public ApiResponse<List<AiConversationSummaryResponse>> list(@AuthenticationPrincipal JwtUser currentUser) {
        return ApiResponse.ok(conversationService.list(currentUser.userId()));
    }

    @PostMapping
    public ApiResponse<AiConversationSummaryResponse> create(
            @RequestBody(required = false) CreateAiConversationRequest request,
            @AuthenticationPrincipal JwtUser currentUser
    ) {
        String title = request == null ? null : request.title();
        return ApiResponse.ok(conversationService.create(currentUser.userId(), title));
    }

    @GetMapping("/{conversationId}")
    public ApiResponse<AiConversationDetailResponse> detail(
            @PathVariable String conversationId,
            @AuthenticationPrincipal JwtUser currentUser
    ) {
        return ApiResponse.ok(conversationService.detail(currentUser.userId(), conversationId));
    }

    @PutMapping("/{conversationId}")
    public ApiResponse<AiConversationSummaryResponse> rename(
            @PathVariable String conversationId,
            @Valid @RequestBody RenameAiConversationRequest request,
            @AuthenticationPrincipal JwtUser currentUser
    ) {
        return ApiResponse.ok(conversationService.rename(currentUser.userId(), conversationId, request.title()));
    }

    @DeleteMapping("/{conversationId}")
    public ApiResponse<Void> delete(
            @PathVariable String conversationId,
            @AuthenticationPrincipal JwtUser currentUser
    ) {
        conversationService.delete(currentUser.userId(), conversationId);
        return ApiResponse.ok(null);
    }
}
