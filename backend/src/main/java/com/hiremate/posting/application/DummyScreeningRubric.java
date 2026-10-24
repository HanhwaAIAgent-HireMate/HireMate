package com.hiremate.posting.application;

import com.hiremate.posting.ScreeningRubric;
import java.util.List;
import java.util.UUID;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 공고 담당이 평가 기준 입력을 만들기 전까지 쓰는 서류 평가 기준 (application.yml의 hiremate.dummy.screening-rubric).
 * 실제 입력이 생기면 이 설정 대신 공고에 저장한 값을 쓴다.
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
