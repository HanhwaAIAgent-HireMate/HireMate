package com.hiremate.ai.infra;

import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.posting.PostingContent;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class StubApplicationAgentTests {

    private static final PostingContent POSTING = new PostingContent("백엔드 개발자", "", "", "", "", "",
            List.of("결제 시스템 개발"), List.of("Java Spring 경험"), List.of("정산 경험"), List.of());

    @Test
    @DisplayName("이력서에 적힌 경력 연수와 첫 회사 이름을 찾는다")
    void readsCareerAndCompany() {
        String resume = "경력\nOO카드 결제플랫폼팀 2021.03 – 현재\nOO시스템 2018.01 - 2021.02";

        assertThat(StubApplicationAgent.careerYears(resume)).isGreaterThanOrEqualTo(5);
        assertThat(StubApplicationAgent.lastCompany(resume)).isEqualTo("OO카드");
        assertThat(StubApplicationAgent.careerYears("저는 경력 6년 차 개발자입니다")).isEqualTo(6);
        assertThat(StubApplicationAgent.careerYears("신입 지원자입니다")).isZero();
    }
}
