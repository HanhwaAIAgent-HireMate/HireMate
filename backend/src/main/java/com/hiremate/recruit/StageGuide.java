package com.hiremate.recruit;

/**
 * 전형 안내. 앞 전형의 다음 전형 안내 메일에 붙는다. 비어 있는 칸은 빈 문자열이다.
 * 끝나는 시간은 일정에 함께 쓴다 (예: "11월 3일(화) 오후 2시~4시"). note는 기타 안내로, 한 줄에 하나씩 쓴다.
 */
public record StageGuide(String schedule, String method, String place, String preparation, String note) {

    public static final StageGuide EMPTY = new StageGuide("", "", "", "", "");

    public StageGuide {
        schedule = clean(schedule);
        method = clean(method);
        place = clean(place);
        preparation = clean(preparation);
        note = clean(note);
    }

    /** 입력한 칸이 하나라도 있는지. is로 시작하면 JSON 응답에 칸으로 나가서 has로 쓴다. */
    public boolean hasContent() {
        return !(schedule.isEmpty() && method.isEmpty() && place.isEmpty() && preparation.isEmpty()
                && note.isEmpty());
    }

    private static String clean(String value) {
        return value == null ? "" : value.strip();
    }
}
