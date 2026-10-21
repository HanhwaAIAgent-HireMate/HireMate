package com.hiremate.recruit;

/**
 * 전형 안내. 앞 전형의 다음 전형 안내 메일에 붙는다. 칸은 모두 선택이고 비어 있으면 빈 문자열이다.
 * 끝나는 시간은 일정에 함께 쓴다 (예: "11월 3일(화) 오후 2시~4시").
 */
public record StageGuide(String schedule, String method, String place, String preparation) {

    public static final StageGuide EMPTY = new StageGuide("", "", "", "");

    public StageGuide {
        schedule = clean(schedule);
        method = clean(method);
        place = clean(place);
        preparation = clean(preparation);
    }

    /** 입력한 칸이 하나라도 있는지. is로 시작하면 JSON 응답에 칸으로 나가서 has로 쓴다. */
    public boolean hasContent() {
        return !(schedule.isEmpty() && method.isEmpty() && place.isEmpty() && preparation.isEmpty());
    }

    private static String clean(String value) {
        return value == null ? "" : value.strip();
    }
}
