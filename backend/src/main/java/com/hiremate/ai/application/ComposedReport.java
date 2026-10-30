package com.hiremate.ai.application;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;
import tools.jackson.databind.JsonNode;

/**
 * Report Agent 결과 (ai의 ComposedReport). spec은 화면과 PDF가 묶음과 함께 그리는 부품 설계서로, backend는 내용을 읽지 않고
 * 그대로 저장해 넘긴다.
 *
 * @param skills Report Agent가 읽은 스킬. 화면의 실행 기록 칩에 쓴다
 * @param specialists 근거 확인을 맡긴 분석 Agent
 * @param fallback 모델 설계서가 검사를 통과하지 못해 코드가 만든 기본 구성을 썼는가
 * @param bundle Agent가 실제로 읽은 묶음. ai가 분석 판정 · 근거를 붙였다. 개발용 Agent는 null이다. 워커 결과에서만 읽고
 *     저장할 때 묶음 칸으로 옮기므로 화면 API에는 없다 (화면은 ReportPayload.bundle을 쓴다)
 */
public record ComposedReport(JsonNode spec, List<String> skills, List<String> specialists, boolean fallback,
        @Schema(hidden = true) ReportBundle bundle) {

    /** 저장할 결과. 묶음은 리포트의 묶음 칸에 따로 둔다. */
    public ComposedReport withoutBundle() {
        return new ComposedReport(spec, skills, specialists, fallback, null);
    }
}
