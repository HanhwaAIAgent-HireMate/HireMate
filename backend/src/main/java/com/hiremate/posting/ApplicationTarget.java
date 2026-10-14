package com.hiremate.posting;

import java.util.Set;
import java.util.UUID;

/** 지원서를 받을 공고. 공고에서 필수로 정한 추가 서류도 지원서의 필수 항목이 된다 (FR-07). */
public record ApplicationTarget(UUID postingId, UUID recruitmentId, UUID companyId, String companyName,
        String postingTitle, Set<DocumentType> requiredExtras) {
}
