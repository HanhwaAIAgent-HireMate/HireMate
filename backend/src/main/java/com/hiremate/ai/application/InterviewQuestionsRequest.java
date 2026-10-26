package com.hiremate.ai.application;

import com.hiremate.apply.ApplicantDetail;
import com.hiremate.company.CompanyProfile;
import com.hiremate.interview.InterviewView;
import com.hiremate.posting.PostingContent;
import io.swagger.v3.oas.annotations.media.Schema;

/** 면접 질문 생성 요청. questionCount가 없으면 최초 자동 생성 구성을 사용한다. */
public record InterviewQuestionsRequest(ApplicantDetail applicant, PostingContent posting, CandidateAnalysis analysis,
        InterviewView interview, @Schema(nullable = true) CompanyProfile company, @Schema(nullable = true) String focus,
        @Schema(nullable = true) Integer questionCount) {
}
