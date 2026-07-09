package com.oneclicktrip.entity;

import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;

@Data
@TableName("food")
public class Food {
    private Long id;
    private Long cityId;
    private String name;
    private String category;
    private String summary;
    private String recommendedArea;
    private BigDecimal avgPrice;
    private String imageUrl;
    private Integer sortOrder;
    private Integer status;
    private Integer deleted;
    private LocalDateTime createTime;
    private LocalDateTime updateTime;
}

