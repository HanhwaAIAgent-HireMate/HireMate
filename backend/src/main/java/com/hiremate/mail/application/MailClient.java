package com.hiremate.mail.application;

/** 메일 발송 수단. 실패하면 예외를 던진다. */
public interface MailClient {

    void send(String to, String subject, String body);
}
