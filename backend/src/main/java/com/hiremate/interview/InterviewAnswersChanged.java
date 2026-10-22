package com.hiremate.interview;

import java.util.UUID;

/** 면접관이 답변을 기록하거나 고쳤다 (답변을 기록한 질문을 지운 경우도 같다). Interview Agent가 답변을 다시 정리한다 (FR-28). */
public record InterviewAnswersChanged(UUID companyId, UUID stageId, UUID applicationId) {
}
