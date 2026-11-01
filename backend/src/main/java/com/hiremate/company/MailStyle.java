package com.hiremate.company;

import com.hiremate.mail.MailBrand.GuideBox;
import com.hiremate.mail.MailBrand.Header;

/**
 * 설정 화면의 메일 꾸밈.
 *
 * @param color 대표 색 (#rrggbb). 고르지 않았으면 기본 색이다
 * @param header 머리 모양
 * @param box 안내 상자 모양
 * @param hasLogo 로고를 올렸는지
 * @param hasBanner 배너를 올렸는지. 없으면 배너 머리는 색 띠로 보낸다
 */
public record MailStyle(String color, Header header, GuideBox box, boolean hasLogo, boolean hasBanner) {
}
