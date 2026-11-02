package com.hiremate.interview;

import java.util.UUID;

/** 면접 변경 알림. applicationId가 없으면 전형 공통 설정의 변경이라 모든 면접 화면에 알린다. */
public record InterviewSessionChanged(UUID companyId, UUID stageId, UUID applicationId) {
}
