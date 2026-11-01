package com.hiremate.mail;

import com.hiremate.mail.application.MailClient;
import com.hiremate.mail.application.MailLayout;
import java.util.ArrayList;
import java.util.List;
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

    /** 로고와 배너는 메일 안에 함께 넣어 보낸다. 공개 주소 없이도 지원자 메일에서 보인다. */
    public MailResult send(String to, String subject, MailContent content, MailBrand brand) {
        List<MailClient.Inline> images = new ArrayList<>();
        String logoSrc = inline(images, MailLayout.LOGO_CID, brand.logo());
        String bannerSrc = inline(images, MailLayout.BANNER_CID, brand.banner());
        MailLayout.Look look = new MailLayout.Look(brand.color(), brand.header(), brand.box(),
                logoSrc, bannerSrc);
        try {
            client.send(to, subject, content.text(), MailLayout.html(subject, content, look), images);
            return MailResult.success();
        } catch (RuntimeException exception) {
            log.warn("Mail delivery failed: {}", exception.getMessage());
            return MailResult.failure(exception.getClass().getSimpleName());
        }
    }

    /** 그림이 있으면 함께 넣을 목록에 더하고 cid: 주소를, 없으면 null을 돌려준다. */
    private static String inline(List<MailClient.Inline> images, String cid, MailBrand.Logo image) {
        if (image == null) {
            return null;
        }
        images.add(new MailClient.Inline(cid, image));
        return "cid:" + cid;
    }
}
