package com.hiremate.mail;

/** 발송 결과. 실패하면 error에 이유를 담고, 부른 쪽이 재시도할 수 있게 기록한다. */
public record MailResult(boolean sent, String error) {

    public static MailResult success() {
        return new MailResult(true, null);
    }

    public static MailResult failure(String error) {
        return new MailResult(false, error);
    }
}
