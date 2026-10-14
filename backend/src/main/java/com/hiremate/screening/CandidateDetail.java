package com.hiremate.screening;

import com.hiremate.apply.ApplicantDocument;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.List;

/** 지원자 카드 (STG-06). 문서 Viewer와 메모를 함께 준다. */
public record CandidateDetail(CandidateRow row, String email, String phone, Instant submittedAt,
        @Schema(nullable = true) String certificates, List<ApplicantDocument> documents, String memo) {
}
