package com.oneclicktrip.entity;

import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@TableName("sys_user")
public class User {
    private Long id;
    private String username;
    private String passwordHash;
    private String nickname;
    private String mobile;
    private String avatarUrl;
    private String role;
    private Integer status;
    private Integer deleted;
    private LocalDateTime createTime;
    private LocalDateTime updateTime;
}
