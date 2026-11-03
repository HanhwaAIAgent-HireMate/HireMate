package com.hiremate.ai.application;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;

/**
 * 지원자 한 명의 인재상 판정. items는 회사 설정의 인재상과 같은 순서다.
 *
 * @param items 인재상마다 하나
 * @param agent 판정한 Agent 이름
 * @param stub 개발용 응답이면 true
 */
public record TalentFit(List<Match> items, String agent, boolean stub) {

    public TalentFit {
        items = items == null ? List.of() : List.copyOf(items);
    }

    /**
     * 맞는 정도. 본인 경험과 정량 지표가 함께 있으면 HIGH, 경험만 있으면 MID, 서류에서 경험이 확인되지 않으면 LOW다.
     * UNKNOWN(확인 필요)은 분석이 없거나 근거를 맞춰 보지 못해 판정하지 못한 경우다.
     */
    public enum Level {
        HIGH, MID, LOW, UNKNOWN
    }

    /**
     * 인재상 하나의 판정.
     *
     * @param evidence 지원자가 무엇을 했는지 짧게. 확인 필요면 비어 있다
     * @param reason 판정 이유 한 문장
     * @param quote 근거가 된 원문 문장
     * @param metric 상일 때 근거의 정량 지표(원문 그대로). 아니면 비어 있다
     */
    public record Match(String title, Level level, String evidence, String reason,
            @Schema(nullable = true) String quote, String metric) {

        public Match {
            // 지표를 담기 전에 저장한 판정에는 값이 없다
            metric = metric == null ? "" : metric;
        }
    }
}
