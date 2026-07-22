package com.oneclicktrip.entity;

import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@TableName("ai_message")
public class AiMessage {
    private Long id;
    private Long aiConversationId;
    private String role;
    private String content;
    private String status;
    private String intent;
    private String agentStateJson;
    private LocalDateTime createTime;
}
