package com.hiremate.company;

import java.util.List;
import java.util.UUID;

/** 회사 소개 설정. 공고의 회사 소개 · 복지와 AI 분석의 인재상 기준으로 쓴다. */
public record CompanyProfile(UUID companyId, String name, String intro, String culture, List<Talent> talents,
        List<String> benefits) {
}
