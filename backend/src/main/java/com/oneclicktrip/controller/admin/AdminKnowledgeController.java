package com.oneclicktrip.controller.admin;

import com.fasterxml.jackson.databind.JsonNode;
import com.oneclicktrip.client.FastApiAgentClient;
import com.oneclicktrip.common.ApiResponse;
import com.oneclicktrip.security.JwtUser;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/admin/knowledge")
public class AdminKnowledgeController {
    private final FastApiAgentClient agentClient;

    public AdminKnowledgeController(FastApiAgentClient agentClient) {
        this.agentClient = agentClient;
    }

    @GetMapping("/stats")
    public ApiResponse<JsonNode> stats() {
        return ApiResponse.ok(agentClient.knowledgeStats());
    }

    @PostMapping("/rebuild")
    public ApiResponse<JsonNode> rebuild() {
        return ApiResponse.ok("知识库索引已按审核记录重建", agentClient.rebuildKnowledgeIndex());
    }

    @GetMapping("/batches")
    public ApiResponse<JsonNode> batches() {
        return ApiResponse.ok(agentClient.knowledgeBatches());
    }

    @GetMapping("/batches/{batchId}")
    public ApiResponse<JsonNode> batch(@PathVariable String batchId) {
        return ApiResponse.ok(agentClient.knowledgeBatch(batchId));
    }

    @PostMapping("/preview")
    public ApiResponse<JsonNode> preview(@RequestBody JsonNode payload) {
        return ApiResponse.ok(agentClient.previewKnowledge(payload));
    }

    @PostMapping("/collect")
    public ApiResponse<JsonNode> collect(@RequestBody JsonNode payload) {
        return ApiResponse.ok(agentClient.collectKnowledge(payload));
    }

    @PostMapping("/batches/{batchId}/publish")
    public ApiResponse<JsonNode> publish(
            @PathVariable String batchId,
            @AuthenticationPrincipal JwtUser currentUser
    ) {
        return ApiResponse.ok(
                "知识批次已发布",
                agentClient.publishKnowledge(batchId, reviewer(currentUser))
        );
    }

    @PostMapping("/batches/{batchId}/records/{recordId}/review")
    public ApiResponse<JsonNode> reviewRecord(
            @PathVariable String batchId,
            @PathVariable String recordId,
            @RequestBody JsonNode payload,
            @AuthenticationPrincipal JwtUser currentUser
    ) {
        return ApiResponse.ok(
                "资料审核结果已保存",
                agentClient.reviewKnowledgeRecord(
                        batchId,
                        recordId,
                        payload,
                        reviewer(currentUser)
                )
        );
    }

    @DeleteMapping("/batches/{batchId}/records/{recordId}")
    public ApiResponse<JsonNode> deleteApprovedRecord(
            @PathVariable String batchId,
            @PathVariable String recordId,
            @RequestBody JsonNode payload,
            @AuthenticationPrincipal JwtUser currentUser
    ) {
        return ApiResponse.ok(
                "已通过资料已删除",
                agentClient.deleteApprovedKnowledgeRecord(
                        batchId,
                        recordId,
                        payload,
                        reviewer(currentUser)
                )
        );
    }

    @PostMapping("/batches/{batchId}/reject")
    public ApiResponse<JsonNode> rejectBatch(
            @PathVariable String batchId,
            @RequestBody JsonNode payload,
            @AuthenticationPrincipal JwtUser currentUser
    ) {
        return ApiResponse.ok(
                "知识批次已驳回",
                agentClient.rejectKnowledgeBatch(batchId, payload, reviewer(currentUser))
        );
    }

    @PostMapping("/batches/{batchId}/reopen")
    public ApiResponse<JsonNode> reopenBatch(
            @PathVariable String batchId,
            @AuthenticationPrincipal JwtUser currentUser
    ) {
        return ApiResponse.ok(
                "知识批次已恢复审核",
                agentClient.reopenKnowledgeBatch(batchId, reviewer(currentUser))
        );
    }

    private String reviewer(JwtUser currentUser) {
        return currentUser == null ? "admin" : currentUser.username();
    }
}
