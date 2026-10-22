package com.hiremate.ai.application;

import com.hiremate.report.ReportContent;
import java.util.Optional;
import java.util.UUID;

/**
 * Report Agent. 채용이 끝나면 전형별 인원 · 최종 합격자 근거 · 특이사항을 요약 문서로 쓴다.
 *
 * <p>stub은 리포트를 바로 돌려준다. remote는 작업을 대기열(job 모듈)에 넣고 빈 값을 돌려주며, AI 워커가 쓴 리포트는
 * {@link ReportResults}가 저장한다. companyId · recruitmentId는 리포트를 저장할 곳이고 ai 서버에는 input만 보낸다.
 */
public interface ReportAgent {

    /** 대기열 작업 유형. ai 서버 경로(/agents/report/write)와 같다. 작업 대상은 {@link #jobTarget}이다. */
    String WRITE_JOB = "report/write";

    Optional<ReportContent> write(UUID companyId, UUID recruitmentId, ReportInput input);

    /** 리포트 작업의 대상. 결과를 저장할 기업과 채용을 '기업 ID:채용 ID'로 적는다. */
    static String jobTarget(UUID companyId, UUID recruitmentId) {
        return companyId + ":" + recruitmentId;
    }
}
