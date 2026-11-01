package com.hiremate.ai.application;

import com.hiremate.company.Talent;
import java.util.List;
import java.util.UUID;

/** 지원자 한 명의 인재상 판정 요청. ai 서버는 지원 접수 때 저장한 분석을 읽고 판정한다. */
public record TalentFitRequest(UUID companyId, UUID recruitmentId, UUID applicationId, List<Talent> talents) {

    public TalentFitRequest {
        talents = talents == null ? List.of() : List.copyOf(talents);
    }
}
