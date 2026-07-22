package com.oneclicktrip.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.oneclicktrip.dto.BookingDraftActionRequest;
import com.oneclicktrip.dto.BookingDraftResponse;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentMatchers;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.sql.ResultSet;
import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.util.HexFormat;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class BookingDraftServiceTest {
    private final JdbcTemplate jdbcTemplate = mock(JdbcTemplate.class);
    private final BookingDraftService service = new BookingDraftService(
            jdbcTemplate,
            new ObjectMapper()
    );

    @Test
    @SuppressWarnings({"rawtypes", "unchecked"})
    void repeatedConfirmationWithTheSameIdempotencyKeyReturnsTheExistingResult() throws Exception {
        String token = "confirmation-token";
        mockDraftQuery("CONFIRMED", token, "idem-1");
        BookingDraftActionRequest request = action(token, "idem-1");

        BookingDraftResponse first = service.confirm("DRAFT-1", request);
        BookingDraftResponse second = service.confirm("DRAFT-1", request);

        assertThat(first.status()).isEqualTo("confirmed");
        assertThat(second.draftId()).isEqualTo("DRAFT-1");
        assertThat(second.confirmationToken()).isNull();
    }

    @Test
    @SuppressWarnings({"rawtypes", "unchecked"})
    void repeatedConfirmationWithAnotherIdempotencyKeyIsRejected() throws Exception {
        String token = "confirmation-token";
        mockDraftQuery("CONFIRMED", token, "idem-original");

        assertThatThrownBy(() -> service.confirm("DRAFT-1", action(token, "idem-other")))
                .hasMessageContaining("幂等键不匹配");
    }

    @SuppressWarnings({"rawtypes", "unchecked"})
    private void mockDraftQuery(String status, String token, String idempotencyKey) throws Exception {
        ResultSet resultSet = mock(ResultSet.class);
        when(resultSet.getString("draft_id")).thenReturn("DRAFT-1");
        when(resultSet.getString("user_id")).thenReturn("42");
        when(resultSet.getString("conversation_id")).thenReturn("conversation-1");
        when(resultSet.getString("plan_id")).thenReturn("plan-1");
        when(resultSet.getInt("plan_version")).thenReturn(1);
        when(resultSet.getString("booking_types_json")).thenReturn("[\"hotel\"]");
        when(resultSet.getString("selected_option_ids_json")).thenReturn("[\"hotel-1\"]");
        when(resultSet.getString("status")).thenReturn(status);
        when(resultSet.getString("confirmation_token_hash")).thenReturn(sha256(token));
        when(resultSet.getString("idempotency_key")).thenReturn(idempotencyKey);
        when(resultSet.getTimestamp("expires_at"))
                .thenReturn(Timestamp.valueOf(LocalDateTime.now().plusMinutes(10)));
        when(resultSet.getTimestamp("create_time"))
                .thenReturn(Timestamp.valueOf(LocalDateTime.now()));

        when(jdbcTemplate.query(
                anyString(),
                ArgumentMatchers.<RowMapper<Object>>any(),
                ArgumentMatchers.<Object[]>any()
        )).thenAnswer(invocation -> {
            RowMapper mapper = invocation.getArgument(1);
            return List.of(mapper.mapRow(resultSet, 0));
        });
    }

    private BookingDraftActionRequest action(String token, String idempotencyKey) {
        return new BookingDraftActionRequest(
                "42",
                "conversation-1",
                "plan-1",
                1,
                token,
                idempotencyKey
        );
    }

    private String sha256(String value) throws Exception {
        return HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256")
                        .digest(value.getBytes(StandardCharsets.UTF_8))
        );
    }
}
