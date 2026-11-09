package com.hiremate.apply;

import java.util.UUID;

/**
 * 지원서의 서류가 모두 정제를 마쳤다 (완료 또는 실패). Application Agent가 이 이벤트로 지원 자료를 분석한다. 정제를 마친 서류는 정제
 * 문서를 펼친 글로, 정제에 실패한 서류는 PDF에서 추출한 글로 분석한다 (ApplicantDocument.text).
 */
public record ApplicationDocumentsNormalized(UUID applicationId, UUID recruitmentId, UUID companyId) {
}
