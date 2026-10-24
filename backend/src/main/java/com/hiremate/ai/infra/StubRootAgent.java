package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import com.hiremate.ai.application.CandidateAnalysis;
import com.hiremate.ai.application.CandidateAnalyst;
import com.hiremate.ai.application.ChatContext;
import com.hiremate.ai.application.ChatHistoryTurn;
import com.hiremate.ai.application.ChatItem;
import com.hiremate.ai.application.ChatPlan;
import com.hiremate.ai.application.ChatPlan.EditAction;
import com.hiremate.ai.application.ChatPlan.Intent;
import com.hiremate.ai.application.ChatProgress;
import com.hiremate.ai.application.RootAgent;
import com.hiremate.apply.ApplicantDetail;
import com.hiremate.apply.ApplicantDocument;
import com.hiremate.company.Talent;
import com.hiremate.posting.PostingService;
import com.hiremate.posting.ScreeningRubric;
import com.hiremate.recruit.StageType;
import com.hiremate.screening.CandidateRow;
import com.hiremate.screening.Decision;
import com.hiremate.screening.SelectionMode;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import org.springframework.stereotype.Component;

/**
 * 개발용 Root Agent. 규칙으로 요청을 찾기 · 분석 · 편집으로 나누고, 제출 문서의 낱말로 후보와 근거를 고른다.
 * 차별 조건(나이 · 성별 · 출신 지역 · 혼인 여부 · 신체 조건) 탐색은 실행하지 않는다 (아키텍처 규칙 6).
 */
@Component
@ConditionalOnAiMode(agent = AiAgent.ROOT, mode = AiMode.STUB)
class StubRootAgent implements RootAgent {

    private static final Pattern BLOCKED = Pattern.compile(
            "나이|연령|\\d+\\s*(살|세)|성별|남자|여자|남성|여성|출신|고향|지역|결혼|혼인|기혼|미혼|자녀|키가|키\\s|몸무게|체중|외모|신체|장애");
    private static final Pattern FIND = Pattern.compile("찾아|보여|골라|추려|있어\\?|있나|있는 사람|누구");
    private static final Pattern MISMATCH = Pattern.compile("차이|상충|엇갈|다른 특징|안 맞");
    private static final Pattern MIN_SCORE = Pattern.compile("(\\d{2,3})\\s*점\\s*이상");
    private static final Pattern WORD = Pattern.compile("[가-힣]{2,}|[A-Za-z][A-Za-z+#.]+");
    private static final Pattern PARTICLE = Pattern.compile("(이|가|을|를|은|는|도|만|의|과|와|에서|에|로|으로|이랑|랑)$");
    private static final Set<String> STOP_WORDS = Set.of("찾아줘", "찾아", "보여줘", "보여", "골라줘", "지원자", "사람",
            "그중", "중에서", "추가해줘", "추가", "해줘", "경험", "있는", "있어", "있나", "드러나는", "관련", "가진", "잘",
            "구체적으로", "적힌", "현재", "결과", "좋은", "좋은데", "지금", "우리", "회사", "중요하게", "보는", "요소",
            "도메인", "프로젝트", "지원서", "내용", "가장", "모두", "전체", "명만", "분만", "넣어줘", "선택");
    private static final Map<String, List<String>> SYNONYMS = Map.of(
            "금융", List.of("금융", "은행", "카드", "페이", "증권", "보험", "결제", "정산", "뱅킹", "bank", "card", "pay",
                    "finance", "payment", "settlement"),
            "결제", List.of("결제", "정산", "payment", "settlement"),
            "협업", List.of("협업", "협력", "소통", "함께", "collaboration", "team"),
            "대용량", List.of("대용량", "트래픽", "트랜잭션", "transaction", "traffic"),
            "리더", List.of("리더", "리드", "주도", "lead", "leader"));

    private final CandidateAnalyst analyst;
    private final PostingService postings;

    StubRootAgent(CandidateAnalyst analyst, PostingService postings) {
        this.analyst = analyst;
        this.postings = postings;
    }

    /** 개발용 Root는 대화를 기억하지 않는다. */
    @Override
    public List<ChatHistoryTurn> history(String threadId) {
        return List.of();
    }

    @Override
    public void forget(String threadId) {
    }

    @Override
    public void forgetStage(UUID stageId) {
    }

    @Override
    public ChatPlan plan(ChatContext context, ChatProgress progress) {
        progress.status("요청을 확인하고 있어요");
        return answer(context);
    }

    private ChatPlan answer(ChatContext context) {
        String message = context.message().trim();
        if (BLOCKED.matcher(message).find()) {
            return ChatPlan.answer(Intent.BLOCKED, "나이, 성별, 출신 지역, 혼인 여부, 신체 조건으로는 지원자를 찾거나 거르지 않아요. "
                    + "직무와 관련된 경험이나 역량으로 다시 말씀해 주세요.", List.of(), List.of(), List.of());
        }
        Optional<ChatPlan> unavailable = unavailableData(context, message);
        if (unavailable.isPresent()) {
            return unavailable.get();
        }
        List<CandidateRow> mentioned = mentioned(context, message);
        if (context.stageType() == StageType.INTERVIEW && asksQuestions(message)) {
            return interviewQuestions(context, mentioned);
        }
        Optional<ChatPlan> edit = edit(context, message);
        if (edit.isPresent()) {
            return edit.get();
        }
        if (message.contains("몇 명") || message.contains("몇명")) {
            return counts(context);
        }
        if (message.contains("합격한") || message.contains("불합격한")) {
            return decided(context, message.contains("불합격한") ? Decision.FAIL : Decision.PASS);
        }
        if (!mentioned.isEmpty()) {
            return analyze(context, message, mentioned);
        }
        if (FIND.matcher(message).find() || message.startsWith("그중") || message.contains("추가해")) {
            return find(context, message);
        }
        return ChatPlan.answer(Intent.CLARIFY, "조건으로 지원자를 찾거나(\"금융 경험이 있는 지원자 찾아줘\"), "
                + "@로 지원자를 골라 물어보세요(\"@이름 강점과 확인할 점은?\").", List.of(), List.of(), List.of());
    }

    /** 아직 없는 전형 결과를 물으면 없다고 답하고, 지금 할 수 있는 질문을 제안한다 (ASK-01). */
    private static Optional<ChatPlan> unavailableData(ChatContext context, String message) {
        boolean asksAssessment = message.contains("평가") || message.contains("과제") || message.contains("점수");
        boolean asksInterview = message.contains("면접 답변") || message.contains("답변에서");
        List<StageType> previous = context.stages().stream()
                .takeWhile(stage -> !stage.id().equals(context.stageId()))
                .map(ChatContext.Stage::type)
                .toList();
        boolean hasAssessment = context.stageType() != StageType.DOCUMENT || previous.contains(StageType.ASSESSMENT);
        boolean hasInterview = context.stageType() == StageType.INTERVIEW || previous.contains(StageType.INTERVIEW);
        if (asksAssessment && !hasAssessment && !message.contains("서류")) {
            return Optional.of(ChatPlan.answer(Intent.CLARIFY, "아직 평가 결과가 없어요. "
                    + "지원서에서 협업 경험이 약한 지원자를 찾아볼까요?", List.of(), List.of(), List.of()));
        }
        if (asksInterview && !hasInterview) {
            return Optional.of(ChatPlan.answer(Intent.CLARIFY, "아직 면접 답변 기록이 없어요. "
                    + "@로 지원자를 골라 면접에서 확인할 점을 물어볼 수 있어요.", List.of(), List.of(), List.of()));
        }
        return Optional.empty();
    }

    /** 선택 지원자 편집: "정하늘도 추가해줘", "@김서준 빼줘", "이 3명 빼줘", "비워줘", "되돌려줘". */
    private static Optional<ChatPlan> edit(ChatContext context, String message) {
        if (message.contains("비워")) {
            return Optional.of(new ChatPlan(Intent.EDIT, null, EditAction.CLEAR, List.of(),
                    "선택 지원자를 비웠어요. [되돌리기]로 돌아갈 수 있어요.", List.of(), List.of(), List.of(), List.of()));
        }
        if (message.contains("되돌려") || message.contains("이전 선택")) {
            return Optional.of(new ChatPlan(Intent.EDIT, null, EditAction.RESTORE, List.of(),
                    "이전 선택 지원자로 되돌렸어요.", List.of(), List.of(), List.of(), List.of()));
        }
        boolean remove = message.contains("빼") || message.contains("제외");
        boolean add = message.contains("추가") || message.contains("넣어");
        if (!remove && !add) {
            return Optional.empty();
        }
        List<CandidateRow> targets = message.contains("이 ") && message.matches(".*이\\s*\\d+\\s*명.*")
                ? context.candidates().stream().filter(row -> context.checked().contains(row.applicationId())).toList()
                : mentioned(context, message);
        if (targets.isEmpty()) {
            if (add && FIND.matcher(message).find() || add && !remove && message.contains("경험")) {
                return Optional.empty();
            }
            return add && !remove ? Optional.empty() : Optional.of(ChatPlan.answer(Intent.CLARIFY,
                    "누구를 말씀하시는지 모르겠어요. @로 지원자를 골라 다시 말씀해 주세요.", List.of(), List.of(), List.of()));
        }
        List<String> sameName = targets.stream().map(CandidateRow::name)
                .filter(name -> context.candidates().stream().filter(row -> row.name().equals(name)).count() > 1)
                .distinct().toList();
        if (!sameName.isEmpty() && context.mentions().isEmpty()) {
            return Optional.of(ChatPlan.answer(Intent.CLARIFY, String.join(", ", sameName)
                    + " 이름의 지원자가 여러 명이에요. @로 골라 주세요.", List.of(), List.of(), List.of()));
        }
        String names = targets.stream().map(CandidateRow::name).collect(Collectors.joining(", "));
        long after = context.candidates().stream().filter(CandidateRow::selected).count()
                + (remove ? -targets.stream().filter(CandidateRow::selected).count()
                        : targets.stream().filter(row -> !row.selected()).count());
        return Optional.of(new ChatPlan(Intent.EDIT, null, remove ? EditAction.REMOVE : EditAction.ADD,
                targets.stream().map(CandidateRow::applicationId).toList(),
                names + " 님을 선택 지원자" + (remove ? "에서 뺐어요." : "에 넣었어요.") + " 지금 **" + after + "명**이에요.",
                List.of(), List.of(), List.of(), List.of()));
    }

    /** 지원자 찾기. 제출 문서와 점수로 후보를 고르고, 근거 문장을 붙여 리스트에 표시한다. */
    private ChatPlan find(ChatContext context, String message) {
        SelectionMode mode = message.startsWith("그중") || message.startsWith("그 중") || message.startsWith("이 중")
                ? SelectionMode.NARROW
                : message.contains("추가") ? SelectionMode.ADD : SelectionMode.REPLACE;
        Stream<CandidateRow> pool = context.candidates().stream()
                .filter(row -> row.decision() == Decision.PENDING && row.aboveLine());
        if (mode == SelectionMode.NARROW) {
            pool = pool.filter(CandidateRow::selected);
        }
        List<CandidateRow> base = pool.toList();
        List<String> agents = new ArrayList<>(List.of("Application Agent"));

        if (MISMATCH.matcher(message).find() && (message.contains("평가") || message.contains("점수"))) {
            return mismatch(context, base, mode);
        }
        List<CandidateRow> scored = base;
        Matcher minimum = MIN_SCORE.matcher(message);
        if (minimum.find()) {
            BigDecimal threshold = new BigDecimal(minimum.group(1));
            scored = base.stream().filter(row -> row.score() != null && row.score().compareTo(threshold) >= 0).toList();
            agents.add("Assessment Agent");
        } else if ((message.contains("평가") || message.contains("점수")) && message.contains("좋")) {
            scored = base.stream()
                    .filter(row -> row.score() != null && row.score().compareTo(BigDecimal.valueOf(80)) >= 0)
                    .toList();
            agents.add("Assessment Agent");
        } else if (message.contains("결과가 아직 없") || message.contains("결과 없는")) {
            scored = base.stream().filter(row -> row.score() == null).toList();
        }

        List<List<String>> concepts = concepts(context, message);
        List<Match> matches = new ArrayList<>();
        for (CandidateRow row : scored) {
            if (concepts.isEmpty()) {
                matches.add(new Match(row, 0, row.lastCompany() == null ? "" : row.lastCompany(), null));
                continue;
            }
            int hits = 0;
            String evidence = null;
            String source = null;
            for (List<String> terms : concepts) {
                Optional<Map.Entry<String, String>> found = evidence(context.documents().get(row.applicationId()),
                        row, terms);
                if (found.isPresent()) {
                    hits++;
                    if (evidence == null) {
                        evidence = found.get().getKey();
                        source = found.get().getValue();
                    }
                }
            }
            if (hits > 0) {
                matches.add(new Match(row, hits, evidence, source));
            }
        }
        matches.sort(Comparator.comparing(Match::hits).reversed());
        if (matches.isEmpty()) {
            return ChatPlan.answer(Intent.ANSWER, "조건에 맞는 지원자를 찾지 못했어요. 선택 지원자는 그대로예요.",
                    List.of(), List.of(), agents);
        }
        List<ChatItem> items = matches.stream().limit(5)
                .map(match -> new ChatItem(match.row().applicationId(), match.row().name(), shorten(match.evidence()),
                        null))
                .toList();
        List<String> sources = matches.stream().map(Match::source).filter(source -> source != null).distinct().toList();
        String message0 = switch (mode) {
            case REPLACE -> "지원자 {total}명 중 조건에 맞는 **{count}명**을 선택했어요.";
            case ADD -> "조건에 맞는 **{count}명**을 선택 지원자에 더했어요.";
            case NARROW -> base.size() + "명 중 **{count}명**으로 좁혔어요.";
        };
        List<UUID> targets = matches.stream().map(match -> match.row().applicationId()).toList();
        return new ChatPlan(Intent.FIND, mode, null, targets, message0, items, sources, agents, List.of());
    }

    private static boolean asksQuestions(String message) {
        boolean question = message.contains("질문") && (message.contains("만들") || message.contains("추천")
                || message.contains("생성") || message.contains("다시") || message.contains("추가"));
        return question || message.contains("면접") && message.contains("확인");
    }

    /** 면접 전형에서 맞춤 질문을 만들어 카드에 넣는다. 대상이 없으면 결정하지 않은 지원자 전원이다. */
    private static ChatPlan interviewQuestions(ChatContext context, List<CandidateRow> mentioned) {
        List<CandidateRow> targets = !mentioned.isEmpty() ? mentioned
                : !context.checked().isEmpty()
                        ? context.candidates().stream().filter(row -> context.checked().contains(row.applicationId()))
                                .toList()
                        : context.candidates().stream().filter(row -> row.decision() == Decision.PENDING).limit(20)
                                .toList();
        return new ChatPlan(Intent.ANSWER, null, null, List.of(),
                "이전 전형 결과를 보고 " + targets.size() + "명의 맞춤 질문을 만들어 카드에 넣었어요.", List.of(),
                List.of("이력서", "평가 결과", "면접 답변 기록"), List.of("Interview Agent"),
                targets.stream().map(CandidateRow::applicationId).toList());
    }

    /** 평가 결과와 지원서가 엇갈리는 후보. 평가 점수와 서류 점수 차이가 15점 이상인 지원자를 고른다. */
    private static ChatPlan mismatch(ChatContext context, List<CandidateRow> base, SelectionMode mode) {
        List<CandidateRow> found = base.stream()
                .filter(row -> row.score() != null && context.documentScores().containsKey(row.applicationId()))
                .filter(row -> row.score().subtract(context.documentScores().get(row.applicationId())).abs()
                        .compareTo(BigDecimal.valueOf(15)) >= 0)
                .sorted(Comparator.comparing((CandidateRow row) -> row.score()
                        .subtract(context.documentScores().get(row.applicationId())).abs()).reversed())
                .toList();
        List<String> agents = List.of("Assessment Agent", "Application Agent");
        if (found.isEmpty()) {
            return ChatPlan.answer(Intent.ANSWER, "평가 결과와 지원서 차이가 큰 지원자를 찾지 못했어요. 선택 지원자는 그대로예요.",
                    List.of(), List.of(), agents);
        }
        List<ChatItem> items = found.stream().limit(5).map(row -> {
            BigDecimal document = context.documentScores().get(row.applicationId());
            String direction = row.score().compareTo(document) > 0 ? "평가가 지원서보다 높음" : "지원서에 비해 평가가 낮음";
            return new ChatItem(row.applicationId(), row.name(),
                    "평가 " + row.score().stripTrailingZeros().toPlainString() + "점 · 서류 "
                            + document.stripTrailingZeros().toPlainString() + "점, " + direction,
                    null);
        }).toList();
        return new ChatPlan(Intent.FIND, mode, null, found.stream().map(CandidateRow::applicationId).toList(),
                "평가 결과와 지원서 차이가 큰 **{count}명**을 골랐어요.", items, List.of("평가 결과", "이력서"), agents, List.of());
    }

    /** 특정 지원자 분석 · 의견 · 비교 · 면접 질문. 화면은 바꾸지 않고 대화로 답한다. */
    private ChatPlan analyze(ChatContext context, String message, List<CandidateRow> targets) {
        List<String> agents = List.of("Application Agent");
        if (message.contains("인재상") || message.contains("잘 맞") || message.contains("문화")) {
            CandidateRow row = targets.getFirst();
            List<Talent> talents = context.company().talents();
            if (talents.isEmpty()) {
                return ChatPlan.answer(Intent.ANSWER, "설정 › 회사 소개에 인재상을 등록하면 인재상과 맞춰 볼 수 있어요.",
                        List.of(), List.of(), agents);
            }
            List<ChatItem> items = new ArrayList<>();
            Set<String> sources = new LinkedHashSet<>();
            for (Talent talent : talents) {
                Optional<Map.Entry<String, String>> found = evidence(context.documents().get(row.applicationId()), row,
                        keywords(talent.title() + " " + talent.description()));
                found.ifPresent(entry -> sources.add(entry.getValue()));
                items.add(new ChatItem(row.applicationId(), talent.title(),
                        found.map(entry -> shorten(entry.getKey())).orElse("근거가 부족해 면접에서 확인이 필요해요"),
                        found.isPresent() ? "OK" : "CHECK"));
            }
            long ok = items.stream().filter(item -> "OK".equals(item.status())).count();
            return ChatPlan.answer(Intent.ANSWER, "인재상 " + talents.size() + "가지 중 **" + ok + "가지**는 근거가 충분하고, "
                    + (talents.size() - ok) + "가지는 면접에서 확인이 필요해요.", items, List.copyOf(sources), agents);
        }
        if (targets.size() > 1 || message.contains("비교")) {
            List<ChatItem> items = targets.stream().map(row -> {
                CandidateAnalysis analysis = analyst.analyze(detail(context, row), context.posting(), rubric(context));
                long met = analysis.conditions().stream().filter(CandidateAnalysis.Condition::met).count();
                String notable = analysis.notable().isEmpty()
                        ? "" : " · " + shorten(analysis.notable().getFirst().text());
                return new ChatItem(row.applicationId(), row.name(),
                        "공고 조건 " + met + "/" + analysis.conditions().size() + " 충족" + notable, null);
            }).toList();
            return ChatPlan.answer(Intent.ANSWER, targets.size() + "명을 공고 조건과 제출 자료로 비교했어요.", items,
                    List.of("이력서", "자기소개서"), agents);
        }
        CandidateRow row = targets.getFirst();
        CandidateAnalysis analysis = analyst.analyze(detail(context, row), context.posting(), rubric(context));
        if (message.contains("면접") || message.contains("질문")) {
            List<ChatItem> questions = new ArrayList<>();
            analysis.checks().stream().limit(2).forEach(check -> questions.add(new ChatItem(row.applicationId(),
                    "확인 필요", "자격 요건과 관련해 직접 해 본 일을 구체적인 사례로 설명해 주세요.", "CHECK")));
            analysis.notable().stream().limit(2).forEach(found -> questions.add(new ChatItem(row.applicationId(),
                    "역할 확인", "\"" + shorten(found.text()) + "\"에서 본인이 맡은 역할과 판단 근거는 무엇이었나요?", null)));
            if (questions.isEmpty()) {
                questions.add(new ChatItem(row.applicationId(), "경험 확인", "지원서에 적은 대표 경험을 구체적으로 설명해 주세요.", null));
            }
            return ChatPlan.answer(Intent.ANSWER, row.name() + " 님은 면접에서 이런 부분을 확인하면 좋아요.", questions,
                    List.of("이력서", "자기소개서"), List.of("Interview Agent"));
        }
        List<ChatItem> items = new ArrayList<>();
        analysis.notable().forEach(found -> items.add(new ChatItem(row.applicationId(), "강점", shorten(found.text()),
                "OK")));
        analysis.checks().forEach(check -> items.add(new ChatItem(row.applicationId(), "확인할 점", shorten(check.text()),
                "CHECK")));
        long met = analysis.conditions().stream().filter(CandidateAnalysis.Condition::met).count();
        return ChatPlan.answer(Intent.ANSWER, row.name() + " 님은 공고 조건 " + analysis.conditions().size() + "개 중 **" + met
                + "개**의 근거가 제출 문서에 있어요.", items, List.of("이력서", "자기소개서"), agents);
    }

    private static ChatPlan counts(ChatContext context) {
        Map<Decision, Long> counts = context.candidates().stream()
                .collect(Collectors.groupingBy(CandidateRow::decision, Collectors.counting()));
        long pending = counts.getOrDefault(Decision.PENDING, 0L);
        return ChatPlan.answer(Intent.ANSWER, "미결정은 **" + pending + "명**이에요. 합격 "
                + counts.getOrDefault(Decision.PASS, 0L) + "명, 불합격 " + counts.getOrDefault(Decision.FAIL, 0L)
                + "명이고, 확정하면 미결정은 모두 불합격으로 처리돼요.",
                List.of(), List.of(), List.of());
    }

    private static ChatPlan decided(ChatContext context, Decision decision) {
        List<ChatItem> items = context.candidates().stream().filter(row -> row.decision() == decision)
                .map(row -> new ChatItem(row.applicationId(), row.name(), career(row), null))
                .toList();
        return ChatPlan.answer(Intent.ANSWER, (decision == Decision.PASS ? "합격" : "불합격") + "으로 결정한 지원자는 **"
                + items.size() + "명**이에요. 결정한 지원자는 리스트에 결정 색으로 표시돼요.", items, List.of(), List.of());
    }

    /** 멘션한 지원자와 문장 속 이름으로 대상을 찾는다. */
    private static List<CandidateRow> mentioned(ChatContext context, String message) {
        Set<UUID> ids = new LinkedHashSet<>(context.mentions());
        context.candidates().stream()
                .filter(row -> message.contains(row.name()))
                .forEach(row -> ids.add(row.applicationId()));
        return context.candidates().stream().filter(row -> ids.contains(row.applicationId())).toList();
    }

    /** 요청에서 찾을 개념. 개념마다 같은 뜻의 낱말 목록이다. */
    private static List<List<String>> concepts(ChatContext context, String message) {
        List<List<String>> concepts = new ArrayList<>();
        if (message.contains("인재상") || message.contains("중요하게")) {
            context.company().talents()
                    .forEach(talent -> concepts.add(keywords(talent.title() + " " + talent.description())));
        }
        for (String word : keywords(message.replaceAll("@\\S+", ""))) {
            if (word.equals("인재상")) {
                continue;
            }
            concepts.add(SYNONYMS.getOrDefault(word, List.of(word)));
        }
        return concepts;
    }

    private static List<String> keywords(String text) {
        return WORD.matcher(text).results()
                .map(match -> PARTICLE.matcher(match.group()).replaceFirst("").toLowerCase(Locale.ROOT))
                .filter(word -> word.length() >= 2 && !STOP_WORDS.contains(word))
                .distinct()
                .toList();
    }

    /** 낱말이 들어 있는 첫 문장과 출처. */
    private static Optional<Map.Entry<String, String>> evidence(List<ApplicantDocument> documents, CandidateRow row,
            List<String> terms) {
        if (row.lastCompany() != null && terms.stream().anyMatch(term -> row.lastCompany().toLowerCase(Locale.ROOT)
                .contains(term))) {
            return Optional.of(Map.entry(career(row), "이력서"));
        }
        for (ApplicantDocument document : documents == null ? List.<ApplicantDocument>of() : documents) {
            for (String line : document.text().split("\\n+|(?<=[.!?])\\s+")) {
                String lower = line.toLowerCase(Locale.ROOT);
                if (line.strip().length() >= 4 && terms.stream().anyMatch(lower::contains)) {
                    return Optional.of(Map.entry(line.strip(), document.type().label()));
                }
            }
        }
        return Optional.empty();
    }

    private static ApplicantDetail detail(ChatContext context, CandidateRow row) {
        List<ApplicantDocument> documents = context.documents().getOrDefault(row.applicationId(), List.of());
        return new ApplicantDetail(null, "", null, documents);
    }

    private static String career(CandidateRow row) {
        if (row.careerYears() == null || row.careerYears() == 0) {
            return "신입";
        }
        return "경력 " + row.careerYears() + "년" + (row.lastCompany() == null ? "" : " · " + row.lastCompany());
    }

    private static String shorten(String text) {
        String trimmed = text.strip().replaceAll("\\s+", " ");
        return trimmed.length() > 48 ? trimmed.substring(0, 47) + "…" : trimmed;
    }

    private ScreeningRubric rubric(ChatContext context) {
        return postings.screeningRubric(context.company().companyId(), context.recruitmentId());
    }

    private record Match(CandidateRow row, int hits, String evidence, String source) {
    }
}
