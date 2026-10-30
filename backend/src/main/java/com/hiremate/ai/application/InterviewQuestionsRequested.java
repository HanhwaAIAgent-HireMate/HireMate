package com.hiremate.ai.application;

import java.util.UUID;

/** 지원자별 자료 준비 요청. 완료된 질문은 다른 지원자를 기다리지 않고 저장한다. */
record InterviewQuestionsRequested(UUID companyId, UUID stageId, UUID applicationId) {
}
