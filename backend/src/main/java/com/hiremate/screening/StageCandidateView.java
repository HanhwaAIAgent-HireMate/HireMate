package com.hiremate.screening;

import com.hiremate.recruit.StageType;
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.util.UUID;

/** 한 지원자의 전형별 결정 · 점수 · 메모. */
public record StageCandidateView(UUID stageId, String stageName, StageType stageType, Decision decision,
        @Schema(nullable = true) Decision finalResult, @Schema(nullable = true) BigDecimal score, String memo) {

    /** 면접관에게 보낼 이번 전형 결과: 결정과 최종 결과를 뺀다. 점수 · 메모는 그대로다. */
    public StageCandidateView hideDecision() {
        return new StageCandidateView(stageId, stageName, stageType, Decision.PENDING, null, score, memo);
    }
}
