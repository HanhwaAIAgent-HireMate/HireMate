package com.hiremate.mail.application;

/** 메일 발송 수단. 실패하면 예외를 던진다. */
public interface MailClient {

    /** 같은 내용의 텍스트와 HTML을 함께 보낸다. 메일 프로그램이 보여 줄 쪽을 고른다. */
    void send(String to, String subject, String text, String html);
}
