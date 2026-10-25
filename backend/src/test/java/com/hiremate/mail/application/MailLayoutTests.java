package com.hiremate.mail.application;

import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.mail.MailBrand;
import com.hiremate.mail.MailContent;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class MailLayoutTests {

    private static final String COLOR = MailBrand.DEFAULT_COLOR;

    @Test
    @DisplayName("회사 이름 머리글, 공고명, 제목, 문단, 안내 상자, 맺음말, 바닥글 순서로 그린다")
    void drawsPartsInOrder() {
        MailContent content = new MailContent("예시 기업", "백엔드 개발자",
                List.of(new MailContent.Text("김하늘님, 감사합니다.\n\n합격하셨습니다.\n다음 전형은 면접입니다."),
                        new MailContent.Guide("아래 안내를 확인해 주세요.", "1차 면접 안내",
                                List.of(new MailContent.Item("일정", "11월 5일")), List.of("신분증을 챙겨 주세요"))),
                "예시 기업 인사팀 드림", "본 메일은 발신 전용입니다.");

        String html = MailLayout.html("[예시 기업] 서류 전형 결과 안내", content, COLOR, null);

        assertThat(html).startsWith("<!doctype html>")
                .containsSubsequence(">예시 기업</td>", ">백엔드 개발자</div>", ">서류 전형 결과 안내</div>",
                        ">김하늘님, 감사합니다.</p>", ">합격하셨습니다.<br>다음 전형은 면접입니다.</p>",
                        ">아래 안내를 확인해 주세요.</p>", ">1차 면접 안내</td>", ">일정</td>", ">11월 5일</td>",
                        "※ 신분증을 챙겨 주세요", ">예시 기업 인사팀 드림</p>", ">본 메일은 발신 전용입니다.</td>");
    }

    @Test
    @DisplayName("기업이 고른 색은 머리글 띠, 회사 이름, 안내 상자 제목에 쓰고, 로고가 있으면 회사 이름 대신 로고를 넣는다")
    void usesBrandColorAndLogo() {
        MailContent content = new MailContent("예시 기업", "백엔드 개발자",
                List.of(new MailContent.Guide("안내", "1차 면접 안내", List.of(), List.of())), "", "발신 전용");

        String text = MailLayout.html("[예시 기업] 결과 안내", content, "#0055a4", null);
        String logo = MailLayout.html("[예시 기업] 결과 안내", content, "#0055a4", "cid:company-logo");

        assertThat(text).containsSubsequence("height:4px;background:#0055a4;", "color:#0055a4;\">예시 기업</td>",
                "color:#0055a4;\">1차 면접 안내</td>").doesNotContain("<img", MailBrand.DEFAULT_COLOR);
        assertThat(logo).contains("<img src=\"cid:company-logo\" alt=\"예시 기업\" height=\"40\"")
                .doesNotContain(">예시 기업</td>");
    }

    @Test
    @DisplayName("회사 이름, 본문, 안내의 꺾쇠와 따옴표는 글자로 바꿔 메일 모양이 깨지지 않는다")
    void escapesEveryText() {
        MailContent content = new MailContent("<b>회사</b>", "\"공고\"",
                List.of(new MailContent.Text("<script>alert(1)</script>"),
                        new MailContent.Guide("안내", "<i>면접</i>", List.of(new MailContent.Item("장소", "A&B 빌딩")),
                                List.of())),
                "", "<a href=x>발신 전용</a>");

        String html = MailLayout.html("<제목>", content, COLOR, null);

        assertThat(html).doesNotContain("<script>", "<b>회사", "<i>면접", "<a href=x>")
                .contains("&lt;script&gt;", "&lt;b&gt;회사", "&quot;공고&quot;", "A&amp;B 빌딩", "&lt;제목&gt;");
    }

    @Test
    @DisplayName("큰 제목에 공고명이 이미 있으면 제목 위의 작은 공고명은 빼고, 없으면 보여 준다")
    void dropsCaptionAlreadyInHeading() {
        MailContent content = new MailContent("예시 기업", "백엔드 개발자", List.of(new MailContent.Text("감사합니다.")),
                "", "발신 전용");

        String receipt = MailLayout.html("[예시 기업] 백엔드 개발자 지원이 접수되었습니다", content, COLOR, null);
        String notice = MailLayout.html("[예시 기업] 서류 전형 결과 안내", content, COLOR, null);

        assertThat(receipt).doesNotContain(">백엔드 개발자</div>").contains(">백엔드 개발자 지원이 접수되었습니다</div>");
        assertThat(notice).contains(">백엔드 개발자</div>", ">서류 전형 결과 안내</div>");
    }

    @Test
    @DisplayName("본문 위 제목은 메일 제목에서 앞의 [회사명]을 뺀 것이다")
    void headingDropsSubjectTag() {
        assertThat(MailLayout.heading("[예시 기업] 최종 합격 안내")).isEqualTo("최종 합격 안내");
        assertThat(MailLayout.heading("최종 합격 안내")).isEqualTo("최종 합격 안내");
        assertThat(MailLayout.heading("[예시 기업]")).isEqualTo("[예시 기업]");
    }
}
