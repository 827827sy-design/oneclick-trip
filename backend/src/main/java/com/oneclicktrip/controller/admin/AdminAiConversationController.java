package com.oneclicktrip.controller.admin;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.oneclicktrip.common.ApiResponse;
import com.oneclicktrip.common.BusinessException;
import com.oneclicktrip.entity.AiConversation;
import com.oneclicktrip.entity.AiMessage;
import com.oneclicktrip.entity.User;
import com.oneclicktrip.mapper.AiConversationMapper;
import com.oneclicktrip.mapper.AiMessageMapper;
import com.oneclicktrip.mapper.UserMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.*;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

@RestController
@RequestMapping("/api/admin/conversations")
public class AdminAiConversationController {
    private static final Pattern SENSITIVE_VALUE = Pattern.compile(
            "(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|authorization|password|secret|confirmation[_-]?token)"
                    + "(\\s*[:=]\\s*|\\s*[\\\"']\\s*:\\s*[\\\"'])([^\\s,;\\\"'}]+)"
    );
    private static final Pattern BEARER_TOKEN = Pattern.compile("(?i)Bearer\\s+[A-Za-z0-9._~-]+");
    private final AiConversationMapper conversationMapper;
    private final AiMessageMapper messageMapper;
    private final UserMapper userMapper;
    private final ObjectMapper objectMapper;
    private final JdbcTemplate jdbcTemplate;

    public AdminAiConversationController(
            AiConversationMapper conversationMapper,
            AiMessageMapper messageMapper,
            UserMapper userMapper,
            ObjectMapper objectMapper,
            JdbcTemplate jdbcTemplate
    ) {
        this.conversationMapper = conversationMapper;
        this.messageMapper = messageMapper;
        this.userMapper = userMapper;
        this.objectMapper = objectMapper;
        this.jdbcTemplate = jdbcTemplate;
    }

    @GetMapping
    public ApiResponse<Page<Map<String, Object>>> list(
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "10") int size,
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) Long userId
    ) {
        LambdaQueryWrapper<AiConversation> wrapper = Wrappers.<AiConversation>lambdaQuery()
                .eq(AiConversation::getDeleted, 0)
                .orderByDesc(AiConversation::getUpdateTime);

        if (userId != null) {
            wrapper.eq(AiConversation::getUserId, userId);
        }

        List<Long> matchedUserIds = List.of();
        if (hasText(keyword)) {
            matchedUserIds = userMapper.selectList(Wrappers.<User>lambdaQuery()
                            .eq(User::getDeleted, 0)
                            .and(w -> w.like(User::getUsername, keyword).or().like(User::getNickname, keyword)))
                    .stream().map(User::getId).toList();
            List<Long> finalMatchedUserIds = matchedUserIds;
            wrapper.and(w -> {
                w.like(AiConversation::getTitle, keyword)
                        .or().like(AiConversation::getConversationId, keyword);
                if (!finalMatchedUserIds.isEmpty()) {
                    w.or().in(AiConversation::getUserId, finalMatchedUserIds);
                }
            });
        }

        Page<AiConversation> source = conversationMapper.selectPage(new Page<>(page, size), wrapper);
        Map<Long, User> users = loadUsers(source.getRecords());
        List<Map<String, Object>> records = source.getRecords().stream()
                .map(conversation -> conversationMap(conversation, users.get(conversation.getUserId())))
                .toList();

        Page<Map<String, Object>> result = new Page<>(source.getCurrent(), source.getSize(), source.getTotal());
        result.setRecords(records);
        result.setPages(source.getPages());
        return ApiResponse.ok(result);
    }

    @GetMapping("/{id}")
    public ApiResponse<Map<String, Object>> detail(@PathVariable Long id) {
        AiConversation conversation = conversationMapper.selectById(id);
        if (conversation == null || Integer.valueOf(1).equals(conversation.getDeleted())) {
            throw new BusinessException("会话不存在");
        }
        User user = userMapper.selectById(conversation.getUserId());
        List<Map<String, Object>> messages = messageMapper.selectList(Wrappers.<AiMessage>lambdaQuery()
                        .eq(AiMessage::getAiConversationId, id)
                        .orderByAsc(AiMessage::getId))
                .stream().map(this::messageMap).toList();

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("conversation", conversationMap(conversation, user));
        result.put("messages", messages);
        result.put("planVersions", planVersions(conversation.getConversationId()));
        return ApiResponse.ok(result);
    }

    @DeleteMapping("/{id}")
    public ApiResponse<Void> delete(@PathVariable Long id) {
        AiConversation conversation = conversationMapper.selectById(id);
        if (conversation == null) {
            throw new BusinessException("会话不存在");
        }
        conversation.setDeleted(1);
        conversationMapper.updateById(conversation);
        return ApiResponse.ok(null);
    }

    private Map<Long, User> loadUsers(List<AiConversation> conversations) {
        List<Long> userIds = conversations.stream().map(AiConversation::getUserId).distinct().toList();
        if (userIds.isEmpty()) {
            return Map.of();
        }
        return userMapper.selectBatchIds(userIds).stream()
                .collect(Collectors.toMap(User::getId, Function.identity()));
    }

    private Map<String, Object> conversationMap(AiConversation conversation, User user) {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("id", conversation.getId());
        data.put("conversationId", conversation.getConversationId());
        data.put("userId", conversation.getUserId());
        data.put("username", user == null ? "未知用户" : user.getUsername());
        data.put("nickname", user == null ? "" : user.getNickname());
        data.put("title", conversation.getTitle());
        data.put("status", conversation.getStatus());
        data.put("lastMessagePreview", redact(conversation.getLastMessagePreview()));
        data.put("messageCount", conversation.getMessageCount());
        data.put("createTime", conversation.getCreateTime());
        data.put("updateTime", conversation.getUpdateTime());
        return data;
    }

    private Map<String, Object> messageMap(AiMessage message) {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("id", message.getId());
        data.put("role", message.getRole());
        data.put("content", redact(message.getContent()));
        data.put("status", message.getStatus());
        data.put("intent", message.getIntent());
        data.put("createTime", message.getCreateTime());
        // 完整 Agent State 可能包含身份、供应商参数或确认凭证，管理端默认不返回原文。
        data.put("hasAgentState", hasText(message.getAgentStateJson()));
        return data;
    }

    private List<Map<String, Object>> planVersions(String conversationId) {
        return jdbcTemplate.query("""
                SELECT id, plan_id, plan_version, destination, plan_json, is_current, created_at
                FROM ai_travel_plan_versions
                WHERE conversation_id = ?
                ORDER BY plan_version DESC, created_at DESC
                """, (rs, rowNum) -> {
            Map<String, Object> data = new LinkedHashMap<>();
            data.put("id", rs.getLong("id"));
            data.put("planId", rs.getString("plan_id"));
            data.put("planVersion", rs.getInt("plan_version"));
            data.put("destination", rs.getString("destination"));
            data.put("current", rs.getBoolean("is_current"));
            data.put("createdAt", rs.getTimestamp("created_at"));
            try {
                data.put("plan", objectMapper.readTree(rs.getString("plan_json")));
            } catch (Exception ignored) {
                data.put("plan", null);
            }
            return data;
        }, conversationId);
    }

    private boolean hasText(String value) {
        return value != null && !value.isBlank();
    }

    private String redact(String value) {
        if (!hasText(value)) {
            return value;
        }
        String redacted = BEARER_TOKEN.matcher(value).replaceAll("Bearer [REDACTED]");
        return SENSITIVE_VALUE.matcher(redacted).replaceAll("$1$2[REDACTED]");
    }
}
