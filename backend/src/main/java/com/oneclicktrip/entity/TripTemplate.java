package com.oneclicktrip.entity;

import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@TableName("trip_template")
public class TripTemplate {
    private Long id;
    private Long cityId;
    private String title;
    private Integer days;
    private String budgetLevel;
    private String pace;
    private String summary;
    private String coverUrl;
    private Integer status;
    private Integer deleted;
    private LocalDateTime createTime;
    private LocalDateTime updateTime;
}

