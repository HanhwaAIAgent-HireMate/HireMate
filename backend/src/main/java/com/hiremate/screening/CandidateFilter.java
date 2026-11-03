package com.hiremate.screening;

import java.util.Collection;
import java.util.Set;

/**
 * 전체 지원자 거르기. 결정 상태는 하나라도 맞으면 남고, 평가 항목과 인재상은 고른 것이 모두 표 보기 표기로 O 또는 중
 * 이상이어야 남는다 (조건형은 충족, 경험형은 충족 · 부분 충족, 인재상은 상 · 중). 비어 있는 칸은 거르지 않는다.
 *
 * @param criteria 평가 항목 ID (자격요건 · 우대사항)
 * @param talents 표 보기 인재상 열 ID (T-1, T-2 …)
 */
public record CandidateFilter(Set<Decision> decisions, Set<String> criteria, Set<String> talents) {

    public static final CandidateFilter NONE = new CandidateFilter(Set.of(), Set.of(), Set.of());

    public CandidateFilter {
        decisions = Set.copyOf(decisions);
        criteria = Set.copyOf(criteria);
        talents = Set.copyOf(talents);
    }

    public static CandidateFilter of(Collection<Decision> decisions, Collection<String> criteria,
            Collection<String> talents) {
        return new CandidateFilter(copy(decisions), copy(criteria), copy(talents));
    }

    private static <T> Set<T> copy(Collection<T> values) {
        return values == null ? Set.of() : Set.copyOf(values);
    }
}
