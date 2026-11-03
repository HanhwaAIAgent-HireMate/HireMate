package com.hiremate.posting;

import java.util.Set;
import java.util.UUID;

/**
 * 지원서를 받을 공고. 공고에서 필수로 정한 추가 서류도 지원서의 필수 항목이 된다 (FR-07).
 * blind는 블라인드 채용이다. 켜져 있으면 서류 본문의 학교 이름을 가려 저장한다 (SchoolNames).
 */
public record ApplicationTarget(UUID postingId, UUID recruitmentId, UUID companyId, String companyName,
        String postingTitle, Set<DocumentType> requiredExtras, boolean blind) {
}
