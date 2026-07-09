package com.oneclicktrip.controller.admin;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.oneclicktrip.common.ApiResponse;
import com.oneclicktrip.common.BusinessException;
import com.oneclicktrip.entity.City;
import com.oneclicktrip.mapper.CityMapper;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDateTime;

@RestController
@RequestMapping("/api/admin/cities")
public class AdminCityController {

    private final CityMapper cityMapper;

    public AdminCityController(CityMapper cityMapper) {
        this.cityMapper = cityMapper;
    }

    @GetMapping
    public ApiResponse<Page<City>> list(
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "10") int size,
            @RequestParam(required = false) String keyword) {

        LambdaQueryWrapper<City> wrapper = Wrappers.<City>lambdaQuery()
                .eq(City::getDeleted, 0)
                .orderByAsc(City::getSortOrder)
                .orderByDesc(City::getId);

        if (keyword != null && !keyword.isBlank()) {
            wrapper.like(City::getName, keyword);
        }

        Page<City> result = cityMapper.selectPage(new Page<>(page, size), wrapper);
        return ApiResponse.ok(result);
    }

    @GetMapping("/{id}")
    public ApiResponse<City> detail(@PathVariable Long id) {
        City city = cityMapper.selectById(id);
        if (city == null) {
            throw new BusinessException("城市不存在");
        }
        return ApiResponse.ok(city);
    }

    @PostMapping
    public ApiResponse<City> create(@RequestBody City city) {
        city.setId(null);
        city.setDeleted(0);
        city.setCreateTime(LocalDateTime.now());
        city.setUpdateTime(LocalDateTime.now());
        if (city.getStatus() == null) city.setStatus(1);
        if (city.getSortOrder() == null) city.setSortOrder(0);
        cityMapper.insert(city);
        return ApiResponse.ok(city);
    }

    @PutMapping("/{id}")
    public ApiResponse<City> update(@PathVariable Long id, @RequestBody City city) {
        City existing = cityMapper.selectById(id);
        if (existing == null) {
            throw new BusinessException("城市不存在");
        }
        city.setId(id);
        city.setUpdateTime(LocalDateTime.now());
        cityMapper.updateById(city);
        return ApiResponse.ok(cityMapper.selectById(id));
    }

    @DeleteMapping("/{id}")
    public ApiResponse<Void> delete(@PathVariable Long id) {
        City city = cityMapper.selectById(id);
        if (city == null) {
            throw new BusinessException("城市不存在");
        }
        city.setDeleted(1);
        city.setUpdateTime(LocalDateTime.now());
        cityMapper.updateById(city);
        return ApiResponse.ok(null);
    }
}
