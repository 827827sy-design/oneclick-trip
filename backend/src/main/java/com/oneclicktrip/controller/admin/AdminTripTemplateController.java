package com.oneclicktrip.controller.admin;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.oneclicktrip.common.ApiResponse;
import com.oneclicktrip.common.BusinessException;
import com.oneclicktrip.entity.TripTemplate;
import com.oneclicktrip.mapper.TripTemplateMapper;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDateTime;

@RestController
@RequestMapping("/api/admin/templates")
public class AdminTripTemplateController {

    private final TripTemplateMapper templateMapper;

    public AdminTripTemplateController(TripTemplateMapper templateMapper) {
        this.templateMapper = templateMapper;
    }

    @GetMapping
    public ApiResponse<Page<TripTemplate>> list(
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "10") int size,
            @RequestParam(required = false) Long cityId) {

        LambdaQueryWrapper<TripTemplate> wrapper = Wrappers.<TripTemplate>lambdaQuery()
                .eq(TripTemplate::getDeleted, 0)
                .eq(cityId != null, TripTemplate::getCityId, cityId)
                .orderByAsc(TripTemplate::getDays)
                .orderByDesc(TripTemplate::getId);

        Page<TripTemplate> result = templateMapper.selectPage(new Page<>(page, size), wrapper);
        return ApiResponse.ok(result);
    }

    @GetMapping("/{id}")
    public ApiResponse<TripTemplate> detail(@PathVariable Long id) {
        TripTemplate template = templateMapper.selectById(id);
        if (template == null) {
            throw new BusinessException("模板不存在");
        }
        return ApiResponse.ok(template);
    }

    @PostMapping
    public ApiResponse<TripTemplate> create(@RequestBody TripTemplate template) {
        template.setId(null);
        template.setDeleted(0);
        template.setCreateTime(LocalDateTime.now());
        template.setUpdateTime(LocalDateTime.now());
        if (template.getStatus() == null) template.setStatus(1);
        templateMapper.insert(template);
        return ApiResponse.ok(template);
    }

    @PutMapping("/{id}")
    public ApiResponse<TripTemplate> update(@PathVariable Long id, @RequestBody TripTemplate template) {
        TripTemplate existing = templateMapper.selectById(id);
        if (existing == null) {
            throw new BusinessException("模板不存在");
        }
        template.setId(id);
        template.setUpdateTime(LocalDateTime.now());
        templateMapper.updateById(template);
        return ApiResponse.ok(templateMapper.selectById(id));
    }

    @DeleteMapping("/{id}")
    public ApiResponse<Void> delete(@PathVariable Long id) {
        TripTemplate template = templateMapper.selectById(id);
        if (template == null) {
            throw new BusinessException("模板不存在");
        }
        template.setDeleted(1);
        template.setUpdateTime(LocalDateTime.now());
        templateMapper.updateById(template);
        return ApiResponse.ok(null);
    }
}
