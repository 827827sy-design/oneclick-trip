package com.oneclicktrip.entity;

import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@TableName("ai_call_log")
public class AiCallLog {
    private Long id;
    private Long userId;
    private String requestText;
    private String responseText;
    private String status;
    private LocalDateTime createTime;
}

