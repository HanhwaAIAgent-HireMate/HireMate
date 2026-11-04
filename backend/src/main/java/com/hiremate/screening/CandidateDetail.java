package com.hiremate.screening;

import com.hiremate.apply.ApplicantDocument;
import com.hiremate.apply.OriginalWarning;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.List;

/**
 * 지원자 카드 (STG-06). 문서 Viewer와 메모를 함께 준다.
 * schoolMentions는 블라인드 채용 서류 전형에서 서류에 출신 학교를 쓴 문장이다. 학교 이름은 가린 채로 주고, 감점이나 불합격은
 * HR이 정한다. schoolCleared면 HR이 확인해 블라인드 위반 의심을 해제했다 (해제 취소할 수 있다).
 * originalWarnings는 원본 PDF를 열면 블라인드로 가린 출신 학교 · 학점이 보이는 서류다. 열기 전에 알린다.
 */
public record CandidateDetail(CandidateRow row, String email, String phone, Instant submittedAt,
        @Schema(nullable = true) String certificates, List<ApplicantDocument> documents, String memo,
        List<String> schoolMentions, boolean schoolCleared, List<OriginalWarning> originalWarnings) {

    /** 면접관에게 보낼 카드: 이번 전형의 결정을 뺀다. 메모는 그대로 보인다. */
    public CandidateDetail hideDecision() {
        return new CandidateDetail(row.hideDecision(), email, phone, submittedAt, certificates, documents, memo,
                schoolMentions, schoolCleared, originalWarnings);
    }
}
