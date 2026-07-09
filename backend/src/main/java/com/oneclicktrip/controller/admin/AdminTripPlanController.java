package com.oneclicktrip.controller.admin;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.oneclicktrip.common.ApiResponse;
import com.oneclicktrip.common.BusinessException;
import com.oneclicktrip.entity.*;
import com.oneclicktrip.mapper.*;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDateTime;
import java.util.*;
import java.util.stream.Collectors;

@RestController
@RequestMapping("/api/admin/trip-plans")
public class AdminTripPlanController {

    private final TripPlanMapper tripPlanMapper;
    private final TripPlanDayMapper dayMapper;
    private final TripPlanItemMapper itemMapper;
    private final UserMapper userMapper;
    private final CityMapper cityMapper;

    public AdminTripPlanController(TripPlanMapper tripPlanMapper,
                                   TripPlanDayMapper dayMapper,
                                   TripPlanItemMapper itemMapper,
                                   UserMapper userMapper,
                                   CityMapper cityMapper) {
        this.tripPlanMapper = tripPlanMapper;
        this.dayMapper = dayMapper;
        this.itemMapper = itemMapper;
        this.userMapper = userMapper;
        this.cityMapper = cityMapper;
    }

    @GetMapping
    public ApiResponse<Page<Map<String, Object>>> list(
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "10") int size,
            @RequestParam(required = false) String keyword) {

        LambdaQueryWrapper<TripPlan> wrapper = Wrappers.<TripPlan>lambdaQuery()
                .eq(TripPlan::getDeleted, 0)
                .orderByDesc(TripPlan::getId);

        Page<TripPlan> planPage = tripPlanMapper.selectPage(new Page<>(page, size), wrapper);

        // 批量获取用户名和城市名
        Set<Long> userIds = planPage.getRecords().stream().map(TripPlan::getUserId).filter(Objects::nonNull).collect(Collectors.toSet());
        Set<Long> cityIds = planPage.getRecords().stream().map(TripPlan::getCityId).filter(Objects::nonNull).collect(Collectors.toSet());

        Map<Long, String> userNames = new HashMap<>();
        Map<Long, String> cityNames = new HashMap<>();

        if (!userIds.isEmpty()) {
            userNames = userMapper.selectBatchIds(userIds).stream()
                    .collect(Collectors.toMap(User::getId, u -> u.getNickname() != null ? u.getNickname() : u.getUsername()));
        }
        if (!cityIds.isEmpty()) {
            cityNames = cityMapper.selectBatchIds(cityIds).stream()
                    .collect(Collectors.toMap(City::getId, City::getName));
        }

        // 转换结果，附加用户名和城市名
        List<Map<String, Object>> records = planPage.getRecords().stream().map(plan -> {
            Map<String, Object> map = new LinkedHashMap<>();
            map.put("id", plan.getId());
            map.put("userId", plan.getUserId());
            map.put("nickname", userNames.getOrDefault(plan.getUserId(), "-"));
            map.put("cityId", plan.getCityId());
            map.put("cityName", cityNames.getOrDefault(plan.getCityId(), "-"));
            map.put("departureCity", plan.getDepartureCity());
            map.put("title", plan.getTitle());
            map.put("days", plan.getDays());
            map.put("peopleCount", plan.getPeopleCount());
            map.put("budgetLevel", plan.getBudgetLevel());
            map.put("pace", plan.getPace());
            map.put("interests", plan.getInterests());
            map.put("totalBudget", plan.getTotalBudget());
            map.put("summary", plan.getSummary());
            map.put("sourceType", plan.getSourceType());
            map.put("createTime", plan.getCreateTime());
            return map;
        }).collect(Collectors.toList());

        // 关键词过滤（在内存中）
        if (keyword != null && !keyword.isBlank()) {
            records = records.stream()
                    .filter(r -> {
                        String title = (String) r.getOrDefault("title", "");
                        String nickname = (String) r.getOrDefault("nickname", "");
                        return title.contains(keyword) || nickname.contains(keyword);
                    })
                    .collect(Collectors.toList());
        }

        Page<Map<String, Object>> result = new Page<>(page, size, planPage.getTotal());
        result.setRecords(records);
        return ApiResponse.ok(result);
    }

    @GetMapping("/{id}")
    public ApiResponse<Map<String, Object>> detail(@PathVariable Long id) {
        TripPlan plan = tripPlanMapper.selectById(id);
        if (plan == null) {
            throw new BusinessException("行程不存在");
        }

        // 获取用户信息
        User user = userMapper.selectById(plan.getUserId());
        City city = cityMapper.selectById(plan.getCityId());

        // 获取行程天
        List<TripPlanDay> days = dayMapper.selectList(
                Wrappers.<TripPlanDay>lambdaQuery()
                        .eq(TripPlanDay::getPlanId, id)
                        .orderByAsc(TripPlanDay::getDayNo));

        // 获取每天的项目
        List<Map<String, Object>> dayPlans = new ArrayList<>();
        for (TripPlanDay day : days) {
            List<TripPlanItem> items = itemMapper.selectList(
                    Wrappers.<TripPlanItem>lambdaQuery()
                            .eq(TripPlanItem::getDayId, day.getId())
                            .orderByAsc(TripPlanItem::getSortOrder));

            Map<String, Object> dayMap = new LinkedHashMap<>();
            dayMap.put("dayNo", day.getDayNo());
            dayMap.put("title", day.getTitle());
            dayMap.put("items", items);
            dayPlans.add(dayMap);
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("id", plan.getId());
        result.put("userId", plan.getUserId());
        result.put("nickname", user != null ? (user.getNickname() != null ? user.getNickname() : user.getUsername()) : "-");
        result.put("cityId", plan.getCityId());
        result.put("cityName", city != null ? city.getName() : "-");
        result.put("departureCity", plan.getDepartureCity());
        result.put("title", plan.getTitle());
        result.put("days", plan.getDays());
        result.put("peopleCount", plan.getPeopleCount());
        result.put("budgetLevel", plan.getBudgetLevel());
        result.put("pace", plan.getPace());
        result.put("interests", plan.getInterests());
        result.put("totalBudget", plan.getTotalBudget());
        result.put("summary", plan.getSummary());
        result.put("sourceType", plan.getSourceType());
        result.put("createTime", plan.getCreateTime());
        result.put("dayPlans", dayPlans);
        return ApiResponse.ok(result);
    }

    @DeleteMapping("/{id}")
    public ApiResponse<Void> delete(@PathVariable Long id) {
        TripPlan plan = tripPlanMapper.selectById(id);
        if (plan == null) {
            throw new BusinessException("行程不存在");
        }
        plan.setDeleted(1);
        plan.setUpdateTime(LocalDateTime.now());
        tripPlanMapper.updateById(plan);
        return ApiResponse.ok(null);
    }
}
