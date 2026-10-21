package com.hiremate.ai.application;

import com.hiremate.apply.ApplicantDetail;
import com.hiremate.apply.ApplicationAnalysis;
import com.hiremate.posting.PostingContent;
import com.hiremate.posting.ScreeningRubric;

/**
 * Application Agent. 제출 자료를 공고의 자격요건과 우대 사항(NCS 평가 조건)에 맞춰 보고 지원자 요약과 서류 점수를 매긴다.
 * 결정은 하지 않는다. 근거가 부족하면 점수를 보류한다.
 */
public interface ApplicationAgent {

    ApplicationAnalysis analyze(ApplicantDetail applicant, PostingContent posting, ScreeningRubric rubric);
}
