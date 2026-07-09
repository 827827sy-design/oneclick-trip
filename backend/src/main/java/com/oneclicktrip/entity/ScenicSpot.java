package com.oneclicktrip.entity;

import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;

@Data
@TableName("scenic_spot")
public class ScenicSpot {
    private Long id;
    private Long cityId;
    private String name;
    private String address;
    private String summary;
    private BigDecimal ticketPrice;
    private String openTime;
    private BigDecimal playHours;
    private BigDecimal rating;
    private String tags;
    private String imageUrl;
    private Integer sortOrder;
    private Integer status;
    private Integer deleted;
    private LocalDateTime createTime;
    private LocalDateTime updateTime;
}

