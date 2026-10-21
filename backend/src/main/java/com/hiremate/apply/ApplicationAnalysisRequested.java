package com.hiremate.apply;

import java.util.UUID;

/** 분석에 실패한 지원서를 담당자가 다시 분석해 달라고 했다 (NFR-05). Application Agent가 다시 분석한다. */
public record ApplicationAnalysisRequested(UUID applicationId, UUID recruitmentId, UUID companyId) {
}
