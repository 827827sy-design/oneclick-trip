package com.oneclicktrip.entity;

import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;

@Data
@TableName("trip_plan_item")
public class TripPlanItem {
    private Long id;
    private Long planDayId;
    private String itemType;
    private String title;
    private String description;
    private String address;
    private String startTime;
    private String endTime;
    private BigDecimal cost;
    private Integer sortOrder;
    private Integer deleted;
    private LocalDateTime createTime;
    private LocalDateTime updateTime;
}

