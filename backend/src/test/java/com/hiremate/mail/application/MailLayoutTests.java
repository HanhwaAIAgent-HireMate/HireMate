package com.hiremate.mail.application;

import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.mail.MailBrand;
import com.hiremate.mail.MailBrand.GuideBox;
import com.hiremate.mail.MailBrand.Header;
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
    @DisplayName("띠 머리는 대표 색 띠 위에 회사 이름을 쓰고, 띠가 밝으면 흰 글자 대신 진한 글자를 쓴다")
    void bandHeaderKeepsNameReadable() {
        MailContent content = new MailContent("예시 기업", "", List.of(), "", "발신 전용");

        String dark = MailLayout.html("결과 안내", content, look("#1e3a5f", Header.BAND, GuideBox.FILL, null, null));
        String light = MailLayout.html("결과 안내", content, look("#fde68a", Header.BAND, GuideBox.FILL, null, null));
        String logo = MailLayout.html("결과 안내", content,
                look("#1e3a5f", Header.BAND, GuideBox.FILL, "cid:company-logo", null));

        assertThat(dark).contains("padding:18px 32px;background:#1e3a5f;", "color:#ffffff;\">예시 기업</span>")
                .doesNotContain("height:4px;");
        assertThat(light).contains("color:#1f2328;\">예시 기업</span>");
        assertThat(logo).containsSubsequence("background:#ffffff;border-radius:6px;", "<img src=\"cid:company-logo\"",
                "height=\"32\"");
    }

    @Test
    @DisplayName("가운데 머리는 로고를 가운데에 두고, 배너 머리는 배너 그림을 두며 그림이 없으면 띠로 그린다")
    void centerAndBannerHeaders() {
        MailContent content = new MailContent("예시 기업", "", List.of(), "", "발신 전용");

        String center = MailLayout.html("결과 안내", content,
                look(COLOR, Header.CENTER, GuideBox.FILL, "cid:company-logo", null));
        String banner = MailLayout.html("결과 안내", content,
                look(COLOR, Header.BANNER, GuideBox.FILL, "cid:company-logo", "cid:company-banner"));
        String noBanner = MailLayout.html("결과 안내", content, look(COLOR, Header.BANNER, GuideBox.FILL, null, null));

        assertThat(center).contains("align=\"center\"", "text-align:center;", "display:inline-block;height:40px;");
        assertThat(banner).contains("<img src=\"cid:company-banner\" alt=\"예시 기업\" width=\"600\"")
                .doesNotContain("cid:company-logo");
        assertThat(noBanner).contains("padding:18px 32px;background:" + COLOR + ";").doesNotContain("<img");
    }

    @Test
    @DisplayName("안내 상자 제목은 보조 색이고, 테두리 상자는 보조 색 테두리, 표는 상자 없이 보조 색 막대로 그린다")
    void guideBoxesUseAccent() {
        MailContent content = new MailContent("예시 기업", "",
                List.of(new MailContent.Guide("안내", "1차 면접 안내", List.of(new MailContent.Item("일정", "11월 5일")),
                        List.of())), "", "발신 전용");

        String fill = MailLayout.html("결과 안내", content, look(GuideBox.FILL));
        String outline = MailLayout.html("결과 안내", content, look(GuideBox.OUTLINE));
        String rows = MailLayout.html("결과 안내", content, look(GuideBox.ROWS));

        assertThat(fill).contains("background:#f6f8fb;", "color:#f97316;\">1차 면접 안내</td>")
                .contains("height:4px;background:#0055a4;");
        assertThat(outline).contains("border:1px solid #f97316;border-radius:8px;background:#ffffff;",
                "color:#f97316;\">1차 면접 안내</td>");
        assertThat(rows).contains("border-left:4px solid #f97316;", "color:#f97316;\">1차 면접 안내</div>")
                .doesNotContain("background:#f6f8fb;");
    }

    private static MailLayout.Look look(String color, Header header, GuideBox box, String logo, String banner) {
        return new MailLayout.Look(color, color, header, box, logo, banner);
    }

    private static MailLayout.Look look(GuideBox box) {
        return new MailLayout.Look("#0055a4", "#f97316", Header.LINE, box, null, null);
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
