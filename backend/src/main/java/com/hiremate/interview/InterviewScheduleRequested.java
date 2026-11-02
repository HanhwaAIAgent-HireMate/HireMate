package com.hiremate.interview;

import java.util.UUID;

/** HR의 결과 확정 또는 재시도 요청. 메일을 보내거나 전형 상태를 바꾸지 않는다. */
public record InterviewScheduleRequested(UUID companyId, UUID previousStageId) {
}
