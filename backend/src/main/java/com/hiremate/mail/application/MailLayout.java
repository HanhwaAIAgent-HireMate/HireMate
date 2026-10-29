package com.hiremate.mail.application;

import com.hiremate.mail.MailBrand.GuideBox;
import com.hiremate.mail.MailBrand.Header;
import com.hiremate.mail.MailContent;
import java.util.Arrays;
import java.util.List;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import org.springframework.web.util.HtmlUtils;

/**
 * 메일 HTML. 머리(로고, 회사 이름이나 배너), 공고명과 제목, 본문, 안내 상자, 맺음말, 바닥글 순서다.
 * 메일 프로그램은 바깥 CSS와 스크립트를 무시해서 꾸밈은 태그 안에 넣고 배치는 표로 한다.
 * 회사 이름부터 본문까지 모든 글은 이스케이프한다. 지원자 이름이나 AI 본문에 꺾쇠가 있어도 메일 모양이 깨지지 않는다.
 * 대표 색은 머리에, 보조 색은 안내 상자 제목과 테두리에 쓴다.
 */
public final class MailLayout {

    /** 메일에 함께 넣어 보내는 로고의 이름. HTML은 cid:로 가리킨다. */
    public static final String LOGO_CID = "company-logo";
    /** 메일에 함께 넣어 보내는 배너의 이름. */
    public static final String BANNER_CID = "company-banner";
    private static final String TEXT = "#1f2328";
    private static final String MUTED = "#6b7280";
    private static final String LINE = "#e5e7eb";
    private static final String BOX = "#f6f8fb";
    private static final String PAGE = "#f3f4f6";
    private static final String WHITE = "#ffffff";
    private static final String FONT = "'Malgun Gothic','Apple SD Gothic Neo','Noto Sans KR',sans-serif";
    private static final String PARAGRAPH = "margin:0 0 14px;font-size:15px;line-height:1.75;color:" + TEXT + ";";
    private static final Pattern BLANK_LINE = Pattern.compile("\\n\\s*\\n");
    private static final Pattern SUBJECT_TAG = Pattern.compile("^\\s*\\[[^]]*]\\s*");

    private MailLayout() {
    }

    /**
     * 메일 모양.
     *
     * @param color 대표 색 (#rrggbb)
     * @param accent 안내 상자에 쓸 색 (#rrggbb)
     * @param logoSrc 로고 그림 주소. 보낼 때는 cid:, 미리보기에서는 data: 주소다. 로고가 없으면 null이고 회사 이름을 쓴다
     * @param bannerSrc 배너 그림 주소. 없으면 null이고 배너 머리는 색 띠로 그린다
     */
    public record Look(String color, String accent, Header header, GuideBox box, String logoSrc, String bannerSrc) {

        /** 얇은 색 줄 머리와 옅은 바탕 안내 상자. */
        public static Look basic(String color, String logoSrc) {
            return new Look(color, color, Header.LINE, GuideBox.FILL, logoSrc, null);
        }
    }

    /** 색과 로고만 정한 기본 모양의 메일 HTML 문서. */
    public static String html(String subject, MailContent content, String color, String logoSrc) {
        return html(subject, content, Look.basic(color, logoSrc));
    }

    /** 메일 HTML 문서. */
    public static String html(String subject, MailContent content, Look look) {
        String heading = heading(subject);
        String caption = caption(content.caption(), heading);
        String blocks = content.blocks().stream().map(block -> block(block, look)).collect(Collectors.joining());
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
                %s
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
                """.formatted(escape(subject), PAGE, PAGE, FONT, LINE, header(content.sender(), look), caption, TEXT,
                escape(heading), LINE, blocks, closing, LINE, MUTED, lines(content.footer()));
    }

    /**
     * 머리 줄들. 얇은 줄과 가운데 머리는 맨 위 4px 색 줄 아래에 로고(높이 40px)나 대표 색 회사 이름을 둔다.
     * 띠 머리는 대표 색 띠 위에 흰 바탕 로고나 회사 이름을 둔다. 배너 머리는 배너 그림만 두고, 그림이 없으면 띠로 그린다.
     */
    private static String header(String sender, Look look) {
        String color = escape(look.color());
        Header header = look.header() == Header.BANNER && look.bannerSrc() == null ? Header.BAND : look.header();
        return switch (header) {
            case LINE, CENTER -> {
                String align = header == Header.CENTER ? "center" : "left";
                String cell = "<td class=\"hm-pad\" align=\"" + align + "\" style=\"padding:20px 32px 0;text-align:"
                        + align + ";";
                String mark = look.logoSrc() == null
                        ? cell + "font-size:16px;font-weight:bold;color:" + color + ";\">" + escape(sender) + "</td>"
                        : cell + "\">" + logo(look.logoSrc(), sender, 40, header == Header.CENTER) + "</td>";
                yield "<tr><td style=\"height:4px;background:" + color
                        + ";font-size:0;line-height:0;\">&nbsp;</td></tr><tr>" + mark + "</tr>";
            }
            case BAND -> {
                String mark = look.logoSrc() == null
                        ? "<span style=\"font-size:17px;font-weight:bold;color:" + onColor(look.color()) + ";\">"
                                + escape(sender) + "</span>"
                        : "<span style=\"display:inline-block;background:" + WHITE + ";border-radius:6px;"
                                + "padding:6px 10px;\">" + logo(look.logoSrc(), sender, 32, false) + "</span>";
                yield "<tr><td class=\"hm-pad\" style=\"padding:18px 32px;background:" + color + ";\">" + mark
                        + "</td></tr>";
            }
            case BANNER -> "<tr><td style=\"font-size:0;line-height:0;\"><img src=\"" + escape(look.bannerSrc())
                    + "\" alt=\"" + escape(sender) + "\" width=\"600\" style=\"display:block;width:100%;"
                    + "max-width:600px;height:auto;border:0;\"></td></tr>";
        };
    }

    private static String logo(String src, String sender, int height, boolean center) {
        return "<img src=\"" + escape(src) + "\" alt=\"" + escape(sender) + "\" height=\"" + height + "\" style=\""
                + (center ? "display:inline-block;" : "display:block;") + "height:" + height
                + "px;width:auto;max-width:220px;border:0;\">";
    }

    /** 색 바탕 위의 글자 색. 흰 글자의 명암비가 4.5:1에 못 미치면 진한 글자를 쓴다. */
    static String onColor(String color) {
        double luminance = luminance(color);
        return 1.05 / (luminance + 0.05) < 4.5 ? TEXT : WHITE;
    }

    private static double luminance(String color) {
        double[] channels = new double[3];
        for (int index = 0; index < 3; index++) {
            double value = Integer.parseInt(color.substring(1 + index * 2, 3 + index * 2), 16) / 255.0;
            channels[index] = value <= 0.03928 ? value / 12.92 : Math.pow((value + 0.055) / 1.055, 2.4);
        }
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
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

    private static String block(MailContent.Block block, Look look) {
        return switch (block) {
            case MailContent.Text text -> paragraphs(text.text());
            case MailContent.Guide guide -> guide(guide, look);
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

    /**
     * 안내 상자. 옅은 바탕은 회색 테두리 상자, 테두리는 보조 색 테두리의 흰 상자, 표는 상자 없이 제목 왼쪽의
     * 보조 색 막대와 줄로 나눈 칸이다. 제목은 어느 모양이든 보조 색 글자다.
     */
    private static String guide(MailContent.Guide guide, Look look) {
        String accent = escape(look.accent());
        boolean rows = look.box() == GuideBox.ROWS;
        String pad = rows ? "10px 4px" : "10px 14px";
        StringBuilder body = new StringBuilder();
        List<MailContent.Item> items = guide.items();
        for (int index = 0; index < items.size(); index++) {
            String border = index == 0 && !rows ? "" : "border-top:1px solid " + LINE + ";";
            body.append("<tr><td class=\"hm-label\" style=\"padding:").append(pad)
                    .append(";width:104px;vertical-align:top;font-size:13px;color:").append(MUTED).append(';')
                    .append(border).append("\">").append(escape(items.get(index).label())).append("</td>")
                    .append("<td style=\"padding:").append(pad)
                    .append(";vertical-align:top;font-size:14px;line-height:1.6;color:").append(TEXT).append(';')
                    .append(border).append("\">").append(lines(items.get(index).value())).append("</td></tr>");
        }
        if (!guide.notes().isEmpty()) {
            body.append("<tr><td colspan=\"2\" style=\"padding:").append(rows ? "12px 4px" : "12px 14px")
                    .append(";border-top:1px solid ").append(LINE)
                    .append(";font-size:13px;line-height:1.7;color:#374151;\">")
                    .append(guide.notes().stream().map(note -> "※ " + escape(note))
                            .collect(Collectors.joining("<br>")))
                    .append("</td></tr>");
        }
        String table = switch (look.box()) {
            case FILL -> "border-collapse:separate;border:1px solid " + LINE + ";border-radius:8px;background:" + BOX
                    + ";";
            case OUTLINE -> "border-collapse:separate;border:1px solid " + accent + ";border-radius:8px;background:"
                    + WHITE + ";";
            case ROWS -> "border-collapse:collapse;";
        };
        String title = rows
                ? "<tr><td colspan=\"2\" style=\"padding:2px 0 10px 0;\"><div style=\"border-left:4px solid "
                        + accent + ";padding:2px 0 2px 10px;font-size:14px;font-weight:bold;color:" + accent + ";\">"
                        + escape(guide.title()) + "</div></td></tr>"
                : "<tr><td colspan=\"2\" style=\"padding:12px 14px;border-bottom:1px solid " + LINE
                        + ";font-size:14px;font-weight:bold;color:" + accent + ";\">" + escape(guide.title())
                        + "</td></tr>";
        return "<p style=\"margin:6px 0 12px;font-size:15px;line-height:1.75;color:" + TEXT + ";\">"
                + lines(guide.lead()) + "</p>"
                + "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" style=\"" + table
                + "margin:0 0 8px;\">" + title + body + "</table>";
    }

    /** 이스케이프하고 줄바꿈을 br로. */
    private static String lines(String text) {
        return escape(text.strip()).replace("\n", "<br>");
    }

    private static String escape(String text) {
        return HtmlUtils.htmlEscape(text, "UTF-8");
    }
}
