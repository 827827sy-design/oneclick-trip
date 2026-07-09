package com.oneclicktrip.entity;

import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;

@Data
@TableName("trip_plan")
public class TripPlan {
    private Long id;
    private Long userId;
    private Long cityId;
    private String departureCity;
    private String title;
    private Integer days;
    private Integer peopleCount;
    private LocalDate startDate;
    private String budgetLevel;
    private String pace;
    private String interests;
    private BigDecimal totalBudget;
    private String summary;
    private String sourceType;
    private Integer deleted;
    private LocalDateTime createTime;
    private LocalDateTime updateTime;
}

