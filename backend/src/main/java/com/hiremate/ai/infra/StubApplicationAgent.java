package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import com.hiremate.ai.application.ApplicationAgent;
import com.hiremate.apply.ApplicantDetail;
import com.hiremate.apply.ApplicantDocument;
import com.hiremate.apply.ApplicationAnalysis;
import com.hiremate.apply.CriterionMark;
import com.hiremate.posting.PostingContent;
import com.hiremate.posting.ScreeningRubric;
import java.time.Year;
import java.time.YearMonth;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import org.springframework.stereotype.Component;

/**
 * 개발용 Application Agent. 제출 문서 본문에서 경력 연수와 마지막 회사를 찾고, 평가 항목마다 항목 글의 낱말이 문서에
 * 나오는 비율로 판정을 붙인다(선 위 · 분포를 모델 없이 보려는 개발용 값이다). 서류는 점수를 매기지 않는다.
 * 실제 판정은 ai 서버의 Application Agent가 한다.
 */
@Component
@ConditionalOnAiMode(agent = AiAgent.APPLICATION, mode = AiMode.STUB)
class StubApplicationAgent implements ApplicationAgent {

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
        return Optional.of(new ApplicationAnalysis(careerYears, lastCompany, null, List.of(), marks(text, rubric)));
    }

    /**
     * 항목 글의 낱말이 문서에 나오는 비율로 판정한다. 60% 이상 충족, 30% 이상은 복합 경험형이면 부분 충족이고
     * 아니면 확인 필요, 조금이라도 나오면 확인 필요, 하나도 없으면 미충족이다. 서류가 비면 모두 확인 필요다.
     */
    static Map<String, CriterionMark> marks(String text, ScreeningRubric rubric) {
        String lower = text.toLowerCase(Locale.ROOT);
        Map<String, CriterionMark> marks = new LinkedHashMap<>();
        for (ScreeningRubric.Criterion criterion : rubric.criteria()) {
            Set<String> words = WORD.matcher(criterion.text()).results()
                    .map(match -> match.group().toLowerCase(Locale.ROOT))
                    .filter(word -> !STOP_WORDS.contains(word))
                    .collect(Collectors.toCollection(LinkedHashSet::new));
            double coverage = words.isEmpty() ? 0 : (double) words.stream().filter(lower::contains).count()
                    / words.size();
            CriterionMark mark;
            if (text.isBlank()) {
                mark = CriterionMark.UNKNOWN;
            } else if (coverage >= 0.6) {
                mark = CriterionMark.MET;
            } else if (coverage >= 0.3 && criterion.criterionType() == ScreeningRubric.CriterionType.COMPOSITE) {
                mark = CriterionMark.PARTIAL;
            } else if (coverage > 0) {
                mark = CriterionMark.UNKNOWN;
            } else {
                mark = CriterionMark.NOT_MET;
            }
            marks.put(criterion.criterionId(), mark);
        }
        return marks;
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

    private static int clampMonth(String month) {
        return Math.clamp(Integer.parseInt(month), 1, 12);
    }
}
