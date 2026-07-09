package com.oneclicktrip.service;

import com.oneclicktrip.common.BusinessException;
import com.oneclicktrip.dto.UpdateUserProfileRequest;
import com.oneclicktrip.dto.UserProfileResponse;
import com.oneclicktrip.entity.User;
import com.oneclicktrip.mapper.UserMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class UserProfileService {
    private final UserMapper userMapper;

    public UserProfileService(UserMapper userMapper) {
        this.userMapper = userMapper;
    }

    public UserProfileResponse getProfile(Long userId) {
        return toResponse(getActiveUser(userId));
    }

    @Transactional
    public UserProfileResponse updateProfile(Long userId, UpdateUserProfileRequest request) {
        User user = getActiveUser(userId);
        user.setNickname(request.nickname().trim());
        user.setAvatarUrl(request.avatarUrl().trim());
        userMapper.updateById(user);
        return toResponse(user);
    }

    private User getActiveUser(Long userId) {
        User user = userMapper.selectById(userId);
        if (user == null || user.getStatus() == null || user.getStatus() != 1) {
            throw new BusinessException("用户不存在或已停用");
        }
        return user;
    }

    private UserProfileResponse toResponse(User user) {
        return new UserProfileResponse(
                user.getId(),
                user.getUsername(),
                user.getNickname(),
                user.getAvatarUrl(),
                user.getRole()
        );
    }
}
