package com.hiremate.ai.application;

import com.hiremate.report.ReportContent;
import java.util.List;
import java.util.UUID;

/**
 * 리포트를 쓰는 데 필요한 확정 결과. ai 서버는 기업 · 채용 범위 안에서 합격자의 지원자 프로필(평가 · 면접 분석)을 더 읽는다.
 *
 * @param finalists 최종 합격자 이름과 분석 근거
 * @param undecided 전형마다 결정하지 않아 불합격으로 확정된 인원
 */
public record ReportInput(UUID companyId, UUID recruitmentId, String title, long applicantCount,
        List<ReportContent.ReportStage> stages, List<FinalistInput> finalists, List<Long> undecided) {

    /**
     * 최종 합격자 한 명.
     *
     * @param applicationId ai 서버가 이 합격자의 지원자 프로필을 찾는 지원서 ID
     */
    public record FinalistInput(UUID applicationId, String name, List<CandidateAnalysis.Finding> notable,
            List<String> memos) {
    }
}
