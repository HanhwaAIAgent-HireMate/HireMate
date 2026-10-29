package com.hiremate.mail;

/**
 * 메일 꾸밈. 기업 설정의 색, 머리와 안내 상자 모양, 로고, 배너다.
 *
 * @param color 대표 색 (#rrggbb). 머리의 색 줄이나 띠, 회사 이름에 쓴다
 * @param accent 보조 색 (#rrggbb). 안내 상자 제목과 테두리에 쓴다. 없으면 null이고 대표 색을 쓴다
 * @param header 머리 모양
 * @param box 안내 상자 모양
 * @param logo 머리의 로고. 없으면 null이고, 머리에 회사 이름을 글자로 쓴다
 * @param banner 배너 머리의 그림. 없으면 null이고, 배너 머리는 색 띠로 보낸다
 */
public record MailBrand(String color, String accent, Header header, GuideBox box, Logo logo, Logo banner) {

    public static final String DEFAULT_COLOR = "#1e3a5f";
    public static final MailBrand BASIC = new MailBrand(DEFAULT_COLOR, null);

    /** 색과 로고만 고른 꾸밈. 머리는 얇은 색 줄, 안내 상자는 옅은 바탕이다. */
    public MailBrand(String color, Logo logo) {
        this(color, null, Header.LINE, GuideBox.FILL, logo, null);
    }

    /** 안내 상자에 쓸 색. 보조 색이 없으면 대표 색이다. */
    public String accentOrColor() {
        return accent == null ? color : accent;
    }

    /** 메일 머리 모양. */
    public enum Header {
        /** 맨 위 얇은 색 줄과 왼쪽 위 로고 */
        LINE,
        /** 대표 색 띠 위에 로고나 회사 이름 */
        BAND,
        /** 얇은 색 줄과 가운데 로고 */
        CENTER,
        /** 맨 위 배너 그림 */
        BANNER
    }

    /** 전형 안내 같은 안내 상자 모양. */
    public enum GuideBox {
        /** 옅은 회색 바탕과 회색 테두리 */
        FILL,
        /** 흰 바탕과 보조 색 테두리 */
        OUTLINE,
        /** 상자 없이 왼쪽 보조 색 막대와 줄로 나눈 표 */
        ROWS
    }

    /** 메일 안에 함께 넣어 보내는 그림. PNG나 JPEG다. */
    public record Logo(byte[] bytes, String contentType) {
    }
}
