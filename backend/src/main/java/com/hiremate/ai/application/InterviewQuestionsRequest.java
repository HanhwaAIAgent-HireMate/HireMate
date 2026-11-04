package com.hiremate.ai.application;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.hiremate.apply.ApplicantDetail;
import com.hiremate.company.CompanyProfile;
import com.hiremate.interview.InterviewView;
import com.hiremate.posting.PostingContent;
import io.swagger.v3.oas.annotations.media.Schema;

/**
 * 면접 질문 생성 요청. questionCount가 없으면 최초 자동 생성 구성을 사용한다. ncs는 Chat 요청에서 NCS를 참고할 때만 담고, 없으면
 * 본문에 넣지 않는다(ai는 없으면 SKIP으로 읽는다).
 */
public record InterviewQuestionsRequest(ApplicantDetail applicant, PostingContent posting, CandidateAnalysis analysis,
        InterviewView interview, @Schema(nullable = true) CompanyProfile company, @Schema(nullable = true) String focus,
        @Schema(nullable = true) Integer questionCount, @Schema(nullable = true) InterviewerMemo memo,
        @JsonInclude(JsonInclude.Include.NON_NULL) @Schema(nullable = true) NcsUse ncs) {

    public InterviewQuestionsRequest(ApplicantDetail applicant, PostingContent posting, CandidateAnalysis analysis,
            InterviewView interview, CompanyProfile company, String focus, Integer questionCount,
            InterviewerMemo memo) {
        this(applicant, posting, analysis, interview, company, focus, questionCount, memo, null);
    }

    public InterviewQuestionsRequest(ApplicantDetail applicant, PostingContent posting, CandidateAnalysis analysis,
            InterviewView interview, CompanyProfile company, String focus, Integer questionCount) {
        this(applicant, posting, analysis, interview, company, focus, questionCount, null);
    }
}
