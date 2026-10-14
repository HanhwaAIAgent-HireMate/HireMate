package com.hiremate.recruit;

import java.util.UUID;

/** 마지막 전형을 종료해 채용이 끝났다. 리포트 생성이 이 이벤트를 받는다. */
public record RecruitmentClosed(UUID recruitmentId, UUID companyId) {
}
