package com.hiremate.mail.infra;

import com.hiremate.mail.application.MailClient;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Component;

@Component
class SmtpMailClient implements MailClient {

    private final JavaMailSender sender;
    private final String from;

    SmtpMailClient(JavaMailSender sender, @Value("${hiremate.mail.from}") String from) {
        this.sender = sender;
        this.from = from;
    }

    @Override
    public void send(String to, String subject, String body) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(from);
        message.setTo(to);
        message.setSubject(subject);
        message.setText(body);
        sender.send(message);
    }
}
