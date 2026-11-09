package com.hiremate.posting;

import java.util.List;

/**
 * 서류 필수 조건. HR이 공고 작성 화면에서 '필수'로 표시한 자격 요건 · 우대 사항 줄의 글이다.
 * 공고에 있는 줄만 남는다. 줄을 지우거나 AI 수정안으로 줄이 바뀌면 그 줄의 표시는 빠진다.
 * 지원자에게는 보여 주지 않는다. 서류 평가 기준의 중요(필수) 표시가 되어 AI 분석과 서류 전형 기준선에 쓰인다 (PostingRubric).
 */
public record RequiredCriteria(List<String> qualifications, List<String> preferred) {

    public static final RequiredCriteria NONE = new RequiredCriteria(List.of(), List.of());

    public RequiredCriteria {
        qualifications = qualifications == null ? List.of() : List.copyOf(qualifications);
        preferred = preferred == null ? List.of() : List.copyOf(preferred);
    }

    /** 공고 본문에 있는 줄만 남긴다. 같은 줄은 하나만 둔다. */
    public RequiredCriteria within(PostingContent content) {
        return new RequiredCriteria(
                qualifications.stream().filter(content.qualifications()::contains).distinct().toList(),
                preferred.stream().filter(content.preferred()::contains).distinct().toList());
    }
}
