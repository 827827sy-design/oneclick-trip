package com.oneclicktrip.entity;

import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@TableName("trip_plan_day")
public class TripPlanDay {
    private Long id;
    private Long planId;
    private Integer dayNo;
    private String title;
    private String summary;
    private Integer deleted;
    private LocalDateTime createTime;
    private LocalDateTime updateTime;
}

