package com.hiremate.company;

/**
 * 설정 화면의 메일 꾸밈.
 *
 * @param color 메일 색 (#rrggbb). 고르지 않았으면 기본 색이다
 * @param hasLogo 로고를 올렸는지
 */
public record MailStyle(String color, boolean hasLogo) {
}
