package com.hiremate.recruit;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

public record RecruitmentInfo(UUID id, UUID companyId, String title, RecruitmentStatus status, UUID currentStageId,
        List<StageInfo> stages, Instant createdAt, Instant publishedAt, Instant closedAt) {

    public Optional<StageInfo> stage(UUID stageId) {
        return stages.stream().filter(stage -> stage.id().equals(stageId)).findFirst();
    }

    public boolean isLastStage(UUID stageId) {
        return !stages.isEmpty() && stages.getLast().id().equals(stageId);
    }
}
