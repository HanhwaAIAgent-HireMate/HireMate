package com.hiremate.ai.application;

import com.hiremate.apply.ApplicantDetail;
import com.hiremate.apply.ApplicationAnalysis;
import com.hiremate.posting.PostingContent;
import com.hiremate.posting.ScreeningRubric;
import java.util.Optional;

/**
 * Application Agent. 제출 자료를 공고의 자격요건과 우대 사항에 맞춰 보고 지원자 요약과 서류 점수를 매긴다.
 * 결정은 하지 않는다. 근거가 부족하면 점수를 보류한다.
 *
 * <p>stub은 결과를 바로 돌려준다. remote는 분석 작업을 대기열(job 모듈)에 넣고 빈 값을 돌려주며, AI 워커가 끝낸 결과는
 * {@link ApplicationAnalysisResults}가 기록한다.
 */
public interface ApplicationAgent {

    /** 대기열 작업 유형. ai 서버 경로(/agents/application/analyze)와 같다. */
    String ANALYZE_JOB = "application/analyze";

    Optional<ApplicationAnalysis> analyze(ApplicantDetail applicant, PostingContent posting, ScreeningRubric rubric);
}
