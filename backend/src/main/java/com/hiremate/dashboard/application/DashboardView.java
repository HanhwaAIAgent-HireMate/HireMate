package com.hiremate.dashboard.application;

import com.hiremate.recruit.RecruitmentStatus;
import com.hiremate.recruit.StageStatus;
import com.hiremate.recruit.StageType;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

/** 채용 대시보드 (DSH-01). 상태 탭 인원과 채용별 Workflow. */
public record DashboardView(StatusCounts counts, List<RecruitmentCard> items) {

    public record StatusCounts(long all, long draft, long published, long inProgress, long closed) {
    }

    public record RecruitmentCard(UUID recruitmentId, UUID postingId, String title, RecruitmentStatus status,
            long applicantCount, @Schema(nullable = true) Instant closeAt,
            @Schema(nullable = true) UUID currentStageId, List<DashboardStep> steps, Instant createdAt) {
    }

    /** 끝난 전형은 회색, 진행 중인 전형은 대상 인원과 함께 강조한다. */
    public record DashboardStep(UUID stageId, String name, StageType type, StageStatus status,
            @Schema(nullable = true) Long targetCount) {
    }
}
