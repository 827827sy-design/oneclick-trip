package com.oneclicktrip.controller.admin;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.oneclicktrip.common.ApiResponse;
import com.oneclicktrip.common.BusinessException;
import com.oneclicktrip.entity.Hotel;
import com.oneclicktrip.mapper.HotelMapper;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDateTime;

@RestController
@RequestMapping("/api/admin/hotels")
public class AdminHotelController {

    private final HotelMapper hotelMapper;

    public AdminHotelController(HotelMapper hotelMapper) {
        this.hotelMapper = hotelMapper;
    }

    @GetMapping
    public ApiResponse<Page<Hotel>> list(
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "10") int size,
            @RequestParam(required = false) Long cityId,
            @RequestParam(required = false) String keyword) {

        LambdaQueryWrapper<Hotel> wrapper = Wrappers.<Hotel>lambdaQuery()
                .eq(Hotel::getDeleted, 0)
                .eq(cityId != null, Hotel::getCityId, cityId)
                .orderByAsc(Hotel::getAvgPrice)
                .orderByDesc(Hotel::getRating);

        if (keyword != null && !keyword.isBlank()) {
            wrapper.like(Hotel::getName, keyword);
        }

        Page<Hotel> result = hotelMapper.selectPage(new Page<>(page, size), wrapper);
        return ApiResponse.ok(result);
    }

    @GetMapping("/{id}")
    public ApiResponse<Hotel> detail(@PathVariable Long id) {
        Hotel hotel = hotelMapper.selectById(id);
        if (hotel == null) {
            throw new BusinessException("酒店不存在");
        }
        return ApiResponse.ok(hotel);
    }

    @PostMapping
    public ApiResponse<Hotel> create(@RequestBody Hotel hotel) {
        hotel.setId(null);
        hotel.setDeleted(0);
        hotel.setCreateTime(LocalDateTime.now());
        hotel.setUpdateTime(LocalDateTime.now());
        if (hotel.getStatus() == null) hotel.setStatus(1);
        hotelMapper.insert(hotel);
        return ApiResponse.ok(hotel);
    }

    @PutMapping("/{id}")
    public ApiResponse<Hotel> update(@PathVariable Long id, @RequestBody Hotel hotel) {
        Hotel existing = hotelMapper.selectById(id);
        if (existing == null) {
            throw new BusinessException("酒店不存在");
        }
        hotel.setId(id);
        hotel.setUpdateTime(LocalDateTime.now());
        hotelMapper.updateById(hotel);
        return ApiResponse.ok(hotelMapper.selectById(id));
    }

    @DeleteMapping("/{id}")
    public ApiResponse<Void> delete(@PathVariable Long id) {
        Hotel hotel = hotelMapper.selectById(id);
        if (hotel == null) {
            throw new BusinessException("酒店不存在");
        }
        hotel.setDeleted(1);
        hotel.setUpdateTime(LocalDateTime.now());
        hotelMapper.updateById(hotel);
        return ApiResponse.ok(null);
    }
}
