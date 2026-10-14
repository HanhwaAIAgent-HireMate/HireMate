package com.hiremate.screening;

import java.util.List;
import java.util.UUID;

/** 확정한 전형 결과. 안내 발송과 리포트가 쓴다. */
public record StageResults(UUID stageId, List<UUID> passed, List<UUID> failed, long undecidedAtConfirm) {
}
