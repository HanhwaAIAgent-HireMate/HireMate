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

    /** 맞는 정도. 서류에 근거가 없으면 UNKNOWN(확인 필요)이고 LOW(하)로 바꾸지 않는다. */
    public enum Level {
        HIGH, MID, LOW, UNKNOWN
    }

    /**
     * 인재상 하나의 판정.
     *
     * @param evidence 지원자가 무엇을 했는지 짧게. 확인 필요면 비어 있다
     * @param reason 판정 이유 한 문장
     * @param quote 근거가 된 원문 문장
     */
    public record Match(String title, Level level, String evidence, String reason,
            @Schema(nullable = true) String quote) {
    }
}
