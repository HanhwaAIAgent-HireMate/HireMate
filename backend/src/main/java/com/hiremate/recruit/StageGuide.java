package com.hiremate.recruit;

import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDate;

/**
 * 전형 안내. 앞 전형의 다음 전형 안내 메일에 붙는다. 정하지 않은 일정 · 진행 방식은 null, 비어 있는 글 칸은 빈 문자열이다.
 * 장소는 온라인이면 접속 링크다. note는 기타 안내로, 한 줄에 하나씩 쓴다 (예: 시작 시간).
 */
public record StageGuide(@Schema(nullable = true) LocalDate schedule, @Schema(nullable = true) GuideMethod method,
        String place, String preparation, String note) {

    public static final StageGuide EMPTY = new StageGuide(null, null, "", "", "");

    public StageGuide {
        place = clean(place);
        preparation = clean(preparation);
        note = clean(note);
    }

    /** 입력한 칸이 하나라도 있는지. is로 시작하면 JSON 응답에 칸으로 나가서 has로 쓴다. */
    public boolean hasContent() {
        return !(schedule == null && method == null && place.isEmpty() && preparation.isEmpty() && note.isEmpty());
    }

    private static String clean(String value) {
        return value == null ? "" : value.strip();
    }
}
