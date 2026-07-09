package com.oneclicktrip.dto;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;

public record TripPlanResponse(
        Long id,
        Long cityId,
        String cityName,
        String departureCity,
        String title,
        Integer days,
        Integer peopleCount,
        LocalDate startDate,
        String budgetLevel,
        String pace,
        String interests,
        BigDecimal totalBudget,
        String summary,
        String sourceType,
        List<TripPlanDayResponse> dayPlans
) {
}

