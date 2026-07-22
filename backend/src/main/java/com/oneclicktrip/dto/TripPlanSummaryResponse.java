package com.oneclicktrip.dto;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;

public record TripPlanSummaryResponse(
        String key,
        String planType,
        Long recordId,
        String planId,
        String conversationId,
        Integer version,
        String destination,
        String title,
        Integer days,
        Integer peopleCount,
        LocalDate startDate,
        BigDecimal totalBudget,
        String currency,
        String sourceType,
        String summary,
        LocalDateTime createTime
) {
}
