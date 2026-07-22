package com.oneclicktrip.service;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
public class AgentRunLogService {
    private static final String BASE_SELECT = """
            SELECT r.*, u.username, u.nickname
            FROM ai_agent_run_log r
            LEFT JOIN sys_user u ON u.id = r.user_id
            """;

    private final JdbcTemplate jdbcTemplate;
    private final ObjectMapper objectMapper;

    public AgentRunLogService(JdbcTemplate jdbcTemplate, ObjectMapper objectMapper) {
        this.jdbcTemplate = jdbcTemplate;
        this.objectMapper = objectMapper;
    }

    public void record(String runId, Long userId, String conversationId, JsonNode job) {
        JsonNode result = job.path("result");
        ArrayNode safeErrors = objectMapper.createArrayNode();
        result.path("tool_errors").forEach(error -> {
            var safe = safeErrors.addObject();
            safe.put("toolName", error.path("tool_name").asText("unknown"));
            safe.put("errorCode", error.path("error_code").asText("UNKNOWN"));
            safe.put("retryable", error.path("retryable").asBoolean(false));
            safe.put("attempt", error.path("attempt").asInt(1));
        });

        ArrayNode degradationModes = objectMapper.createArrayNode();
        result.path("tool_results").fields().forEachRemaining(entry -> {
            JsonNode toolResult = entry.getValue();
            String mode = toolResult.path("data_mode").asText("unknown");
            if (isDegraded(mode)) {
                var degraded = degradationModes.addObject();
                degraded.put("component", entry.getKey());
                degraded.put("mode", mode);
                degraded.put("source", limit(toolResult.path("source").asText("unknown"), 128));
            }
        });
        String modelMode = job.path("model_mode").asText("unknown");
        if ("rules".equalsIgnoreCase(modelMode)) {
            var degraded = degradationModes.addObject();
            degraded.put("component", "llm");
            degraded.put("mode", "rules_fallback");
            degraded.put("source", "local-rules");
        }

        String status = job.path("status").asText("FAILED");
        String errorMessage = "FAILED".equals(status)
                ? sanitize(job.path("error").asText("Agent run failed"))
                : null;
        String errorCode = "FAILED".equals(status) ? "AGENT_RUN_FAILED" : firstErrorCode(safeErrors);

        jdbcTemplate.update("""
                INSERT INTO ai_agent_run_log (
                  run_id, user_id, conversation_id, intent, status, duration_ms,
                  model_mode, next_action, node_timings_json, selected_tools_json,
                  tool_errors_json, degradation_modes_json, plan_saved, error_code,
                  error_message, started_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON DUPLICATE KEY UPDATE
                  status = VALUES(status), duration_ms = VALUES(duration_ms),
                  intent = VALUES(intent), model_mode = VALUES(model_mode),
                  next_action = VALUES(next_action), node_timings_json = VALUES(node_timings_json),
                  selected_tools_json = VALUES(selected_tools_json),
                  tool_errors_json = VALUES(tool_errors_json),
                  degradation_modes_json = VALUES(degradation_modes_json),
                  plan_saved = VALUES(plan_saved), error_code = VALUES(error_code),
                  error_message = VALUES(error_message), completed_at = VALUES(completed_at)
                """,
                runId,
                userId,
                conversationId,
                result.path("intent").asText("unknown"),
                status,
                nullableLong(job.get("duration_ms")),
                limit(modelMode, 128),
                nullIfBlank(result.path("next_action").asText()),
                json(job.path("node_timings"), objectMapper.createObjectNode()),
                json(result.path("selected_tools"), objectMapper.createArrayNode()),
                safeErrors.toString(),
                degradationModes.toString(),
                result.path("plan_saved").asBoolean(false),
                errorCode,
                errorMessage,
                parseTimestamp(job.path("started_at").asText()),
                parseTimestamp(job.path("completed_at").asText())
        );
    }

    public Page<Map<String, Object>> list(
            int page,
            int size,
            Long userId,
            String keyword,
            String intent,
            String status,
            LocalDateTime startTime,
            LocalDateTime endTime
    ) {
        List<Object> params = new ArrayList<>();
        String where = buildWhere(userId, keyword, intent, status, startTime, endTime, params);
        Long total = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM ai_agent_run_log r LEFT JOIN sys_user u ON u.id = r.user_id " + where,
                Long.class,
                params.toArray()
        );
        List<Object> pageParams = new ArrayList<>(params);
        pageParams.add(size);
        pageParams.add((long) (page - 1) * size);
        List<Map<String, Object>> records = jdbcTemplate.query(
                BASE_SELECT + where + " ORDER BY r.create_time DESC LIMIT ? OFFSET ?",
                this::mapRow,
                pageParams.toArray()
        );
        Page<Map<String, Object>> result = new Page<>(page, size, total == null ? 0 : total);
        result.setRecords(records);
        return result;
    }

    public Map<String, Object> detail(Long id) {
        List<Map<String, Object>> rows = jdbcTemplate.query(
                BASE_SELECT + " WHERE r.id = ?",
                this::mapRow,
                id
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public Map<String, Object> stats() {
        return jdbcTemplate.queryForObject("""
                SELECT COUNT(*) total,
                       COALESCE(SUM(status = 'COMPLETED'), 0) completed,
                       COALESCE(ROUND(AVG(duration_ms)), 0) average_duration_ms,
                       COALESCE(SUM(JSON_LENGTH(tool_errors_json) > 0), 0) tool_error_runs,
                       COALESCE(SUM(JSON_LENGTH(degradation_modes_json) > 0), 0) degraded_runs
                FROM ai_agent_run_log
                """, (rs, rowNum) -> {
            long total = rs.getLong("total");
            Map<String, Object> data = new LinkedHashMap<>();
            data.put("total", total);
            data.put("completed", rs.getLong("completed"));
            data.put("completionRate", ratio(rs.getLong("completed"), total));
            data.put("averageDurationMs", rs.getLong("average_duration_ms"));
            data.put("toolErrorRuns", rs.getLong("tool_error_runs"));
            data.put("toolErrorRate", ratio(rs.getLong("tool_error_runs"), total));
            data.put("degradedRuns", rs.getLong("degraded_runs"));
            data.put("degradationRate", ratio(rs.getLong("degraded_runs"), total));
            return data;
        });
    }

    private String buildWhere(
            Long userId, String keyword, String intent, String status,
            LocalDateTime startTime, LocalDateTime endTime, List<Object> params
    ) {
        StringBuilder where = new StringBuilder(" WHERE 1 = 1");
        if (userId != null) {
            where.append(" AND r.user_id = ?");
            params.add(userId);
        }
        if (hasText(keyword)) {
            where.append(" AND (r.conversation_id LIKE ? OR r.run_id LIKE ? OR u.username LIKE ? OR u.nickname LIKE ?)");
            String pattern = "%" + keyword.trim() + "%";
            params.add(pattern);
            params.add(pattern);
            params.add(pattern);
            params.add(pattern);
        }
        if (hasText(intent)) {
            where.append(" AND r.intent = ?");
            params.add(intent);
        }
        if (hasText(status)) {
            where.append(" AND r.status = ?");
            params.add(status);
        }
        if (startTime != null) {
            where.append(" AND r.create_time >= ?");
            params.add(Timestamp.valueOf(startTime));
        }
        if (endTime != null) {
            where.append(" AND r.create_time <= ?");
            params.add(Timestamp.valueOf(endTime));
        }
        return where.toString();
    }

    private Map<String, Object> mapRow(ResultSet rs, int rowNum) throws SQLException {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("id", rs.getLong("id"));
        data.put("runId", rs.getString("run_id"));
        data.put("userId", rs.getLong("user_id"));
        data.put("username", rs.getString("username"));
        data.put("nickname", rs.getString("nickname"));
        data.put("conversationId", rs.getString("conversation_id"));
        data.put("intent", rs.getString("intent"));
        data.put("status", rs.getString("status"));
        data.put("durationMs", rs.getObject("duration_ms"));
        data.put("modelMode", rs.getString("model_mode"));
        data.put("nextAction", rs.getString("next_action"));
        data.put("nodeTimings", readJson(rs.getString("node_timings_json")));
        data.put("selectedTools", readJson(rs.getString("selected_tools_json")));
        data.put("toolErrors", readJson(rs.getString("tool_errors_json")));
        data.put("degradationModes", readJson(rs.getString("degradation_modes_json")));
        data.put("planSaved", rs.getBoolean("plan_saved"));
        data.put("errorCode", rs.getString("error_code"));
        data.put("errorMessage", rs.getString("error_message"));
        data.put("startedAt", rs.getTimestamp("started_at"));
        data.put("completedAt", rs.getTimestamp("completed_at"));
        data.put("createTime", rs.getTimestamp("create_time"));
        return data;
    }

    private JsonNode readJson(String value) {
        try {
            return objectMapper.readTree(value);
        } catch (Exception ignored) {
            return objectMapper.createArrayNode();
        }
    }

    private String json(JsonNode value, JsonNode fallback) {
        return value == null || value.isMissingNode() || value.isNull()
                ? fallback.toString()
                : value.toString();
    }

    private Timestamp parseTimestamp(String value) {
        if (!hasText(value)) {
            return null;
        }
        try {
            return Timestamp.from(Instant.parse(value));
        } catch (Exception ignored) {
            return null;
        }
    }

    private Long nullableLong(JsonNode value) {
        return value == null || value.isNull() || value.isMissingNode() ? null : value.asLong();
    }

    private String firstErrorCode(ArrayNode errors) {
        return errors.isEmpty() ? null : errors.get(0).path("errorCode").asText(null);
    }

    private boolean isDegraded(String mode) {
        String normalized = mode == null ? "" : mode.toLowerCase();
        return normalized.contains("fallback") || normalized.contains("mock") || normalized.contains("unavailable");
    }

    private String sanitize(String value) {
        if (value == null) {
            return null;
        }
        return limit(value
                .replaceAll("(?i)sk-[a-z0-9_-]{8,}", "[REDACTED]")
                .replaceAll("(?i)(bearer\\s+)[^\\s]+", "$1[REDACTED]")
                .replaceAll("(?i)(confirmation[_-]?token[=: ]+)[^,\\s}]+", "$1[REDACTED]"), 512);
    }

    private double ratio(long numerator, long denominator) {
        return denominator == 0 ? 0D : Math.round((numerator * 1000D / denominator)) / 10D;
    }

    private String nullIfBlank(String value) {
        return hasText(value) ? value : null;
    }

    private boolean hasText(String value) {
        return value != null && !value.isBlank();
    }

    private String limit(String value, int maxLength) {
        if (value == null) {
            return null;
        }
        return value.length() <= maxLength ? value : value.substring(0, maxLength);
    }
}
