package com.oneclicktrip.controller;

import com.fasterxml.jackson.databind.JsonNode;
import com.oneclicktrip.dto.BookingDraftActionRequest;
import com.oneclicktrip.dto.BookingDraftCreateRequest;
import com.oneclicktrip.dto.BookingDraftResponse;
import com.oneclicktrip.dto.InternalPlanVersionRequest;
import com.oneclicktrip.dto.InternalPreferenceRequest;
import com.oneclicktrip.dto.InternalPreferenceResponse;
import com.oneclicktrip.service.AgentPersistenceService;
import com.oneclicktrip.service.BookingDraftService;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/internal/ai")
public class InternalAgentPersistenceController {
    private final AgentPersistenceService persistenceService;
    private final BookingDraftService bookingDraftService;

    public InternalAgentPersistenceController(
            AgentPersistenceService persistenceService,
            BookingDraftService bookingDraftService
    ) {
        this.persistenceService = persistenceService;
        this.bookingDraftService = bookingDraftService;
    }

    @GetMapping("/users/{userId}/preferences")
    public InternalPreferenceResponse preferences(@PathVariable String userId) {
        return persistenceService.getPreferences(userId);
    }

    @PutMapping("/users/{userId}/preferences")
    public InternalPreferenceResponse savePreferences(
            @PathVariable String userId,
            @Valid @RequestBody InternalPreferenceRequest request
    ) {
        return persistenceService.savePreferences(userId, request);
    }

    @GetMapping("/plans/current")
    public JsonNode currentPlan(
            @RequestParam("user_id") String userId,
            @RequestParam("conversation_id") String conversationId
    ) {
        return persistenceService.getCurrentPlan(userId, conversationId);
    }

    @PostMapping("/plans/versions")
    public JsonNode savePlanVersion(@Valid @RequestBody InternalPlanVersionRequest request) {
        return persistenceService.savePlanVersion(request);
    }

    @PostMapping("/booking-drafts")
    public BookingDraftResponse createBookingDraft(
            @Valid @RequestBody BookingDraftCreateRequest request
    ) {
        return bookingDraftService.create(request);
    }

    @GetMapping("/booking-drafts/{draftId}")
    public BookingDraftResponse bookingDraft(
            @PathVariable String draftId,
            @RequestParam("user_id") String userId
    ) {
        return bookingDraftService.get(draftId, userId);
    }

    @PostMapping("/booking-drafts/{draftId}/confirm")
    public BookingDraftResponse confirmBookingDraft(
            @PathVariable String draftId,
            @Valid @RequestBody BookingDraftActionRequest request
    ) {
        return bookingDraftService.confirm(draftId, request);
    }

    @PostMapping("/booking-drafts/{draftId}/cancel")
    public BookingDraftResponse cancelBookingDraft(
            @PathVariable String draftId,
            @Valid @RequestBody BookingDraftActionRequest request
    ) {
        return bookingDraftService.cancel(draftId, request);
    }
}
