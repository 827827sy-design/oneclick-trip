package com.oneclicktrip.controller;

import com.oneclicktrip.common.ApiResponse;
import com.oneclicktrip.dto.UpdateUserProfileRequest;
import com.oneclicktrip.dto.UserProfileResponse;
import com.oneclicktrip.security.JwtUser;
import com.oneclicktrip.service.UserProfileService;
import jakarta.validation.Valid;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/users")
public class UserController {
    private final UserProfileService userProfileService;

    public UserController(UserProfileService userProfileService) {
        this.userProfileService = userProfileService;
    }

    @GetMapping("/me")
    public ApiResponse<UserProfileResponse> me(@AuthenticationPrincipal JwtUser user) {
        return ApiResponse.ok(userProfileService.getProfile(user.userId()));
    }

    @PutMapping("/me")
    public ApiResponse<UserProfileResponse> updateMe(
            @AuthenticationPrincipal JwtUser user,
            @Valid @RequestBody UpdateUserProfileRequest request
    ) {
        return ApiResponse.ok("个人资料已更新", userProfileService.updateProfile(user.userId(), request));
    }
}
