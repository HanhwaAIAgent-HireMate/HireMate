package com.hiremate.apply;

import java.util.UUID;

/**
 * 지원서가 접수됐다. 서류 정제를 시작하고, 정제가 모두 끝나면({@link ApplicationDocumentsNormalized}) Application Agent가 지원
 * 자료를 분석한다 (FR-08). 정제를 하지 않는 stub이면 이 이벤트로 바로 분석한다.
 */
public record ApplicationSubmitted(UUID applicationId, UUID recruitmentId, UUID companyId) {
}
