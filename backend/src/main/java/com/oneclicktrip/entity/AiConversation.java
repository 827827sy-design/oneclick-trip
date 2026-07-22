package com.oneclicktrip.entity;

import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@TableName("ai_conversation")
public class AiConversation {
    private Long id;
    private String conversationId;
    private Long userId;
    private String title;
    private String status;
    private String lastMessagePreview;
    private Integer messageCount;
    private Integer deleted;
    private LocalDateTime createTime;
    private LocalDateTime updateTime;
}
