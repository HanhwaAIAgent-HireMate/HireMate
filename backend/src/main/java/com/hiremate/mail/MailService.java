package com.hiremate.mail;

import com.hiremate.mail.application.MailClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/** 텍스트 메일을 보낸다. 예외를 던지지 않고 결과로 알려 준다. */
@Service
public class MailService {

    private static final Logger log = LoggerFactory.getLogger(MailService.class);

    private final MailClient client;

    public MailService(MailClient client) {
        this.client = client;
    }

    public MailResult send(String to, String subject, String body) {
        try {
            client.send(to, subject, body);
            return MailResult.success();
        } catch (RuntimeException exception) {
            log.warn("Mail delivery failed: {}", exception.getMessage());
            return MailResult.failure(exception.getClass().getSimpleName());
        }
    }
}
