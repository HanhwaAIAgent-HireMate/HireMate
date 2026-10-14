package com.hiremate.ai.application;

import com.hiremate.apply.ApplicantDetail;
import com.hiremate.apply.ApplicationAnalysis;
import com.hiremate.posting.PostingContent;

/** Application Agent. 제출 자료를 분석해 지원자 요약과 서류 점수를 매긴다. 결정은 하지 않는다. */
public interface ApplicationAgent {

    ApplicationAnalysis analyze(ApplicantDetail applicant, PostingContent posting);
}
