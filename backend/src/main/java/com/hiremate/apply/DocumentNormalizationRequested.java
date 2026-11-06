package com.hiremate.apply;

import java.util.UUID;

/** 담당자가 정제 작업을 다시 요청했다. */
public record DocumentNormalizationRequested(UUID applicationId, UUID recruitmentId, UUID companyId) {
}
