package com.hiremate.recruit;

import java.util.UUID;

/** 담당자가 전형 결과를 확정했다. 다음 면접의 합격자 질문을 준비하되 전형을 시작하지는 않는다. */
public record StageConfirmed(UUID stageId, UUID companyId) {
}
