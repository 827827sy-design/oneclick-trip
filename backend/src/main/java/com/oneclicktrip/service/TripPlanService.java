package com.oneclicktrip.service;

import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.oneclicktrip.common.BusinessException;
import com.oneclicktrip.dto.GenerateTripPlanRequest;
import com.oneclicktrip.dto.TripPlanDayResponse;
import com.oneclicktrip.dto.TripPlanItemResponse;
import com.oneclicktrip.dto.TripPlanResponse;
import com.oneclicktrip.entity.*;
import com.oneclicktrip.mapper.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;

@Service
public class TripPlanService {
    private final CatalogService catalogService;
    private final TripPlanMapper tripPlanMapper;
    private final TripPlanDayMapper tripPlanDayMapper;
    private final TripPlanItemMapper tripPlanItemMapper;

    public TripPlanService(
            CatalogService catalogService,
            TripPlanMapper tripPlanMapper,
            TripPlanDayMapper tripPlanDayMapper,
            TripPlanItemMapper tripPlanItemMapper
    ) {
        this.catalogService = catalogService;
        this.tripPlanMapper = tripPlanMapper;
        this.tripPlanDayMapper = tripPlanDayMapper;
        this.tripPlanItemMapper = tripPlanItemMapper;
    }

    @Transactional
    public TripPlanResponse generate(GenerateTripPlanRequest request) {
        City city = catalogService.getCity(request.cityId());
        List<ScenicSpot> spots = catalogService.listSpots(request.cityId());
        List<Food> foods = catalogService.listFoods(request.cityId());
        List<Hotel> hotels = catalogService.listHotels(request.cityId());

        if (spots.isEmpty()) {
            throw new BusinessException("该城市还没有景点数据，无法生成行程");
        }
        if (foods.isEmpty()) {
            throw new BusinessException("该城市还没有美食数据，无法生成行程");
        }

        int days = request.days() == null ? 3 : request.days();
        int peopleCount = request.peopleCount() == null ? 1 : request.peopleCount();
        String budgetLevel = defaultText(request.budgetLevel(), "MEDIUM");
        String pace = defaultText(request.pace(), "RELAXED");
        Hotel hotel = chooseHotel(hotels, budgetLevel);
        String interests = request.interests() == null || request.interests().isEmpty()
                ? "轻松,美食"
                : String.join(",", request.interests());

        TripPlan plan = new TripPlan();
        plan.setCityId(city.getId());
        plan.setDepartureCity(defaultText(request.departureCity(), "本地"));
        plan.setTitle(city.getName() + days + "日" + paceText(pace) + "游");
        plan.setDays(days);
        plan.setPeopleCount(peopleCount);
        plan.setStartDate(request.startDate());
        plan.setBudgetLevel(budgetLevel);
        plan.setPace(pace);
        plan.setInterests(interests);
        plan.setSummary("基于数据库景点、美食、住宿资料生成的规则版行程；AI 助手接入后可进一步优化路线。");
        plan.setSourceType("RULE");
        plan.setTotalBudget(BigDecimal.ZERO);
        tripPlanMapper.insert(plan);

        BigDecimal total = BigDecimal.ZERO;
        for (int dayNo = 1; dayNo <= days; dayNo++) {
            TripPlanDay day = new TripPlanDay();
            day.setPlanId(plan.getId());
            day.setDayNo(dayNo);
            day.setTitle("Day " + dayNo + " " + dayTitle(dayNo, city.getName()));
            day.setSummary(dayNo == 1 ? "抵达后安排市区轻松路线。" : "控制景点数量，穿插当地美食。");
            tripPlanDayMapper.insert(day);

            List<TripPlanItem> items = buildDayItems(day.getId(), dayNo, peopleCount, spots, foods, hotel);
            for (TripPlanItem item : items) {
                tripPlanItemMapper.insert(item);
                total = total.add(item.getCost() == null ? BigDecimal.ZERO : item.getCost());
            }
        }

        plan.setTotalBudget(total.setScale(2, RoundingMode.HALF_UP));
        tripPlanMapper.updateById(plan);
        return getPlan(plan.getId());
    }

    public TripPlanResponse getPlan(Long id) {
        TripPlan plan = tripPlanMapper.selectById(id);
        if (plan == null) {
            throw new BusinessException("行程不存在");
        }
        City city = catalogService.getCity(plan.getCityId());
        List<TripPlanDay> days = tripPlanDayMapper.selectList(Wrappers.<TripPlanDay>lambdaQuery()
                .eq(TripPlanDay::getPlanId, id)
                .orderByAsc(TripPlanDay::getDayNo));

        List<TripPlanDayResponse> dayResponses = days.stream()
                .map(day -> new TripPlanDayResponse(
                        day.getId(),
                        day.getDayNo(),
                        day.getTitle(),
                        day.getSummary(),
                        tripPlanItemMapper.selectList(Wrappers.<TripPlanItem>lambdaQuery()
                                        .eq(TripPlanItem::getPlanDayId, day.getId())
                                        .orderByAsc(TripPlanItem::getSortOrder))
                                .stream()
                                .map(this::toItemResponse)
                                .collect(Collectors.toList())
                ))
                .collect(Collectors.toList());

        return new TripPlanResponse(
                plan.getId(),
                plan.getCityId(),
                city.getName(),
                plan.getDepartureCity(),
                plan.getTitle(),
                plan.getDays(),
                plan.getPeopleCount(),
                plan.getStartDate(),
                plan.getBudgetLevel(),
                plan.getPace(),
                plan.getInterests(),
                plan.getTotalBudget(),
                plan.getSummary(),
                plan.getSourceType(),
                dayResponses
        );
    }

    private List<TripPlanItem> buildDayItems(
            Long dayId,
            int dayNo,
            int peopleCount,
            List<ScenicSpot> spots,
            List<Food> foods,
            Hotel hotel
    ) {
        List<TripPlanItem> items = new ArrayList<>();
        ScenicSpot firstSpot = spots.get((dayNo - 1) % spots.size());
        ScenicSpot secondSpot = spots.get(dayNo % spots.size());
        Food lunch = foods.get((dayNo - 1) % foods.size());
        Food dinner = foods.get(dayNo % foods.size());

        items.add(item(dayId, "TRANSPORT", "城市交通", "根据当天景点距离选择地铁、打车或公交。", null, "09:00", "09:30", money(25, peopleCount), 1));
        items.add(item(dayId, "SPOT", firstSpot.getName(), firstSpot.getSummary(), firstSpot.getAddress(), "09:30", "12:00", firstSpot.getTicketPrice().multiply(BigDecimal.valueOf(peopleCount)), 2));
        items.add(item(dayId, "FOOD", lunch.getName(), lunch.getSummary(), lunch.getRecommendedArea(), "12:15", "13:15", lunch.getAvgPrice().multiply(BigDecimal.valueOf(peopleCount)), 3));
        items.add(item(dayId, "SPOT", secondSpot.getName(), secondSpot.getSummary(), secondSpot.getAddress(), "14:00", "17:00", secondSpot.getTicketPrice().multiply(BigDecimal.valueOf(peopleCount)), 4));
        items.add(item(dayId, "FOOD", dinner.getName(), dinner.getSummary(), dinner.getRecommendedArea(), "18:00", "19:30", dinner.getAvgPrice().multiply(BigDecimal.valueOf(peopleCount)), 5));
        if (hotel != null) {
            items.add(item(dayId, "HOTEL", hotel.getName(), hotel.getSummary(), hotel.getArea(), "20:00", "次日", hotel.getAvgPrice(), 6));
        }
        return items;
    }

    private TripPlanItem item(Long dayId, String type, String title, String description, String address,
                              String startTime, String endTime, BigDecimal cost, int sortOrder) {
        TripPlanItem item = new TripPlanItem();
        item.setPlanDayId(dayId);
        item.setItemType(type);
        item.setTitle(title);
        item.setDescription(description);
        item.setAddress(address);
        item.setStartTime(startTime);
        item.setEndTime(endTime);
        item.setCost(cost == null ? BigDecimal.ZERO : cost);
        item.setSortOrder(sortOrder);
        return item;
    }

    private Hotel chooseHotel(List<Hotel> hotels, String budgetLevel) {
        if (hotels.isEmpty()) {
            return null;
        }
        return hotels.stream()
                .filter(hotel -> budgetLevel.equalsIgnoreCase(hotel.getPriceLevel()))
                .findFirst()
                .orElseGet(() -> hotels.stream().min(Comparator.comparing(Hotel::getAvgPrice)).orElse(hotels.get(0)));
    }

    private TripPlanItemResponse toItemResponse(TripPlanItem item) {
        return new TripPlanItemResponse(
                item.getId(),
                item.getItemType(),
                item.getTitle(),
                item.getDescription(),
                item.getAddress(),
                item.getStartTime(),
                item.getEndTime(),
                item.getCost(),
                item.getSortOrder()
        );
    }

    private BigDecimal money(int unit, int peopleCount) {
        return BigDecimal.valueOf((long) unit * peopleCount);
    }

    private String defaultText(String value, String fallback) {
        return value == null || value.isBlank() ? fallback : value;
    }

    private String paceText(String pace) {
        return "COMPACT".equalsIgnoreCase(pace) ? "紧凑" : "轻松";
    }

    private String dayTitle(int dayNo, String cityName) {
        if (dayNo == 1) {
            return cityName + "初印象";
        }
        if (dayNo == 2) {
            return "经典景点与美食";
        }
        return "轻松补充路线";
    }
}

