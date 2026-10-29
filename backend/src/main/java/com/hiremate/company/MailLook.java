package com.hiremate.company;

import com.hiremate.mail.MailBrand.GuideBox;
import com.hiremate.mail.MailBrand.Header;

/**
 * HR이 고른 메일 색과 부품. 저장하거나 저장 전 미리보기에 쓴다.
 *
 * @param color 대표 색. #0055A4처럼 6자리 색 코드이고 앞의 #는 빼도 된다
 * @param accent 보조 색. 없으면 null이다
 */
public record MailLook(String color, String accent, Header header, GuideBox box) {

    /**
     * 미리보기 주소의 질의로 받은 저장 전 꾸밈. color가 없으면 null(저장한 꾸밈)이고,
     * header와 box가 없으면 얇은 색 줄 머리와 옅은 바탕 안내 상자다.
     */
    public static MailLook draft(String color, String accent, Header header, GuideBox box) {
        return color == null ? null
                : new MailLook(color, accent, header == null ? Header.LINE : header, box == null ? GuideBox.FILL : box);
    }
}
