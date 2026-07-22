package com.oneclicktrip.service;

import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.oneclicktrip.common.BusinessException;
import com.oneclicktrip.dto.AiTripPlanDetailResponse;
import com.oneclicktrip.dto.GenerateTripPlanRequest;
import com.oneclicktrip.dto.TripPlanDayResponse;
import com.oneclicktrip.dto.TripPlanItemResponse;
import com.oneclicktrip.dto.TripPlanResponse;
import com.oneclicktrip.dto.TripPlanSummaryResponse;
import com.oneclicktrip.entity.*;
import com.oneclicktrip.mapper.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Timestamp;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;

@Service
public class TripPlanService {
    private static final Logger log = LoggerFactory.getLogger(TripPlanService.class);

    private final CatalogService catalogService;
    private final TripPlanMapper tripPlanMapper;
    private final TripPlanDayMapper tripPlanDayMapper;
    private final TripPlanItemMapper tripPlanItemMapper;
    private final JdbcTemplate jdbcTemplate;
    private final ObjectMapper objectMapper;

    public TripPlanService(
            CatalogService catalogService,
            TripPlanMapper tripPlanMapper,
            TripPlanDayMapper tripPlanDayMapper,
            TripPlanItemMapper tripPlanItemMapper,
            JdbcTemplate jdbcTemplate,
            ObjectMapper objectMapper
    ) {
        this.catalogService = catalogService;
        this.tripPlanMapper = tripPlanMapper;
        this.tripPlanDayMapper = tripPlanDayMapper;
        this.tripPlanItemMapper = tripPlanItemMapper;
        this.jdbcTemplate = jdbcTemplate;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public TripPlanResponse generate(Long userId, GenerateTripPlanRequest request) {
        // 1. 先把生成行程需要的基础资料查出来。
        // 当前 MVP 只依赖本地数据库；未来 AI Agent 也可以先查这些资料再做优化。
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

        // 2. 先保存行程主表。主表只记录“这是谁的几日游、预算、偏好”等概要信息。
        TripPlan plan = new TripPlan();
        plan.setUserId(userId);
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

        // 3. 再按天生成明细。每一天会有交通、景点、午餐、景点、晚餐、酒店这些项目。
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

        // 4. 明细插入完成后，回填整趟行程的总预算。
        plan.setTotalBudget(total.setScale(2, RoundingMode.HALF_UP));
        tripPlanMapper.updateById(plan);
        return getPlan(plan.getId());
    }

    public List<TripPlanSummaryResponse> listUserPlans(Long userId) {
        List<TripPlanSummaryResponse> summaries = new ArrayList<>();

        List<TripPlan> rulePlans = tripPlanMapper.selectList(Wrappers.<TripPlan>lambdaQuery()
                .eq(TripPlan::getUserId, userId)
                .orderByDesc(TripPlan::getUpdateTime));
        for (TripPlan rulePlan : rulePlans) {
            City city = catalogService.getCity(rulePlan.getCityId());
            summaries.add(new TripPlanSummaryResponse(
                    "RULE-" + rulePlan.getId(),
                    "RULE",
                    rulePlan.getId(),
                    String.valueOf(rulePlan.getId()),
                    null,
                    1,
                    city.getName(),
                    rulePlan.getTitle(),
                    rulePlan.getDays(),
                    rulePlan.getPeopleCount(),
                    rulePlan.getStartDate(),
                    rulePlan.getTotalBudget(),
                    "CNY",
                    rulePlan.getSourceType(),
                    rulePlan.getSummary(),
                    rulePlan.getCreateTime()
            ));
        }

        try {
            summaries.addAll(jdbcTemplate.query("""
                            SELECT id, conversation_id, plan_id, plan_version, destination,
                                   plan_json, created_at
                            FROM ai_travel_plan_versions
                            WHERE user_id = ? AND is_current = 1
                            ORDER BY created_at DESC
                            """,
                    (resultSet, rowNum) -> toAiSummary(
                            resultSet.getLong("id"),
                            resultSet.getString("conversation_id"),
                            resultSet.getString("plan_id"),
                            resultSet.getInt("plan_version"),
                            resultSet.getString("destination"),
                            resultSet.getString("plan_json"),
                            resultSet.getTimestamp("created_at")
                    ),
                    String.valueOf(userId)));
        } catch (DataAccessException exception) {
            // The Java application can still run before the AI service creates its tables.
            log.warn("AI plan table is unavailable; returning rule plans only", exception);
        }

        summaries.sort(Comparator.comparing(
                TripPlanSummaryResponse::createTime,
                Comparator.nullsLast(Comparator.reverseOrder())
        ));
        return summaries;
    }

    public TripPlanResponse getUserRulePlan(Long userId, Long id) {
        TripPlan plan = tripPlanMapper.selectById(id);
        if (plan == null || !userId.equals(plan.getUserId())) {
            throw new BusinessException("行程不存在或无权查看");
        }
        return getPlan(id);
    }

    public AiTripPlanDetailResponse getUserAiPlan(Long userId, Long recordId) {
        List<AiTripPlanDetailResponse> plans;
        try {
            plans = jdbcTemplate.query("""
                            SELECT id, conversation_id, plan_id, plan_version, plan_json
                            FROM ai_travel_plan_versions
                            WHERE id = ? AND user_id = ? AND is_current = 1
                            """,
                    (resultSet, rowNum) -> {
                        JsonNode root = readPlanJson(resultSet.getString("plan_json"));
                        return new AiTripPlanDetailResponse(
                                resultSet.getLong("id"),
                                resultSet.getString("conversation_id"),
                                resultSet.getString("plan_id"),
                                resultSet.getInt("plan_version"),
                                root.path("plan"),
                                root.path("entities"),
                                root.path("selected_options")
                        );
                    },
                    recordId,
                    String.valueOf(userId));
        } catch (DataAccessException exception) {
            throw new BusinessException("AI 行程暂时无法读取");
        }

        if (plans.isEmpty()) {
            throw new BusinessException("行程不存在或无权查看");
        }
        return plans.get(0);
    }

    public TripPlanResponse getPlan(Long id) {
        // 查询行程详情时，需要把主表、每天、每天的项目组装成前端容易展示的嵌套结构。
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

        // 用取模轮换景点和美食：当游玩天数多于资料数量时，也能循环安排。
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

    private TripPlanSummaryResponse toAiSummary(
            Long recordId,
            String conversationId,
            String planId,
            Integer version,
            String destination,
            String planJson,
            Timestamp createdAt
    ) {
        JsonNode root = readPlanJson(planJson);
        JsonNode planNode = root.path("plan");
        JsonNode entitiesNode = root.path("entities");
        int days = planNode.path("days").isArray() ? planNode.path("days").size() : entitiesNode.path("days").asInt(0);
        int people = entitiesNode.path("people").asInt(1);
        BigDecimal totalBudget = parseMoney(planNode.path("total_cost").asText("0"));
        LocalDate startDate = parseDate(entitiesNode.path("start_date").asText(null));
        String title = destination + (days > 0 ? days + "天" : "") + "智能行程";
        String summary = firstText(planNode.path("assumptions"), "由 AI 多阶段规划生成，可回到原会话继续修改。");

        return new TripPlanSummaryResponse(
                "AI-" + recordId,
                "AI",
                recordId,
                planId,
                conversationId,
                version,
                destination,
                title,
                days,
                people,
                startDate,
                totalBudget,
                planNode.path("currency").asText("CNY"),
                "AI",
                summary,
                createdAt == null ? null : createdAt.toLocalDateTime()
        );
    }

    private JsonNode readPlanJson(String planJson) {
        try {
            return objectMapper.readTree(planJson);
        } catch (JsonProcessingException exception) {
            throw new BusinessException("行程数据格式异常");
        }
    }

    private BigDecimal parseMoney(String value) {
        try {
            return new BigDecimal(value == null || value.isBlank() ? "0" : value);
        } catch (NumberFormatException exception) {
            return BigDecimal.ZERO;
        }
    }

    private LocalDate parseDate(String value) {
        try {
            return value == null || value.isBlank() || "null".equals(value) ? null : LocalDate.parse(value);
        } catch (RuntimeException exception) {
            return null;
        }
    }

    private String firstText(JsonNode values, String fallback) {
        if (values.isArray() && !values.isEmpty()) {
            String value = values.get(0).asText("");
            if (!value.isBlank()) {
                return value;
            }
        }
        return fallback;
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
