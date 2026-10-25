package com.hiremate.mail;

/**
 * 메일 꾸밈. 기업 설정의 색과 로고다.
 *
 * @param color 머리글 띠, 회사 이름, 안내 상자 제목의 색 (#rrggbb)
 * @param logo 머리글 왼쪽 위의 로고. 없으면 null이고, 머리글에 회사 이름을 글자로 쓴다
 */
public record MailBrand(String color, Logo logo) {

    public static final String DEFAULT_COLOR = "#1e3a5f";
    public static final MailBrand BASIC = new MailBrand(DEFAULT_COLOR, null);

    /** 로고 그림. PNG나 JPEG다. */
    public record Logo(byte[] bytes, String contentType) {
    }
}
