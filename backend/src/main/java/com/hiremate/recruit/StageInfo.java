package com.hiremate.recruit;

import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.UUID;

public record StageInfo(UUID id, UUID recruitmentId, int seq, String name, StageType type, StageStatus status,
        Instant confirmedAt, String confirmedByName, Instant doneAt, StageGuide guide,
        @Schema(nullable = true, requiredMode = Schema.RequiredMode.NOT_REQUIRED) StageIcon icon) {
    public StageInfo(UUID id, UUID recruitmentId, int seq, String name, StageType type, StageStatus status,
            Instant confirmedAt, String confirmedByName, Instant doneAt, StageGuide guide) {
        this(id, recruitmentId, seq, name, type, status, confirmedAt, confirmedByName, doneAt, guide, null);
    }
}
