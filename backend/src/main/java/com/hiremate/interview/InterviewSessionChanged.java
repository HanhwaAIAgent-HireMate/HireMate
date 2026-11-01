package com.hiremate.interview;

import java.util.UUID;

/** 지원자 한 명의 면접(배정 · 입장 · 진행 상태 · 질문 · 답변 · 의견)이 바뀌었다. 열어 둔 화면에 SSE로 알린다. */
public record InterviewSessionChanged(UUID companyId, UUID stageId, UUID applicationId) {
}
