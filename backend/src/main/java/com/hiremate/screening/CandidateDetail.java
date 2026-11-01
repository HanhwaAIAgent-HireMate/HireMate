package com.hiremate.screening;

import com.hiremate.apply.ApplicantDocument;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.List;

/** 지원자 카드 (STG-06). 문서 Viewer와 메모를 함께 준다. */
public record CandidateDetail(CandidateRow row, String email, String phone, Instant submittedAt,
        @Schema(nullable = true) String certificates, List<ApplicantDocument> documents, String memo) {

    /** 면접관에게 보낼 카드: 이번 전형의 결정을 뺀다. 메모는 그대로 보인다. */
    public CandidateDetail hideDecision() {
        return new CandidateDetail(row.hideDecision(), email, phone, submittedAt, certificates, documents, memo);
    }
}
