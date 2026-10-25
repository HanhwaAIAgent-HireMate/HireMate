package com.hiremate.mail;

import com.hiremate.mail.application.MailLayout;

/**
 * 보내기 전 화면에 보여 줄 메일. 보낼 때와 같은 HTML이고, 지원자 값은 예시로 채운다.
 *
 * @param html 메일 HTML 문서 전체. 화면은 스크립트를 막은 iframe에 넣는다
 */
public record MailPreview(String subject, String html) {

    /** 변수는 미리 예시 값으로 채워 넘긴다. */
    public static MailPreview of(String subject, MailContent content) {
        return new MailPreview(subject, MailLayout.html(subject, content));
    }
}
