package com.oneclicktrip.dto;

import java.math.BigDecimal;

public record TripPlanItemResponse(
        Long id,
        String itemType,
        String title,
        String description,
        String address,
        String startTime,
        String endTime,
        BigDecimal cost,
        Integer sortOrder
) {
}

