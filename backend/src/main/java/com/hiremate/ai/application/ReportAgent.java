package com.hiremate.ai.application;

import java.util.Optional;
import java.util.UUID;

/**
 * Report Agent. 전형 결과 · 지원자 비교 · 채용 최종 리포트의 부품 설계서를 쓴다.
 *
 * <p>stub은 설계서를 바로 돌려준다. remote는 작업을 대기열(job 모듈)에 넣고 빈 값을 돌려주며, AI 워커가 쓴 설계서는
 * {@link ReportResults}가 저장한다.
 */
public interface ReportAgent {

    /** 대기열 작업 유형. ai 서버 경로(/agents/report/compose)와 같다. 작업 대상은 리포트 ID다. */
    String COMPOSE_JOB = "report/compose";

    /**
     * 전형 결과 · 지원자 비교 · 최종 리포트의 부품 설계서를 만든다. stub은 바로 돌려주고, remote는 작업을 넣고 빈 값을
     * 돌려준다. AI 워커의 결과는 {@link ReportResults}가 reportId 리포트에 저장한다.
     */
    Optional<ComposedReport> compose(UUID reportId, ReportBundle bundle);

    /**
     * 서류 전형 분포 해설. 화면이 기다리는 요청이라 대기열을 거치지 않고 바로 부른다 (ai 서버 경로 /agents/report/explain).
     * 지원자 개인 정보 없이 숫자와 항목 글만 보낸다.
     */
    DistributionNote explain(ReportDistribution.ForAi distribution);
}
