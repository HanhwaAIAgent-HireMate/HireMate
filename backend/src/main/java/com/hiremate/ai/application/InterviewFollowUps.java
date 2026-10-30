package com.hiremate.ai.application;

import java.util.List;

/**
 * 🎤 꼬리질문 제안 결과.
 *
 * @param needed 답이 충분하면 false다. 이때 화면은 "추가로 확인할 점이 없어요"를 보여 주고 suggestions는 비어 있다
 * @param suggestions 면접관이 고를 꼬리질문 (최대 2개)
 */
public record InterviewFollowUps(boolean needed, List<Suggestion> suggestions) {

    public InterviewFollowUps {
        suggestions = suggestions == null ? List.of() : List.copyOf(suggestions);
    }

    /** 확인할 점이 없다는 결과. */
    public static InterviewFollowUps none() {
        return new InterviewFollowUps(false, List.of());
    }

    /**
     * @param text 꼬리질문 문장
     * @param check 이 질문으로 확인할 점 (확인 포인트). 답변에서 비어 있거나 모호한 부분이다
     */
    public record Suggestion(String text, String check) {
    }
}
