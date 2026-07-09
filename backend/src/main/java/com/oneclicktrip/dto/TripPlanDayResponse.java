package com.oneclicktrip.dto;

import java.util.List;

public record TripPlanDayResponse(
        Long id,
        Integer dayNo,
        String title,
        String summary,
        List<TripPlanItemResponse> items
) {
}

