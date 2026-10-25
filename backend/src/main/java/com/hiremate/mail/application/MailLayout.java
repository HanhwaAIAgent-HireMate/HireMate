package com.hiremate.mail.application;

import com.hiremate.mail.MailContent;
import java.util.Arrays;
import java.util.List;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import org.springframework.web.util.HtmlUtils;

/**
 * 메일 HTML. 회사 로고나 이름 머리글, 공고명과 제목, 본문, 안내 상자, 맺음말, 바닥글 순서다.
 * 메일 프로그램은 바깥 CSS와 스크립트를 무시해서 꾸밈은 태그 안에 넣고 배치는 표로 한다.
 * 회사 이름부터 본문까지 모든 글은 이스케이프한다. 지원자 이름이나 AI 본문에 꺾쇠가 있어도 메일 모양이 깨지지 않는다.
 * 기업이 고른 색은 머리글 띠, 회사 이름, 안내 상자 제목에 쓴다.
 */
public final class MailLayout {

    /** 메일에 함께 넣어 보내는 로고의 이름. HTML은 cid:로 가리킨다. */
    public static final String LOGO_CID = "company-logo";
    private static final String TEXT = "#1f2328";
    private static final String MUTED = "#6b7280";
    private static final String LINE = "#e5e7eb";
    private static final String BOX = "#f6f8fb";
    private static final String PAGE = "#f3f4f6";
    private static final String FONT = "'Malgun Gothic','Apple SD Gothic Neo','Noto Sans KR',sans-serif";
    private static final String PARAGRAPH = "margin:0 0 14px;font-size:15px;line-height:1.75;color:" + TEXT + ";";
    private static final Pattern BLANK_LINE = Pattern.compile("\\n\\s*\\n");
    private static final Pattern SUBJECT_TAG = Pattern.compile("^\\s*\\[[^]]*]\\s*");

    private MailLayout() {
    }

    /**
     * 메일 HTML 문서.
     *
     * @param color 기업이 고른 색 (#rrggbb)
     * @param logoSrc 로고 그림 주소. 보낼 때는 cid:, 미리보기에서는 data: 주소다. 로고가 없으면 null이고 회사 이름을 쓴다
     */
    public static String html(String subject, MailContent content, String color, String logoSrc) {
        String heading = heading(subject);
        String caption = caption(content.caption(), heading);
        String blocks = content.blocks().stream().map(block -> block(block, color)).collect(Collectors.joining());
        String closing = content.closing().isBlank() ? ""
                : "<p style=\"margin:18px 0 0;font-size:15px;line-height:1.75;font-weight:bold;color:" + TEXT
                        + ";\">" + lines(content.closing()) + "</p>";
        return """
                <!doctype html>
                <html lang="ko">
                <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <title>%s</title>
                <style>@media (max-width:480px){.hm-pad{padding-left:20px!important;padding-right:20px!important}\
                .hm-label{width:76px!important}}</style>
                </head>
                <body style="margin:0;padding:0;background:%s;">
                <table role="presentation" width="100%%" cellpadding="0" cellspacing="0" \
                style="background:%s;font-family:%s;word-break:keep-all;">
                <tr><td align="center" style="padding:24px 12px;">
                <table role="presentation" width="100%%" cellpadding="0" cellspacing="0" \
                style="max-width:600px;background:#ffffff;border:1px solid %s;border-radius:10px;overflow:hidden;">
                <tr><td style="height:4px;background:%s;font-size:0;line-height:0;">&nbsp;</td></tr>
                <tr>%s</tr>
                <tr><td class="hm-pad" style="padding:22px 32px 6px;">%s
                <div style="font-size:22px;font-weight:bold;line-height:1.4;color:%s;">%s</div>
                </td></tr>
                <tr><td class="hm-pad" style="padding:14px 32px 0;">\
                <div style="height:1px;background:%s;font-size:0;line-height:0;">&nbsp;</div></td></tr>
                <tr><td class="hm-pad" style="padding:22px 32px 30px;">%s%s</td></tr>
                <tr><td class="hm-pad" style="padding:16px 32px 20px;background:#fafafa;border-top:1px solid %s;\
                font-size:12px;line-height:1.7;color:%s;">%s</td></tr>
                </table>
                </td></tr>
                </table>
                </body>
                </html>
                """.formatted(escape(subject), PAGE, PAGE, FONT, LINE, escape(color),
                header(content.sender(), color, logoSrc), caption, TEXT, escape(heading), LINE, blocks, closing, LINE,
                MUTED, lines(content.footer()));
    }

    /** 머리글. 로고가 있으면 왼쪽 위에 높이 40px로, 없으면 회사 이름을 고른 색 글자로 쓴다. */
    private static String header(String sender, String color, String logoSrc) {
        if (logoSrc == null) {
            return "<td class=\"hm-pad\" style=\"padding:20px 32px 0;font-size:16px;font-weight:bold;color:"
                    + escape(color) + ";\">" + escape(sender) + "</td>";
        }
        return "<td class=\"hm-pad\" style=\"padding:20px 32px 0;\"><img src=\"" + escape(logoSrc) + "\" alt=\""
                + escape(sender) + "\" height=\"40\" style=\"display:block;height:40px;width:auto;max-width:220px;"
                + "border:0;\"></td>";
    }

    /** 제목 위의 작은 공고명. 큰 제목에 공고명이 이미 있으면 (접수 확인 메일) 두 번 쓰지 않는다. */
    private static String caption(String caption, String heading) {
        if (caption.isBlank() || heading.contains(caption.strip())) {
            return "";
        }
        return "\n<div style=\"margin:0 0 6px;font-size:13px;color:" + MUTED + ";\">" + escape(caption) + "</div>";
    }

    /** 본문 위의 큰 제목. 메일 제목에서 앞의 [회사명]을 뺀다. 머리글에 회사 이름이 따로 있다. */
    static String heading(String subject) {
        String heading = SUBJECT_TAG.matcher(subject).replaceFirst("");
        return heading.isBlank() ? subject.strip() : heading.strip();
    }

    private static String block(MailContent.Block block, String color) {
        return switch (block) {
            case MailContent.Text text -> paragraphs(text.text());
            case MailContent.Guide guide -> guide(guide, color);
        };
    }

    /** 빈 줄로 나눈 문단마다 p, 문단 안 줄바꿈은 br. */
    private static String paragraphs(String text) {
        return Arrays.stream(BLANK_LINE.split(text.replace("\r\n", "\n")))
                .map(String::strip)
                .filter(paragraph -> !paragraph.isEmpty())
                .map(paragraph -> "<p style=\"" + PARAGRAPH + "\">" + lines(paragraph) + "</p>")
                .collect(Collectors.joining());
    }

    private static String guide(MailContent.Guide guide, String color) {
        StringBuilder rows = new StringBuilder();
        List<MailContent.Item> items = guide.items();
        for (int index = 0; index < items.size(); index++) {
            String border = index == 0 ? "" : "border-top:1px solid " + LINE + ";";
            rows.append("<tr><td class=\"hm-label\" style=\"padding:10px 14px;width:104px;vertical-align:top;")
                    .append("font-size:13px;color:").append(MUTED).append(';').append(border).append("\">")
                    .append(escape(items.get(index).label())).append("</td>")
                    .append("<td style=\"padding:10px 14px;vertical-align:top;font-size:14px;line-height:1.6;color:")
                    .append(TEXT).append(';').append(border).append("\">")
                    .append(lines(items.get(index).value())).append("</td></tr>");
        }
        if (!guide.notes().isEmpty()) {
            rows.append("<tr><td colspan=\"2\" style=\"padding:12px 14px;border-top:1px solid ").append(LINE)
                    .append(";font-size:13px;line-height:1.7;color:#374151;\">")
                    .append(guide.notes().stream().map(note -> "※ " + escape(note))
                            .collect(Collectors.joining("<br>")))
                    .append("</td></tr>");
        }
        return "<p style=\"margin:6px 0 12px;font-size:15px;line-height:1.75;color:" + TEXT + ";\">"
                + lines(guide.lead()) + "</p>"
                + "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" "
                + "style=\"border-collapse:separate;border:1px solid " + LINE + ";border-radius:8px;background:" + BOX
                + ";margin:0 0 8px;\">"
                + "<tr><td colspan=\"2\" style=\"padding:12px 14px;border-bottom:1px solid " + LINE
                + ";font-size:14px;font-weight:bold;color:" + escape(color) + ";\">" + escape(guide.title())
                + "</td></tr>"
                + rows + "</table>";
    }

    /** 이스케이프하고 줄바꿈을 br로. */
    private static String lines(String text) {
        return escape(text.strip()).replace("\n", "<br>");
    }

    private static String escape(String text) {
        return HtmlUtils.htmlEscape(text, "UTF-8");
    }
}
