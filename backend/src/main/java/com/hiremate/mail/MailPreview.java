package com.hiremate.mail;

import com.hiremate.mail.application.MailLayout;
import java.util.Base64;

/**
 * 보내기 전 화면에 보여 줄 메일. 보낼 때와 같은 HTML이고, 지원자 값은 예시로 채운다.
 *
 * @param html 메일 HTML 문서 전체. 화면은 스크립트를 막은 iframe에 넣는다
 */
public record MailPreview(String subject, String html) {

    /** 변수는 미리 예시 값으로 채워 넘긴다. 로고는 보낼 때와 달리 HTML 안에 data: 주소로 넣는다. */
    public static MailPreview of(String subject, MailContent content, MailBrand brand) {
        String logoSrc = brand.logo() == null ? null
                : "data:" + brand.logo().contentType() + ";base64,"
                        + Base64.getEncoder().encodeToString(brand.logo().bytes());
        return new MailPreview(subject, MailLayout.html(subject, content, brand.color(), logoSrc));
    }
}
