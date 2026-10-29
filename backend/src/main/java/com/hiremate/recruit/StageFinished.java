package com.hiremate.recruit;

import java.util.UUID;

/** 전형을 종료했다. */
public record StageFinished(UUID stageId, UUID companyId) {
}
