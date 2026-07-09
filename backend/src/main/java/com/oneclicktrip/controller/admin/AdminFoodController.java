package com.oneclicktrip.controller.admin;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.oneclicktrip.common.ApiResponse;
import com.oneclicktrip.common.BusinessException;
import com.oneclicktrip.entity.Food;
import com.oneclicktrip.mapper.FoodMapper;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDateTime;

@RestController
@RequestMapping("/api/admin/foods")
public class AdminFoodController {

    private final FoodMapper foodMapper;

    public AdminFoodController(FoodMapper foodMapper) {
        this.foodMapper = foodMapper;
    }

    @GetMapping
    public ApiResponse<Page<Food>> list(
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "10") int size,
            @RequestParam(required = false) Long cityId,
            @RequestParam(required = false) String keyword) {

        LambdaQueryWrapper<Food> wrapper = Wrappers.<Food>lambdaQuery()
                .eq(Food::getDeleted, 0)
                .eq(cityId != null, Food::getCityId, cityId)
                .orderByAsc(Food::getSortOrder);

        if (keyword != null && !keyword.isBlank()) {
            wrapper.like(Food::getName, keyword);
        }

        Page<Food> result = foodMapper.selectPage(new Page<>(page, size), wrapper);
        return ApiResponse.ok(result);
    }

    @GetMapping("/{id}")
    public ApiResponse<Food> detail(@PathVariable Long id) {
        Food food = foodMapper.selectById(id);
        if (food == null) {
            throw new BusinessException("美食不存在");
        }
        return ApiResponse.ok(food);
    }

    @PostMapping
    public ApiResponse<Food> create(@RequestBody Food food) {
        food.setId(null);
        food.setDeleted(0);
        food.setCreateTime(LocalDateTime.now());
        food.setUpdateTime(LocalDateTime.now());
        if (food.getStatus() == null) food.setStatus(1);
        if (food.getSortOrder() == null) food.setSortOrder(0);
        foodMapper.insert(food);
        return ApiResponse.ok(food);
    }

    @PutMapping("/{id}")
    public ApiResponse<Food> update(@PathVariable Long id, @RequestBody Food food) {
        Food existing = foodMapper.selectById(id);
        if (existing == null) {
            throw new BusinessException("美食不存在");
        }
        food.setId(id);
        food.setUpdateTime(LocalDateTime.now());
        foodMapper.updateById(food);
        return ApiResponse.ok(foodMapper.selectById(id));
    }

    @DeleteMapping("/{id}")
    public ApiResponse<Void> delete(@PathVariable Long id) {
        Food food = foodMapper.selectById(id);
        if (food == null) {
            throw new BusinessException("美食不存在");
        }
        food.setDeleted(1);
        food.setUpdateTime(LocalDateTime.now());
        foodMapper.updateById(food);
        return ApiResponse.ok(null);
    }
}
