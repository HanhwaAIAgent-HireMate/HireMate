package com.hiremate.posting;

import com.hiremate.mail.MailContent;

/** 지원자 한 명에게 보낼 접수 확인 메일. 공고의 템플릿에 지원자 값을 채웠다. */
public record ReceiptMail(String subject, MailContent content) {
}
