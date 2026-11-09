package com.hiremate.posting;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

/**
 * 공고 본문과 서류 필수 조건(HR이 공고 작성 화면에서 '필수'로 표시한 줄)으로 서류 평가 기준을 만든다.
 *
 * <ul>
 * <li>항목은 공고의 자격요건 · 우대사항 줄마다 하나다. 번호는 공고 순서다 (Q-01, Q-02 … / P-01 …). 줄 글이 곧 항목 글이라
 * AI 분석의 판정과 서류 전형의 기준선이 같은 줄을 가리킨다.</li>
 * <li>중요(필수) 표시는 공고의 필수 조건 표시다. 기준선은 필수로 표시한 자격요건을 모두 충족했는지로 가른다.</li>
 * <li>유형 · 판정 기준 · 인정 자격증은 평가 기준 입력 화면이 생기기 전까지 설정의 더미에서 같은 글의 항목을 찾아 쓴다. 없으면 판정
 * 기준을 비워 보내고, AI가 그 줄의 판정 기준 초안을 만들어 판정한다.</li>
 * <li>평가 기준 버전에는 항목 글과 필수 표시를 담는다. 표시가 바뀌면 저장된 분석 결과를 다시 쓰지 않는다.</li>
 * </ul>
 */
final class PostingRubric {

    /** 판정 기준이 없는 항목. AI가 판정 기준 초안을 만든다. */
    static final ScreeningRubric.EvaluationRules NO_RULES = new ScreeningRubric.EvaluationRules("", null, "");

    private PostingRubric() {
    }

    static ScreeningRubric of(ScreeningRubric dummy, PostingContent content, RequiredCriteria required) {
        Map<String, ScreeningRubric.Criterion> saved = dummy.criteria().stream()
                .collect(Collectors.toMap(criterion -> key(criterion.category(), criterion.text()),
                        Function.identity(), (first, second) -> first));
        RequiredCriteria marked = required.within(content);
        List<ScreeningRubric.Criterion> criteria = new ArrayList<>();
        criteria.addAll(lines(ScreeningRubric.Category.QUALIFICATION, "Q", content.qualifications(),
                marked.qualifications(), saved));
        criteria.addAll(lines(ScreeningRubric.Category.PREFERENCE, "P", content.preferred(), marked.preferred(),
                saved));
        return new ScreeningRubric(dummy.companyId(), dummy.recruitmentId(), version(dummy.criteriaVersion(), criteria),
                dummy.hireCount(), criteria);
    }

    private static List<ScreeningRubric.Criterion> lines(ScreeningRubric.Category category, String prefix,
            List<String> texts, List<String> required, Map<String, ScreeningRubric.Criterion> saved) {
        List<ScreeningRubric.Criterion> criteria = new ArrayList<>();
        for (int index = 0; index < texts.size(); index++) {
            String text = texts.get(index);
            ScreeningRubric.Criterion found = saved.get(key(category, text));
            criteria.add(new ScreeningRubric.Criterion(String.format("%s-%02d", prefix, index + 1), category, text,
                    required.contains(text),
                    found != null ? found.criterionType() : ScreeningRubric.CriterionType.SINGLE,
                    found != null ? found.evaluationRules() : NO_RULES,
                    found != null ? found.certificates() : List.of()));
        }
        return criteria;
    }

    /** 항목 글은 공백 차이를 무시하고 짝짓는다 (AI 분석의 짝짓기와 같다). */
    private static String key(ScreeningRubric.Category category, String text) {
        return category + ":" + text.replaceAll("\\s+", "");
    }

    /** 더미 버전에 항목 글 · 필수 표시의 지문을 붙인다. 같은 공고 · 같은 표시면 같은 버전이다. */
    private static String version(String base, List<ScreeningRubric.Criterion> criteria) {
        String source = criteria.stream()
                .map(criterion -> criterion.criterionId() + "|" + criterion.text() + "|" + criterion.important())
                .collect(Collectors.joining("\n"));
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(source.getBytes(StandardCharsets.UTF_8));
            return base + "+" + HexFormat.of().formatHex(digest, 0, 6);
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException(impossible);
        }
    }
}
