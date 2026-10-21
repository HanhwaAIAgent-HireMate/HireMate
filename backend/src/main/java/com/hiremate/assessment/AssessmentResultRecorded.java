package com.hiremate.assessment;

import java.util.UUID;

/** 지원자 한 명의 평가 결과(점수 · 파일 · URL · 메모)가 등록되거나 바뀌었다. Assessment Agent가 이 이벤트로 분석한다. */
public record AssessmentResultRecorded(UUID companyId, UUID recruitmentId, UUID stageId, UUID applicationId) {
}
