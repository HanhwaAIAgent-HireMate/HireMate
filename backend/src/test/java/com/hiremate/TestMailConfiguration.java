package com.hiremate;

import com.hiremate.mail.application.MailClient;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

/** 테스트에서는 SMTP 대신 보낸 메일을 기록만 한다. */
@TestConfiguration(proxyBeanMethods = false)
public class TestMailConfiguration {

    @Bean
    @Primary
    RecordingMailClient recordingMailClient() {
        return new RecordingMailClient();
    }

    /** sent에는 "받는 사람|제목|텍스트 본문", html에는 같은 순서로 HTML 본문을 기록한다. */
    public static class RecordingMailClient implements MailClient {

        public final List<String> sent = new CopyOnWriteArrayList<>();
        public final List<String> html = new CopyOnWriteArrayList<>();

        @Override
        public void send(String to, String subject, String text, String html) {
            sent.add(to + "|" + subject + "|" + text);
            this.html.add(html);
        }
    }
}
