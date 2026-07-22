package com.oneclicktrip.controller;

import com.oneclicktrip.common.ApiResponse;
import com.oneclicktrip.entity.AiConversation;
import com.oneclicktrip.entity.AiMessage;
import com.oneclicktrip.security.JwtUser;
import com.oneclicktrip.service.AiConversationService;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/ai/conversations")
public class AiConversationController {
    private final AiConversationService conversationService;

    public AiConversationController(AiConversationService conversationService) {
        this.conversationService = conversationService;
    }

    @GetMapping
    public ApiResponse<List<Map<String, Object>>> list(@AuthenticationPrincipal JwtUser currentUser) {
        List<AiConversation> list = conversationService.listByUser(currentUser.userId());
        List<Map<String, Object>> result = list.stream().map(conv -> {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("conversationId", conv.getConversationId());
            item.put("title", conv.getTitle());
            item.put("lastMessagePreview", conv.getLastMessagePreview());
            item.put("messageCount", conv.getMessageCount());
            item.put("updateTime", conv.getUpdateTime() != null ? conv.getUpdateTime().toString() : null);
            return item;
        }).toList();
        return ApiResponse.ok(result);
    }

    @PostMapping
    public ApiResponse<Map<String, Object>> create(
            @AuthenticationPrincipal JwtUser currentUser,
            @RequestBody(required = false) Map<String, String> body
    ) {
        String title = body != null ? body.getOrDefault("title", "") : "";
        AiConversation conv = conversationService.create(currentUser.userId(), title);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("conversationId", conv.getConversationId());
        result.put("title", conv.getTitle());
        return ApiResponse.ok(result);
    }

    @GetMapping("/{conversationId}")
    public ApiResponse<Map<String, Object>> detail(
            @AuthenticationPrincipal JwtUser currentUser,
            @PathVariable String conversationId
    ) {
        AiConversation conv = conversationService.findById(conversationId, currentUser.userId());
        if (conv == null) {
            return ApiResponse.fail("会话不存在");
        }
        List<AiMessage> messages = conversationService.getMessages(conv.getId());
        List<Map<String, Object>> msgList = messages.stream().map(msg -> {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("role", msg.getRole());
            item.put("content", msg.getContent());
            item.put("status", msg.getStatus());
            item.put("intent", msg.getIntent());
            item.put("agentState", msg.getAgentStateJson() != null
                    ? java.util.Collections.singletonMap("raw", msg.getAgentStateJson())
                    : null);
            return item;
        }).toList();

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("conversationId", conv.getConversationId());
        result.put("title", conv.getTitle());
        result.put("messages", msgList);
        return ApiResponse.ok(result);
    }

    @PutMapping("/{conversationId}")
    public ApiResponse<Void> rename(
            @AuthenticationPrincipal JwtUser currentUser,
            @PathVariable String conversationId,
            @RequestBody Map<String, String> body
    ) {
        String title = body != null ? body.getOrDefault("title", "") : "";
        conversationService.rename(conversationId, currentUser.userId(), title);
        return ApiResponse.ok(null);
    }

    @DeleteMapping("/{conversationId}")
    public ApiResponse<Void> delete(
            @AuthenticationPrincipal JwtUser currentUser,
            @PathVariable String conversationId
    ) {
        conversationService.softDelete(conversationId, currentUser.userId());
        return ApiResponse.ok(null);
    }
}
