package com.oneclicktrip.controller.admin;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.oneclicktrip.common.ApiResponse;
import com.oneclicktrip.common.BusinessException;
import com.oneclicktrip.entity.ScenicSpot;
import com.oneclicktrip.mapper.ScenicSpotMapper;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDateTime;

@RestController
@RequestMapping("/api/admin/spots")
public class AdminSpotController {

    private final ScenicSpotMapper spotMapper;

    public AdminSpotController(ScenicSpotMapper spotMapper) {
        this.spotMapper = spotMapper;
    }

    @GetMapping
    public ApiResponse<Page<ScenicSpot>> list(
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "10") int size,
            @RequestParam(required = false) Long cityId,
            @RequestParam(required = false) String keyword) {

        LambdaQueryWrapper<ScenicSpot> wrapper = Wrappers.<ScenicSpot>lambdaQuery()
                .eq(ScenicSpot::getDeleted, 0)
                .eq(cityId != null, ScenicSpot::getCityId, cityId)
                .orderByAsc(ScenicSpot::getSortOrder)
                .orderByDesc(ScenicSpot::getRating);

        if (keyword != null && !keyword.isBlank()) {
            wrapper.like(ScenicSpot::getName, keyword);
        }

        Page<ScenicSpot> result = spotMapper.selectPage(new Page<>(page, size), wrapper);
        return ApiResponse.ok(result);
    }

    @GetMapping("/{id}")
    public ApiResponse<ScenicSpot> detail(@PathVariable Long id) {
        ScenicSpot spot = spotMapper.selectById(id);
        if (spot == null) {
            throw new BusinessException("景点不存在");
        }
        return ApiResponse.ok(spot);
    }

    @PostMapping
    public ApiResponse<ScenicSpot> create(@RequestBody ScenicSpot spot) {
        spot.setId(null);
        spot.setDeleted(0);
        spot.setCreateTime(LocalDateTime.now());
        spot.setUpdateTime(LocalDateTime.now());
        if (spot.getStatus() == null) spot.setStatus(1);
        if (spot.getSortOrder() == null) spot.setSortOrder(0);
        spotMapper.insert(spot);
        return ApiResponse.ok(spot);
    }

    @PutMapping("/{id}")
    public ApiResponse<ScenicSpot> update(@PathVariable Long id, @RequestBody ScenicSpot spot) {
        ScenicSpot existing = spotMapper.selectById(id);
        if (existing == null) {
            throw new BusinessException("景点不存在");
        }
        spot.setId(id);
        spot.setUpdateTime(LocalDateTime.now());
        spotMapper.updateById(spot);
        return ApiResponse.ok(spotMapper.selectById(id));
    }

    @DeleteMapping("/{id}")
    public ApiResponse<Void> delete(@PathVariable Long id) {
        ScenicSpot spot = spotMapper.selectById(id);
        if (spot == null) {
            throw new BusinessException("景点不存在");
        }
        spot.setDeleted(1);
        spot.setUpdateTime(LocalDateTime.now());
        spotMapper.updateById(spot);
        return ApiResponse.ok(null);
    }
}
