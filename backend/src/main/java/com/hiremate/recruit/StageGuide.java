package com.hiremate.recruit;

import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDate;
import java.time.LocalTime;

/**
 * 전형 안내. 앞 전형의 다음 전형 안내 메일에 붙는다. 정하지 않은 일정 · 시각 · 진행 방식은 null, 비어 있는 글 칸은 빈 문자열이다.
 * time은 면접이 아닌 전형(평가 · 시험)의 시작 시각이다. 면접은 지원자마다 배정한 시간을 쓰므로 비워 둔다.
 * 장소는 온라인이면 접속 링크다. note는 기타 안내로, 한 줄에 하나씩 쓴다.
 */
public record StageGuide(@Schema(nullable = true) LocalDate schedule,
        @Schema(nullable = true, type = "string", example = "14:00:00") LocalTime time,
        @Schema(nullable = true) GuideMethod method, String place, String preparation, String note) {

    public static final StageGuide EMPTY = new StageGuide(null, null, null, "", "", "");

    public StageGuide {
        place = clean(place);
        preparation = clean(preparation);
        note = clean(note);
    }

    /** 시각을 정하지 않은 안내. */
    public StageGuide(LocalDate schedule, GuideMethod method, String place, String preparation, String note) {
        this(schedule, null, method, place, preparation, note);
    }

    /** 시각을 뺀 안내. 면접은 지원자마다 시간을 배정해 안내에 시각을 두지 않는다. */
    public StageGuide withoutTime() {
        return new StageGuide(schedule, null, method, place, preparation, note);
    }

    /** 입력한 칸이 하나라도 있는지. is로 시작하면 JSON 응답에 칸으로 나가서 has로 쓴다. */
    public boolean hasContent() {
        return !(schedule == null && time == null && method == null && place.isEmpty() && preparation.isEmpty()
                && note.isEmpty());
    }

    private static String clean(String value) {
        return value == null ? "" : value.strip();
    }
}
