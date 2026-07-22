package com.oneclicktrip.service;

import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.oneclicktrip.common.BusinessException;
import com.oneclicktrip.dto.AiChatResponse;
import com.oneclicktrip.dto.AiConversationDetailResponse;
import com.oneclicktrip.dto.AiConversationSummaryResponse;
import com.oneclicktrip.dto.AiMessageResponse;
import com.oneclicktrip.entity.AiConversation;
import com.oneclicktrip.entity.AiMessage;
import com.oneclicktrip.mapper.AiConversationMapper;
import com.oneclicktrip.mapper.AiMessageMapper;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;

@Service
public class AiConversationService {
    private final AiConversationMapper conversationMapper;
    private final AiMessageMapper messageMapper;
    private final ObjectMapper objectMapper;

    public AiConversationService(
            AiConversationMapper conversationMapper,
            AiMessageMapper messageMapper,
            ObjectMapper objectMapper
    ) {
        this.conversationMapper = conversationMapper;
        this.messageMapper = messageMapper;
        this.objectMapper = objectMapper;
    }

    public List<AiConversationSummaryResponse> list(Long userId) {
        return conversationMapper.selectList(Wrappers.<AiConversation>lambdaQuery()
                        .eq(AiConversation::getUserId, userId)
                        .eq(AiConversation::getDeleted, 0)
                        .orderByDesc(AiConversation::getUpdateTime))
                .stream().map(this::toSummary).toList();
    }

    public AiConversationSummaryResponse create(Long userId, String requestedTitle) {
        AiConversation conversation = new AiConversation();
        conversation.setConversationId(UUID.randomUUID().toString());
        conversation.setUserId(userId);
        conversation.setTitle(hasText(requestedTitle) ? limit(requestedTitle.trim(), 128) : "新对话");
        conversation.setStatus("ACTIVE");
        conversation.setMessageCount(0);
        conversation.setDeleted(0);
        conversationMapper.insert(conversation);
        return toSummary(conversationMapper.selectById(conversation.getId()));
    }

    public AiConversationDetailResponse detail(Long userId, String conversationId) {
        AiConversation conversation = requireOwned(userId, conversationId);
        List<AiMessageResponse> messages = messages(conversation.getId());
        return new AiConversationDetailResponse(toSummary(conversation), messages);
    }

    public AiConversationSummaryResponse rename(Long userId, String conversationId, String title) {
        AiConversation conversation = requireOwned(userId, conversationId);
        conversation.setTitle(limit(title.trim(), 128));
        conversationMapper.updateById(conversation);
        return toSummary(conversationMapper.selectById(conversation.getId()));
    }

    public void delete(Long userId, String conversationId) {
        AiConversation conversation = requireOwned(userId, conversationId);
        conversationMapper.deleteById(conversation.getId());
    }

    public AiConversation findOrCreate(Long userId, String conversationId, String firstMessage) {
        AiConversation existing = conversationMapper.selectOne(Wrappers.<AiConversation>lambdaQuery()
                .eq(AiConversation::getConversationId, conversationId)
                .last("LIMIT 1"));
        if (existing != null) {
            if (!userId.equals(existing.getUserId()) || Integer.valueOf(1).equals(existing.getDeleted())) {
                throw new BusinessException("无权访问该会话");
            }
            return existing;
        }

        AiConversation conversation = new AiConversation();
        conversation.setConversationId(conversationId);
        conversation.setUserId(userId);
        conversation.setTitle(titleFrom(firstMessage));
        conversation.setStatus("ACTIVE");
        conversation.setMessageCount(0);
        conversation.setDeleted(0);
        conversationMapper.insert(conversation);
        return conversationMapper.selectById(conversation.getId());
    }

    public void recordUserMessage(AiConversation conversation, String content) {
        if ((conversation.getMessageCount() == null || conversation.getMessageCount() == 0)
                && "新对话".equals(conversation.getTitle())) {
            conversation.setTitle(titleFrom(content));
        }
        insertMessage(conversation.getId(), "USER", content, "COMPLETED", null, null);
        refreshSummary(conversation, content);
    }

    public void recordAssistantMessage(AiConversation conversation, AiChatResponse response) {
        String stateJson = null;
        try {
            if (response.agentState() != null) {
                stateJson = objectMapper.writeValueAsString(response.agentState());
            }
        } catch (Exception ignored) {
            // 文本消息仍可正常保存，结构化展示数据缺失时前端会降级为普通回复。
        }
        insertMessage(
                conversation.getId(),
                "ASSISTANT",
                response.message(),
                response.status(),
                response.intent(),
                stateJson
        );
        refreshSummary(conversation, response.message());
    }

    public void recordFailure(AiConversation conversation, String message) {
        insertMessage(conversation.getId(), "ASSISTANT", message, "FAILED", null, null);
        refreshSummary(conversation, message);
    }

    private AiConversation requireOwned(Long userId, String conversationId) {
        AiConversation conversation = conversationMapper.selectOne(Wrappers.<AiConversation>lambdaQuery()
                .eq(AiConversation::getConversationId, conversationId)
                .eq(AiConversation::getUserId, userId)
                .eq(AiConversation::getDeleted, 0)
                .last("LIMIT 1"));
        if (conversation == null) {
            throw new BusinessException("会话不存在");
        }
        return conversation;
    }

    private void insertMessage(
            Long conversationId,
            String role,
            String content,
            String status,
            String intent,
            String stateJson
    ) {
        AiMessage message = new AiMessage();
        message.setAiConversationId(conversationId);
        message.setRole(role);
        message.setContent(content == null ? "" : content);
        message.setStatus(status);
        message.setIntent(intent);
        message.setAgentStateJson(stateJson);
        messageMapper.insert(message);
    }

    private void refreshSummary(AiConversation conversation, String preview) {
        Long count = messageMapper.selectCount(Wrappers.<AiMessage>lambdaQuery()
                .eq(AiMessage::getAiConversationId, conversation.getId()));
        conversation.setLastMessagePreview(limit(preview, 255));
        conversation.setMessageCount(count.intValue());
        conversation.setUpdateTime(LocalDateTime.now());
        conversationMapper.updateById(conversation);
    }

    private List<AiMessageResponse> messages(Long conversationId) {
        return messageMapper.selectList(Wrappers.<AiMessage>lambdaQuery()
                        .eq(AiMessage::getAiConversationId, conversationId)
                        .orderByAsc(AiMessage::getId))
                .stream().map(this::toMessage).toList();
    }

    private AiMessageResponse toMessage(AiMessage message) {
        JsonNode state = null;
        if (hasText(message.getAgentStateJson())) {
            try {
                state = objectMapper.readTree(message.getAgentStateJson());
            } catch (Exception ignored) {
                state = null;
            }
        }
        return new AiMessageResponse(
                message.getId(),
                message.getRole(),
                message.getContent(),
                message.getStatus(),
                message.getIntent(),
                state,
                message.getCreateTime()
        );
    }

    private AiConversationSummaryResponse toSummary(AiConversation conversation) {
        return new AiConversationSummaryResponse(
                conversation.getId(),
                conversation.getConversationId(),
                conversation.getTitle(),
                conversation.getStatus(),
                conversation.getLastMessagePreview(),
                conversation.getMessageCount(),
                conversation.getCreateTime(),
                conversation.getUpdateTime()
        );
    }

    private String titleFrom(String message) {
        if (!hasText(message)) {
            return "新对话";
        }
        String cleaned = message.trim().replaceAll("\\s+", " ");
        return cleaned.length() <= 24 ? cleaned : cleaned.substring(0, 24) + "...";
    }

    private boolean hasText(String value) {
        return value != null && !value.isBlank();
    }

    private String limit(String value, int maxLength) {
        if (value == null) {
            return "";
        }
        return value.length() <= maxLength ? value : value.substring(0, maxLength);
    }
}
