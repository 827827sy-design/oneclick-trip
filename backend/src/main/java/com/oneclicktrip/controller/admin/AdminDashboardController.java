package com.oneclicktrip.controller.admin;

import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.oneclicktrip.common.ApiResponse;
import com.oneclicktrip.entity.*;
import com.oneclicktrip.mapper.*;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api/admin")
public class AdminDashboardController {

    private final UserMapper userMapper;
    private final CityMapper cityMapper;
    private final ScenicSpotMapper spotMapper;
    private final TripPlanMapper tripPlanMapper;

    public AdminDashboardController(UserMapper userMapper, CityMapper cityMapper,
                                    ScenicSpotMapper spotMapper, TripPlanMapper tripPlanMapper) {
        this.userMapper = userMapper;
        this.cityMapper = cityMapper;
        this.spotMapper = spotMapper;
        this.tripPlanMapper = tripPlanMapper;
    }

    @GetMapping("/dashboard")
    public ApiResponse<Map<String, Object>> dashboard() {
        long totalUsers = userMapper.selectCount(Wrappers.<User>lambdaQuery().eq(User::getDeleted, 0));
        long totalCities = cityMapper.selectCount(Wrappers.<City>lambdaQuery().eq(City::getDeleted, 0));
        long totalSpots = spotMapper.selectCount(Wrappers.<ScenicSpot>lambdaQuery().eq(ScenicSpot::getDeleted, 0));
        long totalPlans = tripPlanMapper.selectCount(Wrappers.<TripPlan>lambdaQuery().eq(TripPlan::getDeleted, 0));

        Map<String, Object> data = Map.of(
                "totalUsers", totalUsers,
                "totalCities", totalCities,
                "totalSpots", totalSpots,
                "totalPlans", totalPlans
        );
        return ApiResponse.ok(data);
    }
}
