package com.hiremate.mail;

import com.hiremate.mail.application.MailClient;
import com.hiremate.mail.application.MailLayout;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/** 메일을 보낸다. HTML을 못 보는 메일 프로그램을 위해 같은 내용의 텍스트도 함께 보낸다. 예외를 던지지 않고 결과로 알려 준다. */
@Service
public class MailService {

    private static final Logger log = LoggerFactory.getLogger(MailService.class);

    private final MailClient client;

    public MailService(MailClient client) {
        this.client = client;
    }

    public MailResult send(String to, String subject, MailContent content) {
        try {
            client.send(to, subject, content.text(), MailLayout.html(subject, content));
            return MailResult.success();
        } catch (RuntimeException exception) {
            log.warn("Mail delivery failed: {}", exception.getMessage());
            return MailResult.failure(exception.getClass().getSimpleName());
        }
    }
}
