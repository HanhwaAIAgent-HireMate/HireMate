package com.hiremate.apply;

import java.util.UUID;

/** 지원서가 접수됐다. Application Agent가 이 이벤트로 지원 자료를 분석한다 (FR-08). */
public record ApplicationSubmitted(UUID applicationId, UUID recruitmentId, UUID companyId) {
}
