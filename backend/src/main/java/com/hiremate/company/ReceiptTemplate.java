package com.hiremate.company;

import com.hiremate.mail.MailContent;
import java.util.List;
import java.util.Map;

/**
 * 지원서를 내면 바로 보내는 접수 확인 메일 양식. 설정 › 안내 메일에서 기업마다 한 번 정하고 모든 공고에 쓴다.
 * 보낼 때의 양식을 쓰므로 모집 중에 고치면 그 뒤에 지원한 사람부터 새 문장을 받는다.
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

    /** 지원자 값을 채운 제목과 본문. */
    public ReceiptTemplate fill(String companyName, String title, String applicantName, int applicationNo) {
        Map<String, String> values = Map.of("{지원자명}", applicantName, "{회사명}", companyName, "{공고명}", title,
                "{지원번호}", String.valueOf(applicationNo));
        return new ReceiptTemplate(replace(subject, values), replace(body, values));
    }

    /** 값을 채운 양식의 메일 내용. 본문은 문단 글이고 필수 문구는 바닥글이다. */
    public MailContent toMail(String companyName, String title) {
        return new MailContent(companyName, title, List.of(new MailContent.Text(body)), "", REQUIRED_TEXT);
    }

    private static String replace(String text, Map<String, String> values) {
        String filled = text;
        for (Map.Entry<String, String> value : values.entrySet()) {
            filled = filled.replace(value.getKey(), value.getValue());
        }
        return filled;
    }
}
