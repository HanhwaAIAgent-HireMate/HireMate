package com.hiremate.ai.application;

import java.util.List;

/**
 * 표 보기의 열. 자격요건 · 우대사항 열의 칸은 지원자 카드의 항목별 판정(criteria)으로, 인재상 열의 칸은 인재상 판정으로 채운다.
 *
 * @param features 자격요건, 우대사항, 인재상 순서
 */
public record CandidateTable(List<Feature> features) {

    public CandidateTable {
        features = features == null ? List.of() : List.copyOf(features);
    }

    /** 열의 묶음. */
    public enum Group {
        QUALIFICATION, PREFERENCE, TALENT
    }

    /** 칸 표기. CONDITION은 O · X, EXPERIENCE는 상 · 중 · 하다. */
    public enum Kind {
        CONDITION, EXPERIENCE
    }

    /**
     * 열 하나.
     *
     * @param id 자격요건 · 우대사항이면 평가 항목 ID(Q-01), 인재상이면 설정 순서로 만든 ID(T-1)
     * @param label 열 이름으로 쓰는 짧은 키워드
     * @param text 원래 문장. 열 이름에 마우스를 올리면 보여 준다
     */
    public record Feature(String id, Group group, Kind kind, String label, String text) {
    }
}
