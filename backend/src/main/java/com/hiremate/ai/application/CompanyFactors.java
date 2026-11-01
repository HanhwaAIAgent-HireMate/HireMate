package com.hiremate.ai.application;

import com.hiremate.company.Talent;
import java.util.List;

/** 회사 소개 · 조직 문화 글에서 뽑은 인재상 요소. title은 짧은 낱말, description은 요소가 나온 원문 문장이다. */
public record CompanyFactors(List<Talent> items) {

    public CompanyFactors {
        items = items == null ? List.of() : List.copyOf(items);
    }
}
