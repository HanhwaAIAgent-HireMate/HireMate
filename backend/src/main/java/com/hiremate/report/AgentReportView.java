package com.hiremate.report;

import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.UUID;

/**
 * Report Agent 리포트 한 건. bundle · result는 JSON 글자 그대로다 (ai 모듈이 화면 응답으로 바꾼다).
 *
 * @param result 다 쓰기 전이거나 실패했으면 null
 */
public record AgentReportView(UUID id, UUID recruitmentId, UUID stageId, AgentReportKind kind,
        AgentReportStatus status, String focus, boolean brief, String bundle, @Schema(nullable = true) String result,
        @Schema(nullable = true) String error, Instant createdAt, @Schema(nullable = true) Instant finishedAt) {
}
