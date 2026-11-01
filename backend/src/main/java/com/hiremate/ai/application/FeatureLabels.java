package com.hiremate.ai.application;

import java.util.List;

/** 표 보기의 열 이름. 요청한 평가 기준 · 인재상 문장과 같은 순서의 짧은 키워드다 (예: '인성을 중요시한다' → '인성'). */
public record FeatureLabels(List<String> labels) {

    public FeatureLabels {
        labels = labels == null ? List.of() : List.copyOf(labels);
    }
}
