package com.oneclicktrip.controller.admin;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.oneclicktrip.common.ApiResponse;
import com.oneclicktrip.common.BusinessException;
import com.oneclicktrip.entity.AiConversation;
import com.oneclicktrip.entity.AiMessage;
import com.oneclicktrip.mapper.AiConversationMapper;
import com.oneclicktrip.mapper.AiMessageMapper;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

@RestController
@RequestMapping("/api/admin/conversations")
public class AdminAiConversationController {

    private static final Pattern SENSITIVE_VALUE = Pattern.compile(
            "(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|authorization|password|secret)"
                    + "(\\s*[:=]\\s*|\\s*[\\\"']\\s*:\\s*[\\\"'])([^\\s,;\\\"'}]+)"
    );
    private static final Pattern BEARER_TOKEN = Pattern.compile("(?i)Bearer\\s+[A-Za-z0-9._~-]+");

    private final AiConversationMapper conversationMapper;
    private final AiMessageMapper messageMapper;

    public AdminAiConversationController(
            AiConversationMapper conversationMapper,
            AiMessageMapper messageMapper
    ) {
        this.conversationMapper = conversationMapper;
        this.messageMapper = messageMapper;
    }

    @GetMapping
    public ApiResponse<Page<AiConversation>> list(
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "10") int size,
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) Long userId,
            @RequestParam(required = false) String status
    ) {
        int safePage = Math.max(page, 1);
        int safeSize = Math.min(Math.max(size, 1), 100);
        LambdaQueryWrapper<AiConversation> wrapper = Wrappers.<AiConversation>lambdaQuery()
                .eq(AiConversation::getDeleted, 0)
                .orderByDesc(AiConversation::getUpdateTime);

        if (userId != null) {
            wrapper.eq(AiConversation::getUserId, userId);
        }
        if (status != null && !status.isBlank()) {
            wrapper.eq(AiConversation::getStatus, status.trim().toUpperCase());
        }
        if (keyword != null && !keyword.isBlank()) {
            String value = keyword.trim();
            wrapper.and(query -> {
                query.like(AiConversation::getConversationId, value)
                        .or().like(AiConversation::getTitle, value);
                try {
                    query.or().eq(AiConversation::getUserId, Long.parseLong(value));
                } catch (NumberFormatException ignored) {
                    // 非数字关键词只匹配会话 ID 和标题。
                }
            });
        }

        Page<AiConversation> result = conversationMapper.selectPage(new Page<>(safePage, safeSize), wrapper);
        result.getRecords().forEach(this::sanitizeConversation);
        return ApiResponse.ok(result);
    }

    @GetMapping("/{id}")
    public ApiResponse<Map<String, Object>> detail(@PathVariable Long id) {
        AiConversation conversation = requireConversation(id);
        sanitizeConversation(conversation);

        List<Map<String, Object>> messages = messageMapper.selectList(
                Wrappers.<AiMessage>lambdaQuery()
                        .eq(AiMessage::getAiConversationId, id)
                        .orderByAsc(AiMessage::getId)
        ).stream().map(this::toSafeMessage).toList();

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("id", conversation.getId());
        result.put("conversationId", conversation.getConversationId());
        result.put("userId", conversation.getUserId());
        result.put("title", conversation.getTitle());
        result.put("status", conversation.getStatus());
        result.put("lastMessagePreview", conversation.getLastMessagePreview());
        result.put("messageCount", conversation.getMessageCount());
        result.put("createTime", conversation.getCreateTime());
        result.put("updateTime", conversation.getUpdateTime());
        result.put("messages", messages);
        return ApiResponse.ok(result);
    }

    @DeleteMapping("/{id}")
    public ApiResponse<Void> delete(@PathVariable Long id) {
        AiConversation conversation = requireConversation(id);
        conversation.setDeleted(1);
        conversationMapper.updateById(conversation);
        return ApiResponse.ok(null);
    }

    private AiConversation requireConversation(Long id) {
        AiConversation conversation = conversationMapper.selectById(id);
        if (conversation == null || Integer.valueOf(1).equals(conversation.getDeleted())) {
            throw new BusinessException("会话不存在");
        }
        return conversation;
    }

    private Map<String, Object> toSafeMessage(AiMessage message) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("id", message.getId());
        result.put("role", message.getRole());
        result.put("content", redact(message.getContent()));
        result.put("status", message.getStatus());
        result.put("intent", message.getIntent());
        result.put("createTime", message.getCreateTime());
        // agentStateJson 可能包含身份、确认令牌或供应商参数，管理端默认不返回原文。
        result.put("hasAgentState", message.getAgentStateJson() != null && !message.getAgentStateJson().isBlank());
        return result;
    }

    private void sanitizeConversation(AiConversation conversation) {
        conversation.setLastMessagePreview(redact(conversation.getLastMessagePreview()));
    }

    private String redact(String value) {
        if (value == null || value.isBlank()) {
            return value;
        }
        String redacted = BEARER_TOKEN.matcher(value).replaceAll("Bearer [REDACTED]");
        return SENSITIVE_VALUE.matcher(redacted).replaceAll("$1$2[REDACTED]");
    }
}
