package com.hiremate.mail.infra;

import com.hiremate.mail.application.MailClient;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.MailPreparationException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Component;

@Component
class SmtpMailClient implements MailClient {

    private final JavaMailSender sender;
    private final String from;

    SmtpMailClient(JavaMailSender sender, @Value("${hiremate.mail.from}") String from) {
        this.sender = sender;
        this.from = from;
    }

    /** 텍스트와 HTML을 한 메일(multipart/alternative)에 담는다. */
    @Override
    public void send(String to, String subject, String text, String html) {
        MimeMessage message = sender.createMimeMessage();
        try {
            MimeMessageHelper helper = new MimeMessageHelper(message, true, StandardCharsets.UTF_8.name());
            helper.setFrom(from);
            helper.setTo(to);
            helper.setSubject(subject);
            helper.setText(text, html);
        } catch (MessagingException exception) {
            throw new MailPreparationException(exception);
        }
        sender.send(message);
    }
}
