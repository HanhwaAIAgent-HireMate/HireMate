package com.hiremate.interview;

/**
 * Chat의 면접 질문 교체에서 지우지 않고 남긴 질문 수.
 *
 * @param manual 담당자가 직접 넣은 질문
 * @param answered 답변을 기록한 AI 질문
 */
public record KeptQuestions(int manual, int answered) {

    public boolean any() {
        return manual > 0 || answered > 0;
    }
}
