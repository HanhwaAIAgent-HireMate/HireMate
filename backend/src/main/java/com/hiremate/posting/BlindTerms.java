package com.hiremate.posting;

import java.util.List;
import java.util.regex.Pattern;

/**
 * 블라인드 채용에서 쓰지 않는 학력 · 출신 학교 조건. ai guardrails의 _BLIND_ATTRIBUTE와 같은 낱말을 본다.
 * 직무와 관련된 전공, 자격, 경력은 막지 않는다. HR이 직접 쓴 자격 요건 · 우대 사항을 게시 전에 확인한다.
 */
final class BlindTerms {

    private static final String SCHOOL_ORIGIN =
            "(?:(?!여)[가-힣A-Za-z]대|SKY|대학교?|대학원|학교|고등학교|고교)\\s*출신|출신\\s*(?:학교|대학교?|교)";
    private static final Pattern BLIND = Pattern.compile(SCHOOL_ORIGIN
            + "|(?:[가-힣A-Za-z]대|대학교?|대학원)\\s*(?:나온|졸업)|대학교|학교명|대학명"
            + "|학력|학벌|학위|학사|석사|박사|대졸|고졸|전문대|명문대|지방대|인서울|학점"
            + "|(?<![A-Za-z])(?:SKY|GPA)(?![A-Za-z])");

    private BlindTerms() {
    }

    /** 학력 · 출신 학교 조건이 들어간 줄. */
    static List<String> linesWithBlindTerms(List<String> lines) {
        return lines.stream().filter(line -> BLIND.matcher(line).find()).toList();
    }
}
