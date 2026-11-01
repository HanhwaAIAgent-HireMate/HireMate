package com.hiremate.ai.application;

import com.hiremate.company.CompanyProfileChanged;
import com.hiremate.company.CompanyService;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

/**
 * 회사 소개 · 조직 문화 글이 바뀌면 글에서 인재상 요소를 다시 뽑아 둔다. 설정의 인재상과 합쳐 표 보기 · 인재상 판정 ·
 * 인재상 포함 정렬에 쓴다. 실패하면 설정의 인재상만 쓴다.
 */
@Component
class CompanyFactorListener {

    private static final Logger log = LoggerFactory.getLogger(CompanyFactorListener.class);

    private final CandidateAnalyst analyst;
    private final CompanyService companies;

    CompanyFactorListener(CandidateAnalyst analyst, CompanyService companies) {
        this.analyst = analyst;
        this.companies = companies;
    }

    @ApplicationModuleListener
    void on(CompanyProfileChanged event) {
        try {
            CompanyFactors factors = event.text().isBlank() ? new CompanyFactors(List.of())
                    : analyst.factors(event.text());
            companies.recordCultureFactors(event.companyId(), event.text(), factors.items());
        } catch (RuntimeException exception) {
            log.warn("Company factors for {} could not be read: {}", event.companyId(), exception.getMessage());
        }
    }
}
