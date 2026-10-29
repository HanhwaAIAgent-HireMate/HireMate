package com.hiremate;

import com.hiremate.mail.application.MailClient;
import com.hiremate.mail.application.MailLayout;
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

    /**
     * sent에는 "받는 사람|제목|텍스트 본문", html, logos, banners에는 같은 순서로 HTML 본문과
     * 함께 넣은 로고, 배너 형식(없으면 "")을 기록한다.
     */
    public static class RecordingMailClient implements MailClient {

        public final List<String> sent = new CopyOnWriteArrayList<>();
        public final List<String> html = new CopyOnWriteArrayList<>();
        public final List<String> logos = new CopyOnWriteArrayList<>();
        public final List<String> banners = new CopyOnWriteArrayList<>();

        /** 목록들의 순서가 어긋나지 않게 한 번에 하나씩 기록한다. */
        @Override
        public synchronized void send(String to, String subject, String text, String html, List<Inline> images) {
            sent.add(to + "|" + subject + "|" + text);
            this.html.add(html);
            logos.add(type(images, MailLayout.LOGO_CID));
            banners.add(type(images, MailLayout.BANNER_CID));
        }

        private static String type(List<Inline> images, String cid) {
            return images.stream().filter(image -> image.cid().equals(cid)).map(image -> image.image().contentType())
                    .findFirst().orElse("");
        }
    }
}
