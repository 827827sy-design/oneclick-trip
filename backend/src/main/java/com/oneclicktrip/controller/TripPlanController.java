package com.oneclicktrip.controller;

import com.oneclicktrip.common.ApiResponse;
import com.oneclicktrip.dto.GenerateTripPlanRequest;
import com.oneclicktrip.dto.TripPlanResponse;
import com.oneclicktrip.service.TripPlanService;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/trip-plans")
public class TripPlanController {
    private final TripPlanService tripPlanService;

    public TripPlanController(TripPlanService tripPlanService) {
        this.tripPlanService = tripPlanService;
    }

    @PostMapping("/generate")
    public ApiResponse<TripPlanResponse> generate(@Valid @RequestBody GenerateTripPlanRequest request) {
        return ApiResponse.ok("已生成规则版行程", tripPlanService.generate(request));
    }

    @GetMapping("/{id}")
    public ApiResponse<TripPlanResponse> detail(@PathVariable Long id) {
        return ApiResponse.ok(tripPlanService.getPlan(id));
    }
}

