package com.hiremate.mail;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class MailContentTests {

    private static final MailContent CONTENT = new MailContent("예시 기업", "백엔드 개발자",
            List.of(new MailContent.Text("{지원자명}님, 지원해 주셔서 감사합니다."), new MailContent.Text("서류 전형에 합격하셨습니다."),
                    new MailContent.Guide("아래 안내를 확인해 주세요.", "{전형명} 안내",
                            List.of(new MailContent.Item("일정", "11월 5일"), new MailContent.Item("준비 사항", "신분증")),
                            List.of("{지원자명}님은 참석 여부를 알려 주세요"))),
            "예시 기업 인사팀 드림", "본 메일은 발신 전용입니다.");

    @Test
    @DisplayName("텍스트 메일은 본문, 안내, 맺음말, 바닥글을 빈 줄로 잇고 안내는 ■ 제목과 칸 줄로 쓴다")
    void textJoinsPartsWithBlankLines() {
        assertThat(CONTENT.text()).isEqualTo("""
                {지원자명}님, 지원해 주셔서 감사합니다.

                서류 전형에 합격하셨습니다.

                아래 안내를 확인해 주세요.

                ■ {전형명} 안내
                - 일정: 11월 5일
                - 준비 사항: 신분증

                ※ {지원자명}님은 참석 여부를 알려 주세요

                예시 기업 인사팀 드림

                본 메일은 발신 전용입니다.""");
    }

    @Test
    @DisplayName("비어 있는 부분은 넣지 않는다")
    void textSkipsBlankParts() {
        MailContent receipt = new MailContent("예시 기업", "백엔드 개발자",
                List.of(new MailContent.Text("접수되었습니다.")), "", "본 메일은 발신 전용입니다.");

        assertThat(receipt.text()).isEqualTo("접수되었습니다.\n\n본 메일은 발신 전용입니다.");
    }

    @Test
    @DisplayName("변수는 본문과 안내 상자까지 모두 채운다")
    void fillReplacesVariablesEverywhere() {
        MailContent filled = CONTENT.fill(Map.of("{지원자명}", "김하늘", "{전형명}", "코딩테스트"));

        assertThat(filled.text()).contains("김하늘님, 지원해", "■ 코딩테스트 안내", "※ 김하늘님은")
                .doesNotContain("{지원자명}", "{전형명}");
    }
}
