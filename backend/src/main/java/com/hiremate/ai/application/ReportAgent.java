package com.hiremate.ai.application;

import com.hiremate.report.ReportContent;

/** Report Agent. 채용이 끝나면 전형별 인원 · 최종 합격자 근거 · 특이사항을 요약 문서로 쓴다. */
public interface ReportAgent {

    ReportContent write(ReportInput input);
}
