package com.oneclicktrip.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import java.time.LocalDate;
import java.util.List;

public record GenerateTripPlanRequest(
        String departureCity,
        @NotNull Long cityId,
        @Min(1) @Max(10) Integer days,
        @Min(1) @Max(20) Integer peopleCount,
        LocalDate startDate,
        String budgetLevel,
        String pace,
        String hotelPreference,
        List<String> interests
) {
}

