package com.oneclicktrip.entity;

import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;

@Data
@TableName("hotel")
public class Hotel {
    private Long id;
    private Long cityId;
    private String name;
    private String area;
    private String summary;
    private String priceLevel;
    private BigDecimal avgPrice;
    private BigDecimal rating;
    private String imageUrl;
    private Integer status;
    private Integer deleted;
    private LocalDateTime createTime;
    private LocalDateTime updateTime;
}

