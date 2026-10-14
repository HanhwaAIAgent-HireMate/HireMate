package com.hiremate.report;

import java.util.List;

/**
 * 최종 채용 리포트 (FR-31). 차트 대시보드가 아닌 요약 문서이며 채용 상태를 바꾸지 않는다.
 */
public record ReportContent(String summary, long applicantCount, long finalCount, List<ReportStage> stages,
        List<Finalist> finalists, List<String> notes) {

    public record ReportStage(String name, long target, long pass, long fail) {
    }

    /** 최종 합격자와 판단 근거. 근거마다 출처를 붙인다. */
    public record Finalist(String name, String reason, List<String> sources) {
    }
}
