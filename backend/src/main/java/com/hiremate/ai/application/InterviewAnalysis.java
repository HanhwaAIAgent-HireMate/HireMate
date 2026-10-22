package com.hiremate.ai.application;

import java.util.List;
import java.util.UUID;

/**
 * 면접 답변 분석 (FR-28). 질문마다 답변에서 확인된 점과 아직 확인 안 된 점을 정리한다.
 * 답변 원문은 interview 모듈에 그대로 두고, 이 레코드는 AI 해석만 담는다. 합격 · 불합격 의견은 담지 않는다.
 *
 * @param answers 질문마다 하나. 질문 순서와 같다
 */
public record InterviewAnalysis(List<Answer> answers, String agent, boolean stub) {

    /** 질문 하나의 확인 상태. */
    public enum Status {
        /** 질문이 확인하려던 것이 답변에 구체적으로 나왔다. */
        CONFIRMED,
        /** 일부만 나왔다. */
        PARTIAL,
        /** 답변은 있지만 확인하려던 것이 나오지 않았다. */
        NOT_CONFIRMED,
        /** 답변 기록이 없다. */
        NO_ANSWER
    }

    /**
     * @param confirmed 확인된 점. quote는 답변 원문에 실제로 있는 구절만 남는다
     * @param unconfirmed 다음 면접에서 이어서 물을 점
     */
    public record Answer(UUID questionId, Status status, List<Point> confirmed, List<String> unconfirmed) {
    }

    public record Point(String point, String quote) {
    }
}
