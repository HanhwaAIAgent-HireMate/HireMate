package com.hiremate.posting;

import com.hiremate.mail.MailBrand;
import com.hiremate.mail.MailContent;
import java.util.List;
import java.util.Map;

/**
 * 지원서를 내면 바로 보내는 접수 확인 메일. HR이 공고를 쓸 때 고치고, 게시하면 바꿀 수 없다 (모든 지원자가 같은 메일을 받는다).
 * {지원자명}, {회사명}, {공고명}, {지원번호}는 보낼 때 값으로 바뀌고, 필수 문구는 메일 바닥글로 붙어 고칠 수 없다.
 * AI는 쓰지 않는다. 지원자마다 바로 나가 HR이 보낼 때 확인할 수 없기 때문이다.
 */
public record ReceiptTemplate(String subject, String body) {

    public static final String REQUIRED_TEXT = "본 메일은 발신 전용입니다. 지원자 정보는 채용 목적으로만 이용됩니다.";

    public static final ReceiptTemplate DEFAULT = new ReceiptTemplate("[{회사명}] {공고명} 지원이 접수되었습니다",
            """
            {지원자명}님, {회사명} {공고명} 채용에 지원해 주셔서 감사합니다.

            지원번호 {지원번호}번으로 접수되었습니다.
            전형 결과는 이 메일 주소로 안내드리겠습니다.

            {회사명} 인사팀 드림""");

    /** 지원자에게 보낼 메일. 본문은 문단 글이고 필수 문구는 바닥글이다. */
    public ReceiptMail fill(String companyName, String title, String applicantName, int applicationNo,
            MailBrand brand) {
        Map<String, String> values = Map.of("{지원자명}", applicantName, "{회사명}", companyName, "{공고명}", title,
                "{지원번호}", String.valueOf(applicationNo));
        return new ReceiptMail(replace(subject, values), new MailContent(companyName, title,
                List.of(new MailContent.Text(replace(body, values))), "", REQUIRED_TEXT), brand);
    }

    private static String replace(String text, Map<String, String> values) {
        String filled = text;
        for (Map.Entry<String, String> value : values.entrySet()) {
            filled = filled.replace(value.getKey(), value.getValue());
        }
        return filled;
    }
}
