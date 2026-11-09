package com.hiremate.posting.application;

import com.hiremate.posting.ScreeningRubric;
import java.util.List;
import java.util.UUID;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 공고 담당이 평가 기준 입력을 만들기 전까지 쓰는 서류 평가 기준 (application.yml의 hiremate.dummy.screening-rubric).
 * 항목 · 필수 표시는 공고에서 정하고(PostingRubric), 이 설정에서는 같은 글의 항목의 유형 · 판정 기준 · 인정 자격증만 쓴다.
 * 여기의 중요 표시와 항목 번호는 쓰지 않는다.
 */
@ConfigurationProperties("hiremate.dummy.screening-rubric")
public record DummyScreeningRubric(String criteriaVersion, int hireCount, List<ScreeningRubric.Criterion> criteria) {

    public DummyScreeningRubric {
        criteria = criteria == null ? List.of() : List.copyOf(criteria);
    }

    public ScreeningRubric of(UUID companyId, UUID recruitmentId) {
        return new ScreeningRubric(companyId, recruitmentId, criteriaVersion, hireCount, criteria);
    }
}
