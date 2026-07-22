package com.oneclicktrip.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.oneclicktrip.dto.AiChatResponse;
import com.oneclicktrip.entity.AiConversation;
import com.oneclicktrip.entity.AiMessage;
import com.oneclicktrip.mapper.AiConversationMapper;
import com.oneclicktrip.mapper.AiMessageMapper;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class AiConversationService {
    private final AiConversationMapper conversationMapper;
    private final AiMessageMapper messageMapper;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public AiConversationService(AiConversationMapper conversationMapper, AiMessageMapper messageMapper) {
        this.conversationMapper = conversationMapper;
        this.messageMapper = messageMapper;
    }

    public AiConversation findOrCreate(Long userId, String conversationId, String firstMessage) {
        AiConversation conv = findByConversationId(conversationId);
        if (conv != null) {
            return conv;
        }
        conv = new AiConversation();
        conv.setConversationId(conversationId);
        conv.setUserId(userId);
        conv.setTitle(truncate(firstMessage, 128));
        conv.setStatus("ACTIVE");
        conv.setMessageCount(0);
        conversationMapper.insert(conv);
        return conv;
    }

    public void recordUserMessage(AiConversation conversation, String content) {
        AiMessage msg = new AiMessage();
        msg.setAiConversationId(conversation.getId());
        msg.setRole("USER");
        msg.setContent(content);
        msg.setStatus("COMPLETED");
        messageMapper.insert(msg);
        conversation.setMessageCount(conversation.getMessageCount() + 1);
        conversation.setLastMessagePreview(truncate(content, 255));
        conversationMapper.updateById(conversation);
    }

    public void recordAssistantMessage(AiConversation conversation, AiChatResponse response) {
        AiMessage msg = new AiMessage();
        msg.setAiConversationId(conversation.getId());
        msg.setRole("ASSISTANT");
        msg.setContent(response.message());
        msg.setStatus(response.status());
        msg.setIntent(response.intent());
        try {
            msg.setAgentStateJson(objectMapper.writeValueAsString(response.agentState()));
        } catch (JsonProcessingException ignored) {
        }
        messageMapper.insert(msg);
        conversation.setMessageCount(conversation.getMessageCount() + 1);
        conversation.setLastMessagePreview(truncate(response.message(), 255));
        conversationMapper.updateById(conversation);
    }

    public void recordFailure(AiConversation conversation, String errorMessage) {
        AiMessage msg = new AiMessage();
        msg.setAiConversationId(conversation.getId());
        msg.setRole("ASSISTANT");
        msg.setContent(errorMessage);
        msg.setStatus("FAILED");
        messageMapper.insert(msg);
        conversation.setMessageCount(conversation.getMessageCount() + 1);
        conversation.setLastMessagePreview(truncate(errorMessage, 255));
        conversationMapper.updateById(conversation);
    }

    public List<AiConversation> listByUser(Long userId) {
        LambdaQueryWrapper<AiConversation> q = new LambdaQueryWrapper<>();
        q.eq(AiConversation::getUserId, userId)
                .eq(AiConversation::getDeleted, 0)
                .orderByDesc(AiConversation::getUpdateTime);
        return conversationMapper.selectList(q);
    }

    public AiConversation create(Long userId, String title) {
        AiConversation conv = new AiConversation();
        conv.setConversationId(java.util.UUID.randomUUID().toString());
        conv.setUserId(userId);
        conv.setTitle(title != null && !title.isBlank() ? title : "新对话");
        conv.setStatus("ACTIVE");
        conv.setMessageCount(0);
        conversationMapper.insert(conv);
        return conv;
    }

    public AiConversation findById(String conversationId, Long userId) {
        LambdaQueryWrapper<AiConversation> q = new LambdaQueryWrapper<>();
        q.eq(AiConversation::getConversationId, conversationId)
                .eq(AiConversation::getUserId, userId)
                .eq(AiConversation::getDeleted, 0);
        return conversationMapper.selectOne(q);
    }

    public List<AiMessage> getMessages(Long conversationId) {
        LambdaQueryWrapper<AiMessage> q = new LambdaQueryWrapper<>();
        q.eq(AiMessage::getAiConversationId, conversationId)
                .orderByAsc(AiMessage::getId);
        return messageMapper.selectList(q);
    }

    public void rename(String conversationId, Long userId, String title) {
        LambdaUpdateWrapper<AiConversation> q = new LambdaUpdateWrapper<>();
        q.eq(AiConversation::getConversationId, conversationId)
                .eq(AiConversation::getUserId, userId)
                .set(AiConversation::getTitle, title);
        conversationMapper.update(q);
    }

    public void softDelete(String conversationId, Long userId) {
        LambdaUpdateWrapper<AiConversation> q = new LambdaUpdateWrapper<>();
        q.eq(AiConversation::getConversationId, conversationId)
                .eq(AiConversation::getUserId, userId);
        AiConversation conv = new AiConversation();
        conv.setDeleted(1);
        conversationMapper.update(conv, q);
    }

    private AiConversation findByConversationId(String conversationId) {
        LambdaQueryWrapper<AiConversation> q = new LambdaQueryWrapper<>();
        q.eq(AiConversation::getConversationId, conversationId)
                .eq(AiConversation::getDeleted, 0);
        return conversationMapper.selectOne(q);
    }

    private String truncate(String value, int maxLength) {
        if (value == null) return "";
        return value.length() <= maxLength ? value : value.substring(0, maxLength);
    }
}
