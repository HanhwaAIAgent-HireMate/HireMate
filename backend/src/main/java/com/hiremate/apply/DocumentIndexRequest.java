package com.hiremate.apply;

import java.util.UUID;

/** 저장된 정제 문서의 검색 범위와 버전. */
public record DocumentIndexRequest(UUID companyId, UUID recruitmentId, UUID applicationId, int revision,
        boolean blind, String applicantName, NormalizedDocument document) {
}
