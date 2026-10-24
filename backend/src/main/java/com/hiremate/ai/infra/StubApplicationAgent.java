package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import com.hiremate.ai.application.ApplicationAgent;
import com.hiremate.apply.ApplicantDetail;
import com.hiremate.apply.ApplicantDocument;
import com.hiremate.apply.ApplicationAnalysis;
import com.hiremate.posting.PostingContent;
import com.hiremate.posting.ScreeningRubric;
import java.math.BigDecimal;
import java.time.Year;
import java.time.YearMonth;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import org.springframework.stereotype.Component;

/**
 * 개발용 Application Agent. 제출 문서 본문에서 경력 연수와 마지막 회사를 찾고, 공고의 업무 · 자격 요건 · 우대 사항
 * 낱말이 문서에 얼마나 나오는지로 서류 점수(0~100)를 매긴다. 60점 이상을 자격요건 통과로 보고, 점수는 보류하지 않는다
 * (개발용 기본값. 실제 판정은 ai 서버의 Application Agent가 한다).
 */
@Component
@ConditionalOnAiMode(agent = AiAgent.APPLICATION, mode = AiMode.STUB)
class StubApplicationAgent implements ApplicationAgent {

    static final int PASS_SCORE = 60;

    private static final Pattern CAREER_YEARS = Pattern.compile("경력\\s*(\\d{1,2})\\s*년");
    private static final Pattern PERIOD = Pattern.compile("((?:19|20)\\d{2})[.\\-/]\\s?(\\d{1,2})\\s*[~\\-–—]\\s*"
            + "(현재|재직\\s*중|((?:19|20)\\d{2})[.\\-/]\\s?(\\d{1,2}))");
    private static final Pattern COMPANY = Pattern.compile("([가-힣A-Za-z0-9&]{1,20}"
            + "(?:카드|페이먼츠|페이|은행|증권|생명|보험|캐피탈|시스템|데이터|물류|마켓|게임즈|솔루션|커머스|테크|랩스|소프트|"
            + "전자|컴퍼니|그룹|핀테크|네트웍스|정보통신))");
    private static final Pattern WORD = Pattern.compile("[가-힣]{2,}|[A-Za-z][A-Za-z+#.]{1,}");
    private static final Set<String> STOP_WORDS = Set.of("경험", "있으신", "있는", "이상", "관련", "개발", "업무", "분",
            "통해", "위한", "대한", "등의", "또는", "그리고", "with", "and", "the");

    @Override
    public Optional<ApplicationAnalysis> analyze(ApplicantDetail applicant, PostingContent posting,
            ScreeningRubric rubric) {
        String text = applicant.documents().stream().map(ApplicantDocument::text).collect(Collectors.joining("\n"));
        int careerYears = careerYears(text);
        String lastCompany = careerYears == 0 ? null : lastCompany(text);
        int score = score(text, posting, careerYears);
        return Optional.of(ApplicationAnalysis.of(careerYears, lastCompany, BigDecimal.valueOf(score),
                score >= PASS_SCORE, false, List.of()));
    }

    static int careerYears(String text) {
        Matcher stated = CAREER_YEARS.matcher(text);
        if (stated.find()) {
            return Integer.parseInt(stated.group(1));
        }
        int months = 0;
        Matcher period = PERIOD.matcher(text);
        while (period.find()) {
            YearMonth start = YearMonth.of(Integer.parseInt(period.group(1)), clampMonth(period.group(2)));
            YearMonth end = period.group(4) == null
                    ? YearMonth.now()
                    : YearMonth.of(Integer.parseInt(period.group(4)), clampMonth(period.group(5)));
            if (!end.isBefore(start) && start.getYear() <= Year.now().getValue()) {
                months += (end.getYear() - start.getYear()) * 12 + end.getMonthValue() - start.getMonthValue();
            }
        }
        return months / 12;
    }

    /** 문서에 처음 나오는 회사 이름. 이력서는 보통 최근 경력부터 적는다. */
    static String lastCompany(String text) {
        Matcher company = COMPANY.matcher(text);
        return company.find() ? company.group(1) : null;
    }

    static int score(String text, PostingContent posting, int careerYears) {
        Set<String> keywords = Stream.of(posting.duties(), posting.qualifications(), posting.preferred())
                .flatMap(List::stream)
                .flatMap(line -> WORD.matcher(line).results().map(match -> match.group().toLowerCase(Locale.ROOT)))
                .filter(word -> !STOP_WORDS.contains(word))
                .collect(Collectors.toCollection(LinkedHashSet::new));
        String lower = text.toLowerCase(Locale.ROOT);
        long matched = keywords.stream().filter(lower::contains).count();
        double coverage = keywords.isEmpty() ? 0.5 : (double) matched / keywords.size();
        int base = text.isBlank() ? 20 : 40;
        return (int) Math.min(100, Math.round(base + coverage * 45 + Math.min(careerYears, 10) * 1.5));
    }

    private static int clampMonth(String month) {
        return Math.clamp(Integer.parseInt(month), 1, 12);
    }
}
