package com.hiremate.screening;

import java.util.List;
import java.util.UUID;

/** 전형이 열리며 지원자가 확정됐다. 전형별 준비 작업은 이 목록에 공통 설정을 적용한다. */
public record StageCandidatesStarted(UUID companyId, UUID stageId, List<UUID> applicationIds) {
}
