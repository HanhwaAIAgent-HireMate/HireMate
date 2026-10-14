package com.hiremate.screening;

import com.hiremate.recruit.RecruitmentStatus;
import com.hiremate.recruit.StageStatus;
import com.hiremate.recruit.StageType;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

/** 전형 화면 위쪽(Workflow Stepper · Stage 바)에 필요한 정보. */
public record StageOverview(UUID stageId, String name, StageType type, StageStatus status, boolean last,
        UUID recruitmentId, String recruitmentTitle, RecruitmentStatus recruitmentStatus, UUID postingId,
        long applicantCount, List<StageStep> steps, DecisionCounts counts, long selectedCount, boolean canRestore,
        boolean hasScores, @Schema(nullable = true) Instant confirmedAt) {

    /** Stepper의 전형 한 칸. 시작하지 않은 전형은 대상 인원이 없다. */
    public record StageStep(UUID stageId, String name, StageType type, StageStatus status,
            @Schema(nullable = true) Long targetCount) {
    }

    public record DecisionCounts(long pending, long pass, long fail, long total) {
    }
}
