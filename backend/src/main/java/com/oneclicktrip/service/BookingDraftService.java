package com.oneclicktrip.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.oneclicktrip.common.BusinessException;
import com.oneclicktrip.dto.BookingDraftActionRequest;
import com.oneclicktrip.dto.BookingDraftCreateRequest;
import com.oneclicktrip.dto.BookingDraftResponse;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Base64;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.UUID;

@Service
public class BookingDraftService {
    private static final Set<String> ALLOWED_BOOKING_TYPES = Set.of(
            "hotel", "train", "flight", "ticket", "transport"
    );
    private static final int DRAFT_TTL_MINUTES = 15;

    private final JdbcTemplate jdbcTemplate;
    private final ObjectMapper objectMapper;
    private final SecureRandom secureRandom = new SecureRandom();

    public BookingDraftService(JdbcTemplate jdbcTemplate, ObjectMapper objectMapper) {
        this.jdbcTemplate = jdbcTemplate;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public BookingDraftResponse create(BookingDraftCreateRequest request) {
        String userId = requireNumericUserId(request.userId());
        List<String> bookingTypes = normalizeBookingTypes(request.bookingTypes());
        List<String> optionIds = request.selectedOptionIds().stream()
                .filter(value -> value != null && !value.isBlank())
                .distinct()
                .toList();
        if (optionIds.isEmpty()) {
            throw new BusinessException("必须选择至少一个可预订选项");
        }
        JsonNode planState = loadCurrentPlan(
                userId,
                request.conversationId(),
                request.planId(),
                request.planVersion()
        );
        Set<String> allowedOptionIds = collectOptionIds(planState);
        if (!allowedOptionIds.containsAll(optionIds)) {
            throw new BusinessException("预订选项不属于当前方案或已经失效");
        }

        String draftId = "DRAFT-" + UUID.randomUUID().toString().replace("-", "").toUpperCase(Locale.ROOT);
        String token = generateToken();
        LocalDateTime now = LocalDateTime.now();
        LocalDateTime expiresAt = now.plusMinutes(DRAFT_TTL_MINUTES);
        jdbcTemplate.update(
                """
                        INSERT INTO ai_booking_draft
                            (draft_id, user_id, conversation_id, plan_id, plan_version,
                             booking_types_json, selected_option_ids_json, status,
                             confirmation_token_hash, expires_at, create_time, update_time)
                        VALUES (?, ?, ?, ?, ?, CAST(? AS JSON), CAST(? AS JSON),
                                'PENDING_CONFIRMATION', ?, ?, ?, ?)
                        """,
                draftId,
                userId,
                request.conversationId(),
                request.planId(),
                request.planVersion(),
                writeJson(bookingTypes),
                writeJson(optionIds),
                sha256(token),
                Timestamp.valueOf(expiresAt),
                Timestamp.valueOf(now),
                Timestamp.valueOf(now)
        );
        return new BookingDraftResponse(
                draftId,
                "pending_confirmation",
                request.conversationId(),
                userId,
                request.planId(),
                request.planVersion(),
                bookingTypes,
                optionIds,
                now,
                expiresAt,
                token
        );
    }

    @Transactional
    public BookingDraftResponse confirm(String draftId, BookingDraftActionRequest request) {
        return changeStatus(draftId, request, "CONFIRMED");
    }

    @Transactional
    public BookingDraftResponse cancel(String draftId, BookingDraftActionRequest request) {
        return changeStatus(draftId, request, "CANCELLED");
    }

    public BookingDraftResponse get(String draftId, String rawUserId) {
        DraftRow row = loadDraft(draftId, false);
        String userId = requireNumericUserId(rawUserId);
        if (!row.userId().equals(userId)) {
            throw new BusinessException("订单草稿不存在或无权查看");
        }
        return toResponse(row, null);
    }

    private BookingDraftResponse changeStatus(
            String draftId,
            BookingDraftActionRequest request,
            String targetStatus
    ) {
        DraftRow row = loadDraft(draftId, true);
        String userId = requireNumericUserId(request.userId());
        assertBinding(row, request, userId);
        if (!MessageDigest.isEqual(
                row.confirmationTokenHash().getBytes(StandardCharsets.UTF_8),
                sha256(request.confirmationToken()).getBytes(StandardCharsets.UTF_8)
        )) {
            throw new BusinessException("确认凭证无效");
        }
        if (row.status().equals(targetStatus)) {
            if (request.idempotencyKey().equals(row.idempotencyKey())) {
                return toResponse(row, null);
            }
            throw new BusinessException("订单草稿已经处理，幂等键不匹配");
        }
        if (!"PENDING_CONFIRMATION".equals(row.status())) {
            throw new BusinessException("订单草稿当前状态不可操作");
        }
        if (row.expiresAt().isBefore(LocalDateTime.now())) {
            jdbcTemplate.update(
                    "UPDATE ai_booking_draft SET status = 'EXPIRED', update_time = ? WHERE draft_id = ?",
                    Timestamp.valueOf(LocalDateTime.now()),
                    draftId
            );
            throw new BusinessException("订单草稿已经过期");
        }

        LocalDateTime now = LocalDateTime.now();
        try {
            jdbcTemplate.update(
                    """
                            UPDATE ai_booking_draft
                            SET status = ?, idempotency_key = ?, confirmed_at = ?, update_time = ?
                            WHERE draft_id = ? AND status = 'PENDING_CONFIRMATION'
                            """,
                    targetStatus,
                    request.idempotencyKey(),
                    "CONFIRMED".equals(targetStatus) ? Timestamp.valueOf(now) : null,
                    Timestamp.valueOf(now),
                    draftId
            );
        } catch (DuplicateKeyException exception) {
            throw new BusinessException("幂等键已被其他请求使用");
        }
        return toResponse(row.withStatus(targetStatus, request.idempotencyKey()), null);
    }

    private JsonNode loadCurrentPlan(
            String userId,
            String conversationId,
            String planId,
            int planVersion
    ) {
        List<JsonNode> rows = jdbcTemplate.query(
                """
                        SELECT plan_json
                        FROM ai_travel_plan_versions
                        WHERE user_id = ? AND conversation_id = ? AND plan_id = ?
                          AND plan_version = ? AND is_current = 1
                        """,
                (resultSet, rowNum) -> readJson(resultSet.getString("plan_json")),
                userId,
                conversationId,
                planId,
                planVersion
        );
        if (rows.isEmpty()) {
            throw new BusinessException("当前方案不存在、版本已过期或不属于该用户");
        }
        return rows.get(0);
    }

    private DraftRow loadDraft(String draftId, boolean forUpdate) {
        String suffix = forUpdate ? " FOR UPDATE" : "";
        List<DraftRow> rows = jdbcTemplate.query(
                """
                        SELECT draft_id, user_id, conversation_id, plan_id, plan_version,
                               booking_types_json, selected_option_ids_json, status,
                               confirmation_token_hash, idempotency_key, expires_at, create_time
                        FROM ai_booking_draft
                        WHERE draft_id = ?
                        """ + suffix,
                (resultSet, rowNum) -> new DraftRow(
                        resultSet.getString("draft_id"),
                        resultSet.getString("user_id"),
                        resultSet.getString("conversation_id"),
                        resultSet.getString("plan_id"),
                        resultSet.getInt("plan_version"),
                        readStringList(resultSet.getString("booking_types_json")),
                        readStringList(resultSet.getString("selected_option_ids_json")),
                        resultSet.getString("status"),
                        resultSet.getString("confirmation_token_hash"),
                        resultSet.getString("idempotency_key"),
                        resultSet.getTimestamp("expires_at").toLocalDateTime(),
                        resultSet.getTimestamp("create_time").toLocalDateTime()
                ),
                draftId
        );
        if (rows.isEmpty()) {
            throw new BusinessException("订单草稿不存在");
        }
        return rows.get(0);
    }

    private void assertBinding(DraftRow row, BookingDraftActionRequest request, String userId) {
        if (!row.userId().equals(userId)
                || !row.conversationId().equals(request.conversationId())
                || !row.planId().equals(request.planId())
                || row.planVersion() != request.planVersion()) {
            throw new BusinessException("订单草稿与用户或当前方案不匹配");
        }
    }

    private Set<String> collectOptionIds(JsonNode planState) {
        Set<String> ids = new HashSet<>();
        JsonNode selected = planState.path("selected_options");
        selected.fields().forEachRemaining(entry -> {
            if (entry.getValue().isArray()) {
                entry.getValue().forEach(value -> ids.add(value.asText()));
            }
        });
        JsonNode plan = planState.path("plan");
        addText(ids, plan.path("hotel_area_id"));
        addText(ids, plan.path("transport_option_id"));
        plan.path("days").forEach(day -> {
            addText(ids, day.path("hotel_option_id"));
            day.path("items").forEach(item -> addText(ids, item.path("ticket_option_id")));
        });
        ids.remove("");
        return ids;
    }

    private void addText(Set<String> ids, JsonNode value) {
        if (value.isTextual() && !value.asText().isBlank()) {
            ids.add(value.asText());
        }
    }

    private List<String> normalizeBookingTypes(List<String> values) {
        List<String> normalized = new ArrayList<>();
        for (String value : values) {
            String item = value == null ? "" : value.trim().toLowerCase(Locale.ROOT);
            if (!ALLOWED_BOOKING_TYPES.contains(item)) {
                throw new BusinessException("不支持的预订类型：" + value);
            }
            if (!normalized.contains(item)) {
                normalized.add(item);
            }
        }
        return List.copyOf(normalized);
    }

    private BookingDraftResponse toResponse(DraftRow row, String token) {
        return new BookingDraftResponse(
                row.draftId(), row.status().toLowerCase(Locale.ROOT), row.conversationId(), row.userId(),
                row.planId(), row.planVersion(), row.bookingTypes(), row.selectedOptionIds(),
                row.createdAt(), row.expiresAt(), token
        );
    }

    private String generateToken() {
        byte[] bytes = new byte[32];
        secureRandom.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    private String sha256(String value) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8));
            return java.util.HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 unavailable", exception);
        }
    }

    private String requireNumericUserId(String value) {
        if (value == null || !value.matches("[1-9]\\d*")) {
            throw new BusinessException("user_id 必须是有效的登录用户编号");
        }
        return value;
    }

    private JsonNode readJson(String value) {
        try {
            return objectMapper.readTree(value);
        } catch (JsonProcessingException exception) {
            throw new BusinessException("方案 JSON 数据格式异常");
        }
    }

    private List<String> readStringList(String value) {
        try {
            return objectMapper.readValue(value, new TypeReference<>() { });
        } catch (JsonProcessingException exception) {
            throw new BusinessException("订单草稿 JSON 数据格式异常");
        }
    }

    private String writeJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            throw new BusinessException("无法序列化订单草稿");
        }
    }

    private record DraftRow(
            String draftId,
            String userId,
            String conversationId,
            String planId,
            int planVersion,
            List<String> bookingTypes,
            List<String> selectedOptionIds,
            String status,
            String confirmationTokenHash,
            String idempotencyKey,
            LocalDateTime expiresAt,
            LocalDateTime createdAt
    ) {
        DraftRow withStatus(String newStatus, String newIdempotencyKey) {
            return new DraftRow(
                    draftId, userId, conversationId, planId, planVersion,
                    bookingTypes, selectedOptionIds, newStatus, confirmationTokenHash,
                    newIdempotencyKey, expiresAt, createdAt
            );
        }
    }
}
