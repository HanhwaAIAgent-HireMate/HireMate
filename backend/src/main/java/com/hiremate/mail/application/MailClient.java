package com.hiremate.mail.application;

import com.hiremate.mail.MailBrand;
import java.util.List;

/** 메일 발송 수단. 실패하면 예외를 던진다. */
public interface MailClient {

    /**
     * 같은 내용의 텍스트와 HTML을 함께 보낸다. 메일 프로그램이 보여 줄 쪽을 고른다.
     *
     * @param images HTML이 cid:로 가리키는 로고와 배너. 없으면 빈 목록
     */
    void send(String to, String subject, String text, String html, List<Inline> images);

    /** 메일 안에 함께 넣는 그림. HTML은 cid:{cid}로 가리킨다. */
    record Inline(String cid, MailBrand.Logo image) {
    }
}
