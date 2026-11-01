package com.hiremate.company;

import java.util.UUID;

/**
 * 회사 소개 · 조직 문화 글이 바뀌었다. AI가 글에서 인재상 요소를 다시 뽑는다.
 *
 * @param text 회사 소개와 조직 문화를 이은 글. 요소를 기록할 때 같은 글인지 확인하는 데 쓴다
 */
public record CompanyProfileChanged(UUID companyId, String text) {
}
