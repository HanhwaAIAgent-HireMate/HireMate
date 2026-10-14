package com.hiremate.screening;

import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.util.UUID;

/** 한 지원자의 전형별 결정 · 점수 · 메모. */
public record StageCandidateView(UUID stageId, Decision decision, @Schema(nullable = true) Decision finalResult,
        @Schema(nullable = true) BigDecimal score, String memo) {
}
