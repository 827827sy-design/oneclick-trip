package com.oneclicktrip.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.oneclicktrip.common.BusinessException;
import com.oneclicktrip.dto.InternalPlanVersionRequest;
import com.oneclicktrip.dto.InternalPreferenceRequest;
import com.oneclicktrip.dto.InternalPreferenceResponse;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.util.List;

@Service
public class AgentPersistenceService {
    private final JdbcTemplate jdbcTemplate;
    private final ObjectMapper objectMapper;

    public AgentPersistenceService(JdbcTemplate jdbcTemplate, ObjectMapper objectMapper) {
        this.jdbcTemplate = jdbcTemplate;
        this.objectMapper = objectMapper;
    }

    public InternalPreferenceResponse getPreferences(String rawUserId) {
        String userId = requireNumericUserId(rawUserId);
        List<InternalPreferenceResponse> rows = jdbcTemplate.query(
                """
                        SELECT preference_json, source_version, updated_at
                        FROM ai_user_travel_preferences
                        WHERE user_id = ?
                        """,
                (resultSet, rowNum) -> new InternalPreferenceResponse(
                        userId,
                        readJson(resultSet.getString("preference_json")),
                        resultSet.getInt("source_version"),
                        resultSet.getTimestamp("updated_at").toLocalDateTime()
                ),
                userId
        );
        if (!rows.isEmpty()) {
            return rows.get(0);
        }
        ObjectNode empty = objectMapper.createObjectNode();
        empty.putArray("liked_tags");
        empty.putArray("disliked_tags");
        empty.putArray("preferred_transport");
        empty.putNull("pace");
        empty.putNull("typical_budget_scope");
        empty.putArray("memory_items");
        empty.put("source_version", 0);
        return new InternalPreferenceResponse(userId, empty, 0, null);
    }

    @Transactional
    public InternalPreferenceResponse savePreferences(
            String rawUserId,
            InternalPreferenceRequest request
    ) {
        String userId = requireNumericUserId(rawUserId);
        int sourceVersion = request.sourceVersion() == null
                ? request.preferences().path("source_version").asInt(0)
                : request.sourceVersion();
        if (sourceVersion < 0) {
            throw new BusinessException("偏好版本不能小于 0");
        }
        LocalDateTime now = LocalDateTime.now();
        jdbcTemplate.update(
                """
                        INSERT INTO ai_user_travel_preferences
                            (user_id, preference_json, source_version, updated_at)
                        VALUES (?, CAST(? AS JSON), ?, ?)
                        ON DUPLICATE KEY UPDATE
                            preference_json = VALUES(preference_json),
                            source_version = VALUES(source_version),
                            updated_at = VALUES(updated_at)
                        """,
                userId,
                writeJson(request.preferences()),
                sourceVersion,
                Timestamp.valueOf(now)
        );
        return new InternalPreferenceResponse(userId, request.preferences(), sourceVersion, now);
    }

    public JsonNode getCurrentPlan(String rawUserId, String conversationId) {
        String userId = requireNumericUserId(rawUserId);
        List<JsonNode> rows = jdbcTemplate.query(
                """
                        SELECT plan_json
                        FROM ai_travel_plan_versions
                        WHERE user_id = ? AND conversation_id = ? AND is_current = 1
                        ORDER BY plan_version DESC
                        LIMIT 1
                        """,
                (resultSet, rowNum) -> readJson(resultSet.getString("plan_json")),
                userId,
                conversationId
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    @Transactional
    public JsonNode savePlanVersion(InternalPlanVersionRequest request) {
        String userId = requireNumericUserId(request.userId());
        JsonNode plan = request.planState().path("plan");
        String planId = requiredText(plan, "plan_id", "方案缺少 plan_id");
        String destination = requiredText(plan, "destination", "方案缺少 destination");
        int version = plan.path("version").asInt(0);
        if (version < 1) {
            throw new BusinessException("方案版本必须大于 0");
        }

        List<PlanVersionRow> existingRows = jdbcTemplate.query(
                """
                        SELECT plan_version, plan_json
                        FROM ai_travel_plan_versions
                        WHERE user_id = ? AND conversation_id = ? AND plan_id = ?
                        ORDER BY plan_version DESC
                        LIMIT 1
                        """,
                (resultSet, rowNum) -> new PlanVersionRow(
                        resultSet.getInt("plan_version"),
                        readJson(resultSet.getString("plan_json"))
                ),
                userId,
                request.conversationId(),
                planId
        );
        if (!existingRows.isEmpty()) {
            PlanVersionRow latest = existingRows.get(0);
            if (latest.version() == version && latest.planState().equals(request.planState())) {
                return latest.planState();
            }
            if (version != latest.version() + 1) {
                throw new BusinessException("方案版本必须在当前版本基础上递增 1");
            }
        } else if (version != 1) {
            throw new BusinessException("首个方案版本必须为 1");
        }

        jdbcTemplate.update(
                """
                        UPDATE ai_travel_plan_versions
                        SET is_current = 0
                        WHERE user_id = ? AND conversation_id = ? AND is_current = 1
                        """,
                userId,
                request.conversationId()
        );
        try {
            jdbcTemplate.update(
                    """
                            INSERT INTO ai_travel_plan_versions
                                (user_id, conversation_id, plan_id, plan_version, destination,
                                 plan_json, is_current, created_at)
                            VALUES (?, ?, ?, ?, ?, CAST(? AS JSON), 1, ?)
                            """,
                    userId,
                    request.conversationId(),
                    planId,
                    version,
                    destination,
                    writeJson(request.planState()),
                    Timestamp.valueOf(LocalDateTime.now())
            );
        } catch (DuplicateKeyException exception) {
            throw new BusinessException("方案版本已存在，请勿重复写入不同内容");
        }
        return request.planState();
    }

    private String requireNumericUserId(String value) {
        if (value == null || !value.matches("[1-9]\\d*")) {
            throw new BusinessException("user_id 必须是有效的登录用户编号");
        }
        return value;
    }

    private String requiredText(JsonNode node, String field, String message) {
        String value = node.path(field).asText("");
        if (value.isBlank()) {
            throw new BusinessException(message);
        }
        return value;
    }

    private JsonNode readJson(String value) {
        try {
            return objectMapper.readTree(value);
        } catch (JsonProcessingException exception) {
            throw new BusinessException("持久化 JSON 数据格式异常");
        }
    }

    private String writeJson(JsonNode value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            throw new BusinessException("无法序列化持久化数据");
        }
    }

    private record PlanVersionRow(int version, JsonNode planState) {
    }
}
