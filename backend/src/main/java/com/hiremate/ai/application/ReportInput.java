package com.hiremate.ai.application;

import com.hiremate.report.ReportContent;
import java.util.List;

/**
 * 리포트를 쓰는 데 필요한 확정 결과.
 *
 * @param finalists 최종 합격자 이름과 분석 근거
 * @param undecided 전형마다 결정하지 않아 불합격으로 확정된 인원
 */
public record ReportInput(String title, long applicantCount, List<ReportContent.ReportStage> stages,
        List<FinalistInput> finalists, List<Long> undecided) {

    public record FinalistInput(String name, List<CandidateAnalysis.Finding> notable, List<String> memos) {
    }
}
