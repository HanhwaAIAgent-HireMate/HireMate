package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import com.hiremate.ai.application.CandidateAnalysis;
import com.hiremate.ai.application.CandidateAnalyst;
import com.hiremate.ai.application.CompanyFactors;
import com.hiremate.ai.application.FeatureLabels;
import com.hiremate.ai.application.TalentFit;
import com.hiremate.ai.application.TalentFitRequest;
import com.hiremate.apply.ApplicantDetail;
import com.hiremate.apply.ApplicantDocument;
import com.hiremate.apply.QualificationStatus;
import com.hiremate.company.Talent;
import com.hiremate.posting.DocumentType;
import com.hiremate.posting.PostingContent;
import com.hiremate.posting.ScreeningRubric;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.regex.Pattern;
import org.springframework.stereotype.Component;

/**
 * 개발용 지원자 분석. 공고의 자격 요건 · 우대 사항 낱말이 들어 있는 문장을 제출 문서에서 찾아 근거로 붙인다.
 * 근거 문장을 찾지 못한 조건은 확인 필요로 둔다.
 */
@Component
@ConditionalOnAiMode(agent = AiAgent.CANDIDATE_ANALYST, mode = AiMode.STUB)
class StubCandidateAnalyst implements CandidateAnalyst {

    private static final Pattern WORD = Pattern.compile("[가-힣]{2,}|[A-Za-z][A-Za-z+#.]{1,}");
    private static final Pattern SENTENCE_BREAK = Pattern.compile("\\n+|(?<=[.!?。])\\s+");
    private static final Pattern NUMBER = Pattern.compile("\\d");
    private static final List<String> STOP_WORDS = List.of("경험", "있으신", "있는", "이상", "관련", "업무", "통해",
            "위한", "대한", "등의", "또는", "그리고", "해본", "본", "분");
    private static final int MAX_LABEL = 16;
    private static final Pattern VALUE_WORD = Pattern.compile("중요|중시|우선|환영");
    // 영문 · 숫자 바로 뒤에 붙은 조사. 'Spring Boot로' → 'Spring Boot'
    private static final Pattern PARTICLE = Pattern.compile("(?<=[A-Za-z0-9])(으로|로|를|을|의|에서|와|과|는|은|이|가)$");
    // 잘린 끝에 남으면 뜻이 끊기는 말. 'Java 또는' → 'Java'
    private static final List<String> DANGLING = List.of("또는", "및", "등", "와", "과", "·", "기반", "등으로");
    // 열 이름 끝에서 떼어도 뜻이 남는 말. '인성을 중요시한다' → '인성' (ai의 table.py와 같은 규칙)
    private static final Pattern LABEL_ENDING = Pattern.compile(
            "\\s*(을|를|이|가|은|는)?\\s*(중요시|중시|최우선으로|우선)\\s*(한다|합니다|하는|함)?\\.?$"
                    + "|\\s*(경험|경력)?\\s*(보유자?|우대|있는 분|있으신 분|이 있는 분|자)\\.?$");

    @Override
    public CandidateAnalysis analyze(ApplicantDetail applicant, PostingContent posting, ScreeningRubric rubric) {
        Map<String, DocumentType> sentences = sentences(applicant.documents());
        List<CandidateAnalysis.Condition> conditions = new ArrayList<>();
        List<CandidateAnalysis.Finding> notable = new ArrayList<>();
        List<CandidateAnalysis.Finding> checks = new ArrayList<>();
        Map<String, DocumentType> highlights = new LinkedHashMap<>();

        for (String requirement : posting.qualifications()) {
            Optional<Map.Entry<String, DocumentType>> evidence = evidence(sentences, requirement);
            conditions.add(new CandidateAnalysis.Condition(label(requirement), evidence.isPresent(), requirement));
            evidence.ifPresentOrElse(found -> highlights.put(found.getKey(), found.getValue()),
                    () -> checks.add(new CandidateAnalysis.Finding(
                            "\"" + requirement + "\"의 근거가 제출 문서에 없어요. 면접에서 확인이 필요해요.", "공고 · 자격 요건")));
        }
        for (String preference : posting.preferred()) {
            Optional<Map.Entry<String, DocumentType>> evidence = evidence(sentences, preference);
            evidence.ifPresent(found -> {
                conditions.add(new CandidateAnalysis.Condition(label(preference), true, preference));
                highlights.put(found.getKey(), found.getValue());
                notable.add(new CandidateAnalysis.Finding(found.getKey(), source(found.getValue())));
            });
        }
        sentences.entrySet().stream()
                .filter(entry -> NUMBER.matcher(entry.getKey()).find() && !highlights.containsKey(entry.getKey()))
                .filter(entry -> entry.getKey().length() >= 12)
                .limit(Math.max(0, 2 - notable.size()))
                .forEach(entry -> {
                    notable.add(new CandidateAnalysis.Finding(entry.getKey(), source(entry.getValue())));
                    highlights.put(entry.getKey(), entry.getValue());
                });
        if (sentences.isEmpty()) {
            checks.add(new CandidateAnalysis.Finding("제출 문서에서 글자를 읽지 못했어요. 원본 PDF를 확인해 주세요.", "제출 문서"));
        }
        return new CandidateAnalysis(conditions, notable, checks, List.of(), null, CandidateAnalysis.ScoreStatus.HELD,
                null, null, QualificationStatus.UNDETERMINED, null, null, null, 0, null, null, 0, List.of(),
                List.of(),
                highlights.entrySet().stream()
                        .map(entry -> new CandidateAnalysis.Evidence(entry.getValue(), entry.getKey()))
                        .toList(),
                "Application Agent", true);
    }

    private static Map<String, DocumentType> sentences(List<ApplicantDocument> documents) {
        Map<String, DocumentType> sentences = new LinkedHashMap<>();
        for (ApplicantDocument document : documents) {
            Arrays.stream(SENTENCE_BREAK.split(document.text()))
                    .map(line -> line.replaceFirst("^[·•\\-*]\\s*", "").strip())
                    .filter(line -> line.length() >= 6)
                    .forEach(line -> sentences.putIfAbsent(line, document.type()));
        }
        return sentences;
    }

    private static Optional<Map.Entry<String, DocumentType>> evidence(Map<String, DocumentType> sentences,
            String requirement) {
        List<String> keywords = keywords(requirement);
        if (keywords.isEmpty()) {
            return Optional.empty();
        }
        return sentences.entrySet().stream()
                .map(entry -> Map.entry(entry, hits(entry.getKey(), keywords)))
                .filter(scored -> scored.getValue() > 0)
                .max(Comparator.comparing(Map.Entry::getValue))
                .map(Map.Entry::getKey);
    }

    private static long hits(String sentence, List<String> keywords) {
        String lower = sentence.toLowerCase(Locale.ROOT);
        return keywords.stream().filter(lower::contains).count();
    }

    private static List<String> keywords(String text) {
        return WORD.matcher(text).results()
                .map(match -> match.group().toLowerCase(Locale.ROOT))
                .filter(word -> !STOP_WORDS.contains(word))
                .distinct()
                .toList();
    }

    private static String label(String requirement) {
        List<String> words = WORD.matcher(requirement).results().map(match -> match.group())
                .filter(word -> !STOP_WORDS.contains(word))
                .limit(2)
                .toList();
        return words.isEmpty() ? requirement : String.join("·", words);
    }

    private static String source(DocumentType type) {
        return type.label();
    }

    /** 모델 없이 끝말을 떼고 단어 경계에서 자른다. 겹치면 뒤에 점을 붙여 구분한다. */
    @Override
    public FeatureLabels labels(List<String> texts) {
        List<String> labels = new ArrayList<>();
        for (String text : texts) {
            String label = shortLabel(text);
            while (labels.contains(label)) {
                label = label + "·";
            }
            labels.add(label);
        }
        return new FeatureLabels(labels);
    }

    /** 개발용 응답은 인재상을 판정하지 않고 모두 확인 필요로 둔다. */
    @Override
    public TalentFit talents(TalentFitRequest request) {
        return new TalentFit(request.talents().stream()
                .map(talent -> new TalentFit.Match(talent.title(), TalentFit.Level.UNKNOWN, "",
                        "개발용 응답이라 판정하지 않았어요.", null))
                .toList(), "Application Agent", true);
    }

    /** 모델 없이 '중요' · '중시' · '우선' · '환영'이 든 문장을 요소로 보고 끝말을 떼어 이름을 붙인다. */
    @Override
    public CompanyFactors factors(String text) {
        List<Talent> factors = new ArrayList<>();
        for (String sentence : SENTENCE_BREAK.split(text)) {
            String line = sentence.strip();
            if (VALUE_WORD.matcher(line).find() && factors.size() < 6) {
                String title = shortLabel(line.replaceAll("[.!]$", ""));
                if (factors.stream().noneMatch(factor -> factor.title().equals(title))) {
                    factors.add(new Talent(title, line));
                }
            }
        }
        return new CompanyFactors(factors);
    }

    static String shortLabel(String text) {
        String compact = String.join(" ", text.trim().split("\\s+"));
        String words = LABEL_ENDING.matcher(compact).replaceAll("");
        if (words.isBlank()) {
            words = compact;
        }
        if (words.length() <= MAX_LABEL) {
            return words;
        }
        List<String> kept = new ArrayList<>();
        for (String word : words.split(" ")) {
            if (String.join(" ", kept).length() + word.length() + (kept.isEmpty() ? 0 : 1) > MAX_LABEL) {
                break;
            }
            kept.add(word);
        }
        while (!kept.isEmpty() && DANGLING.contains(kept.getLast())) {
            kept.removeLast();
        }
        if (!kept.isEmpty()) {
            kept.set(kept.size() - 1, PARTICLE.matcher(kept.getLast()).replaceAll(""));
        }
        return kept.isEmpty() ? words.substring(0, MAX_LABEL) : String.join(" ", kept);
    }
}
