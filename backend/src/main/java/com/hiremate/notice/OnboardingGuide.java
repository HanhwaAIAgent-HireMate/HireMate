package com.hiremate.notice;

/**
 * 최종 합격 안내에 붙는 입사 안내. 입사일은 최종 합격자를 정한 뒤에 정해져, 공고가 아니라 보낼 때 안내 화면에서 쓴다.
 * 비어 있는 칸은 빈 문자열이다. note는 기타 안내로, 한 줄에 하나씩 쓴다.
 */
public record OnboardingGuide(String startDate, String place, String documents, String preparation, String note) {

    public static final OnboardingGuide EMPTY = new OnboardingGuide("", "", "", "", "");

    public OnboardingGuide {
        startDate = clean(startDate);
        place = clean(place);
        documents = clean(documents);
        preparation = clean(preparation);
        note = clean(note);
    }

    /** 입력한 칸이 하나라도 있는지. is로 시작하면 JSON 응답에 칸으로 나가서 has로 쓴다. */
    public boolean hasContent() {
        return !(startDate.isEmpty() && place.isEmpty() && documents.isEmpty() && preparation.isEmpty()
                && note.isEmpty());
    }

    private static String clean(String value) {
        return value == null ? "" : value.strip();
    }
}
