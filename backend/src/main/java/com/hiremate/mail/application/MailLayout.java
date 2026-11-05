package com.hiremate.mail.application;

import com.hiremate.mail.MailBrand.GuideBox;
import com.hiremate.mail.MailBrand.Header;
import com.hiremate.mail.MailContent;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
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
     * @param color 대표 색 (#rrggbb). 머리와 안내 상자 제목 · 테두리에 쓴다
     * @param logoSrc 로고 그림 주소. 보낼 때는 cid:, 미리보기에서는 data: 주소다. 로고가 없으면 null이고 회사 이름을 쓴다
     * @param bannerSrc 배너 그림 주소. 없으면 null이고 배너 머리는 색 띠로 그린다
     */
    public record Look(String color, Header header, GuideBox box, String logoSrc, String bannerSrc) {

        /** 얇은 색 줄 머리와 옅은 바탕 안내 상자. */
        public static Look basic(String color, String logoSrc) {
            return new Look(color, Header.LINE, GuideBox.FILL, logoSrc, null);
        }
    }

    /** 색과 로고만 정한 기본 모양의 메일 HTML 문서. */
    public static String html(String subject, MailContent content, String color, String logoSrc) {
        return html(subject, content, Look.basic(color, logoSrc));
    }

    /** 메일 HTML 문서. */
    public static String html(String subject, MailContent content, Look look) {
        boolean center = look.header() == Header.CENTER;
        boolean band = shape(look) == Header.BAND;
        String page = center ? tint(look.color()) : PAGE;
        String heading = heading(subject);
        // 띠 머리는 제목을 색 띠 안에 쓰고, 다른 머리는 카드 안 머리 아래에 쓴 뒤 가는 줄로 본문과 나눈다
        String title = band ? band(content.sender(), look, content.caption(), heading) : """
                %s
                <tr><td class="hm-pad" style="padding:%s;">%s%s
                <div style="font-size:22px;font-weight:bold;line-height:1.4;color:%s;">%s</div>
                </td></tr>
                <tr><td class="hm-pad" style="padding:14px 32px 0;">\
                <div style="height:1px;background:%s;font-size:0;line-height:0;">&nbsp;</div></td></tr>"""
                .formatted(header(content.sender(), look),
                        center ? "30px 32px 6px;text-align:center" : "22px 32px 6px",
                        center ? "<div style=\"width:40px;height:3px;margin:0 auto 16px;background:"
                                + escape(look.color()) + ";font-size:0;line-height:0;\">&nbsp;</div>" : "",
                        caption(content.caption(), heading, MUTED), TEXT, escape(heading), LINE);
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
                <tr><td align="center" style="padding:24px 12px;">%s
                <table role="presentation" width="100%%" cellpadding="0" cellspacing="0" \
                style="max-width:600px;background:#ffffff;border:1px solid %s;border-radius:10px;overflow:hidden;">
                %s
                <tr><td class="hm-pad" style="padding:%s;">%s%s</td></tr>
                <tr><td class="hm-pad" style="padding:16px 32px 20px;background:#fafafa;border-top:1px solid %s;\
                font-size:12px;line-height:1.7;color:%s;">%s</td></tr>
                </table>
                </td></tr>
                </table>
                </body>
                </html>
                """.formatted(escape(subject), page, page, FONT, center ? centerMark(content.sender(), look) : "",
                LINE, title, band ? "28px 32px 30px" : "22px 32px 30px", blocks, closing, LINE, MUTED,
                lines(content.footer()));
    }

    /** 실제로 그릴 머리. 배너 그림이 없는 배너 머리는 띠로 그린다. */
    private static Header shape(Look look) {
        return look.header() == Header.BANNER && look.bannerSrc() == null ? Header.BAND : look.header();
    }

    /**
     * 띠 머리. 대표 색 띠 안 위쪽에 로고(흰 바탕, 높이 28px)나 회사 이름을 두고, 아래에 공고명과 큰 제목을 쓴다.
     * 띠가 밝으면 흰 글자 대신 진한 글자를 쓴다.
     */
    private static String band(String sender, Look look, String caption, String heading) {
        String text = onColor(look.color());
        String soft = mix(text, look.color(), 0.3f);
        String mark = look.logoSrc() == null
                ? "<div style=\"font-size:15px;font-weight:bold;color:" + soft + ";\">" + escape(sender) + "</div>"
                : "<span style=\"display:inline-block;background:" + WHITE + ";border-radius:8px;"
                        + "padding:8px 12px;\">" + logo(look.logoSrc(), sender, 28, false) + "</span>";
        return "<tr><td class=\"hm-pad\" style=\"padding:26px 32px 30px;background:" + escape(look.color()) + ";\">"
                + mark + "<div style=\"height:28px;font-size:0;line-height:0;\">&nbsp;</div>"
                + caption(caption, heading, soft)
                + "<div style=\"font-size:24px;font-weight:bold;line-height:1.4;color:" + text + ";\">"
                + escape(heading) + "</div></td></tr>";
    }

    /**
     * 가운데 머리. 대표 색을 옅게 깐 바탕 위, 흰 카드 바깥 가운데에 로고(높이 48px)와 회사 이름을 둔다.
     * 로고가 없으면 회사 이름을 대표 색 큰 글자로 쓴다. 카드 안 제목도 가운데로 맞추고 위에 짧은 색 줄을 둔다.
     */
    private static String centerMark(String sender, Look look) {
        String mark = look.logoSrc() == null
                ? "<div style=\"font-size:20px;font-weight:bold;color:" + escape(look.color()) + ";\">"
                        + escape(sender) + "</div>"
                : logo(look.logoSrc(), sender, 48, true)
                        + "<div style=\"margin-top:8px;font-size:16px;font-weight:bold;color:" + TEXT + ";\">"
                        + escape(sender) + "</div>";
        return "\n<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" "
                + "style=\"max-width:600px;\"><tr><td align=\"center\" style=\"padding:8px 0 20px;text-align:center;\">"
                + mark + "</td></tr></table>";
    }

    /** 가운데 머리의 바탕. 대표 색을 흰색에 8%만 섞는다. 메일 프로그램이 투명도를 모를 수 있어 섞은 색을 쓴다. */
    static String tint(String color) {
        return mix(color, WHITE, 0.92f);
    }

    /** color를 toward 쪽으로 amount만큼 섞은 색. */
    private static String mix(String color, String toward, float amount) {
        StringBuilder hex = new StringBuilder("#");
        for (int index = 0; index < 3; index++) {
            int from = Integer.parseInt(color.substring(1 + index * 2, 3 + index * 2), 16);
            int to = Integer.parseInt(toward.substring(1 + index * 2, 3 + index * 2), 16);
            hex.append(String.format(Locale.ROOT, "%02x", Math.round(from + (to - from) * amount)));
        }
        return hex.toString();
    }

    /**
     * 카드 안 머리 줄들. 얇은 줄 머리는 맨 위 4px 색 줄 아래 왼쪽에 로고(높이 40px)나 대표 색 회사 이름을 둔다.
     * 배너 머리는 배너 그림만 둔다. 띠 머리는 제목과 함께 그리고 ({@link #band}), 가운데 머리는 카드 밖에 그린다
     * ({@link #centerMark}).
     */
    private static String header(String sender, Look look) {
        String color = escape(look.color());
        return switch (shape(look)) {
            case CENTER, BAND -> "";
            case LINE -> {
                String cell = "<td class=\"hm-pad\" align=\"left\" style=\"padding:20px 32px 0;text-align:left;";
                String mark = look.logoSrc() == null
                        ? cell + "font-size:16px;font-weight:bold;color:" + color + ";\">" + escape(sender) + "</td>"
                        : cell + "\">" + logo(look.logoSrc(), sender, 40, false) + "</td>";
                yield "<tr><td style=\"height:4px;background:" + color
                        + ";font-size:0;line-height:0;\">&nbsp;</td></tr><tr>" + mark + "</tr>";
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
    private static String caption(String caption, String heading, String color) {
        if (caption.isBlank() || heading.contains(caption.strip())) {
            return "";
        }
        return "\n<div style=\"margin:0 0 6px;font-size:13px;color:" + color + ";\">" + escape(caption) + "</div>";
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

    /** 칸 값 아래의 흐린 작은 메모. 미리보기에서만 쓴다. */
    private static String hint(MailContent.Item item) {
        return item.hint().isBlank() ? ""
                : "<br><span style=\"font-size:11px;color:" + MUTED + ";\">" + escape(item.hint()) + "</span>";
    }

    /**
     * 안내 상자. 옅은 바탕은 회색 테두리 상자, 테두리는 대표 색 테두리의 흰 상자, 표는 상자 없이 제목 왼쪽의
     * 대표 색 막대와 줄로 나눈 칸이다. 제목은 어느 모양이든 대표 색 글자다.
     */
    private static String guide(MailContent.Guide guide, Look look) {
        String color = escape(look.color());
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
                    .append(border).append("\">").append(lines(items.get(index).value())).append(hint(items.get(index)))
                    .append("</td></tr>");
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
            case OUTLINE -> "border-collapse:separate;border:1px solid " + color + ";border-radius:8px;background:"
                    + WHITE + ";";
            case ROWS -> "border-collapse:collapse;";
        };
        String title = rows
                ? "<tr><td colspan=\"2\" style=\"padding:2px 0 10px 0;\"><div style=\"border-left:4px solid "
                        + color + ";padding:2px 0 2px 10px;font-size:14px;font-weight:bold;color:" + color + ";\">"
                        + escape(guide.title()) + "</div></td></tr>"
                : "<tr><td colspan=\"2\" style=\"padding:12px 14px;border-bottom:1px solid " + LINE
                        + ";font-size:14px;font-weight:bold;color:" + color + ";\">" + escape(guide.title())
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
