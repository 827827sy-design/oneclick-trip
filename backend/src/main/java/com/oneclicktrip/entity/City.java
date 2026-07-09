package com.oneclicktrip.entity;

import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@TableName("city")
public class City {
    private Long id;
    private String name;
    private String province;
    private String summary;
    private String bestSeason;
    private String imageUrl;
    private Integer status;
    private Integer sortOrder;
    private Integer deleted;
    private LocalDateTime createTime;
    private LocalDateTime updateTime;
}

