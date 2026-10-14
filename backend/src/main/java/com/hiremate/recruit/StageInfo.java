package com.hiremate.recruit;

import java.time.Instant;
import java.util.UUID;

public record StageInfo(UUID id, UUID recruitmentId, int seq, String name, StageType type, StageStatus status,
        Instant confirmedAt, Instant doneAt) {
}
