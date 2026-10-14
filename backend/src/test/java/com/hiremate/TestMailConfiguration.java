package com.hiremate;

import com.hiremate.mail.application.MailClient;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

/** 테스트에서는 SMTP 대신 보낸 메일을 기록만 한다. */
@TestConfiguration(proxyBeanMethods = false)
class TestMailConfiguration {

    @Bean
    @Primary
    RecordingMailClient recordingMailClient() {
        return new RecordingMailClient();
    }

    static class RecordingMailClient implements MailClient {

        final List<String> sent = new CopyOnWriteArrayList<>();

        @Override
        public void send(String to, String subject, String body) {
            sent.add(to + "|" + subject + "|" + body);
        }
    }
}
