package com.oneclicktrip.controller.admin;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.oneclicktrip.common.ApiResponse;
import com.oneclicktrip.common.BusinessException;
import com.oneclicktrip.service.AgentRunLogService;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDateTime;
import java.util.Map;

@RestController
@RequestMapping("/api/admin/agent-runs")
public class AdminAgentRunController {
    private final AgentRunLogService runLogService;

    public AdminAgentRunController(AgentRunLogService runLogService) {
        this.runLogService = runLogService;
    }

    @GetMapping
    public ApiResponse<Page<Map<String, Object>>> list(
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int size,
            @RequestParam(required = false) Long userId,
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) String intent,
            @RequestParam(required = false) String status,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) LocalDateTime startTime,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) LocalDateTime endTime
    ) {
        int safeSize = Math.max(1, Math.min(size, 100));
        return ApiResponse.ok(runLogService.list(Math.max(page, 1), safeSize, userId, keyword, intent, status, startTime, endTime));
    }

    @GetMapping("/stats")
    public ApiResponse<Map<String, Object>> stats() {
        return ApiResponse.ok(runLogService.stats());
    }

    @GetMapping("/{id}")
    public ApiResponse<Map<String, Object>> detail(@PathVariable Long id) {
        Map<String, Object> detail = runLogService.detail(id);
        if (detail == null) {
            throw new BusinessException("Agent 运行记录不存在");
        }
        return ApiResponse.ok(detail);
    }
}
