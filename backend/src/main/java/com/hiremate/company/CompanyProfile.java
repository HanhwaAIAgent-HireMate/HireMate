package com.hiremate.company;

import java.util.List;
import java.util.UUID;

/**
 * 회사 소개 설정. 공고의 회사 소개 · 복지와 AI 분석의 인재상 기준으로 쓴다.
 *
 * @param address 회사 주소. 채용 페이지 맨 아래에 보여 준다. 적지 않았으면 빈 글이다
 */
public record CompanyProfile(UUID companyId, String name, String intro, String culture, List<Talent> talents,
        List<String> benefits, String address) {
}
