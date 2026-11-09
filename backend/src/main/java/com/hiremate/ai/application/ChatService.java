package com.hiremate.ai.application;

import com.hiremate.apply.ApplicantDocument;
import com.hiremate.apply.ApplicationService;
import com.hiremate.assessment.AssessmentService;
import com.hiremate.company.CompanyService;
import com.hiremate.global.ApiException;
import com.hiremate.interview.InterviewService;
import com.hiremate.interview.InterviewSessions;
import com.hiremate.interview.InterviewView;
import com.hiremate.interview.InterviewerRole;
import com.hiremate.interview.KeptQuestions;
import com.hiremate.posting.PostingService;
import com.hiremate.recruit.RecruitService;
import com.hiremate.recruit.RecruitmentInfo;
import com.hiremate.recruit.StageInfo;
import com.hiremate.recruit.StageStatus;
import com.hiremate.recruit.StageType;
import com.hiremate.report.AgentReportKind;
import com.hiremate.screening.CandidateFilter;
import com.hiremate.screening.CandidatePage;
import com.hiremate.screening.CandidateRow;
import com.hiremate.screening.ScreeningService;
import com.hiremate.screening.SelectionMode;
import com.hiremate.screening.StageTabService;
import com.hiremate.screening.StageTabView;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.TreeMap;
import java.util.UUID;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

/**
 * AI Chat. Root Agent의 계획 가운데 선택 지원자 변경은 screening 모듈이 대상과 권한을 검증해 실행한다.
 * 합격 · 불합격 결정은 이 경로로 할 수 없다 (아키텍처 규칙 1, 2).
 */
@Service
public class ChatService {

    /** 비교 리포트의 지원자 수 범위. 도넛 · 막대가 견줄 수 있는 만큼이다. */
    static final int MIN_COMPARED = 2;
    static final int MAX_COMPARED = 5;

    private static final Logger log = LoggerFactory.getLogger(ChatService.class);
    private static final Pattern QUESTION_COUNT = Pattern.compile("(?<!\\d)(\\d+)\\s*(?:개|문항)");
    private static final int CANDIDATE_PAGE_SIZE = 200;
    private static final String KEPT_QUESTIONS = "직접 넣은 질문 %d개와 답변을 기록한 질문 %d개는 남겼어요.";
    public static final String INTERVIEWER_LOCKED =
            "면접관 모드에서는 선택 지원자를 바꿀 수 없어요. 지원자 분석과 질문 만들기는 할 수 있어요.";
    /** NCS를 참고하라고 했는데 인용한 질문이 없을 때 Chat 답 끝에 붙이는 안내. */
    static final String NCS_MISSED = "요청하신 NCS를 참고하지 못해, NCS 없이 질문을 만들었어요.";
    static final String INTERVIEWER_REPLACE = "면접관 모드에서는 기존 질문을 지우지 않고 새 질문만 더해요.";

    private final ScreeningService screening;
    private final RecruitService recruits;
    private final ApplicationService applications;
    private final CompanyService companies;
    private final PostingService postings;
    private final RootAgent root;
    private final InterviewAiService interviews;
    private final AiSettings settings;
    private final AssessmentService assessments;
    private final StageTabService tabs;
    private final ReportComposer composer;
    private final InterviewSessions sessions;

    public ChatService(ScreeningService screening, RecruitService recruits, ApplicationService applications,
            CompanyService companies, PostingService postings, RootAgent root, InterviewAiService interviews,
            AiSettings settings, AssessmentService assessments, StageTabService tabs, ReportComposer composer,
            InterviewSessions sessions) {
        this.sessions = sessions;
        this.screening = screening;
        this.recruits = recruits;
        this.applications = applications;
        this.companies = companies;
        this.postings = postings;
        this.root = root;
        this.interviews = interviews;
        this.settings = settings;
        this.assessments = assessments;
        this.tabs = tabs;
        this.composer = composer;
    }

    /**
     * 전형과 탭을 확인하고 Root에 넘길 자료를 모은다. 다른 기업의 전형이나 다른 전형의 탭이면 찾을 수 없다.
     * 스트림을 열기 전에 부른다. 선택 표시는 그 탭 기준이다.
     */
    public ChatInput prepare(UUID companyId, UUID stageId, UUID tabId, ChatAsker asker, String message,
            List<UUID> mentions, List<UUID> checked) {
        return prepare(companyId, stageId, tabId, asker, message, mentions, checked, null);
    }

    /**
     * interviewerId가 있으면 면접관 모드의 Chat이다. Root에는 그 면접관이 배정된 지원자만 넘기고, 이번 전형의 결정은
     * 숨기며, 선택 지원자는 바꿀 수 없다고 알린다. 면접관 의견은 어느 Chat에도 넘기지 않는다.
     */
    public ChatInput prepare(UUID companyId, UUID stageId, UUID tabId, ChatAsker asker, String message,
            List<UUID> mentions, List<UUID> checked, UUID interviewerId) {
        RecruitmentInfo recruitment = recruits.getByStage(companyId, stageId);
        StageInfo stage = recruitment.stage(stageId).orElseThrow();
        Map<UUID, InterviewerRole> interviewerRoles = interviewerId == null ? Map.of()
                : sessions.roles(companyId, interviewerId, stageId);
        List<CandidateRow> candidates = interviewerId == null ? allCandidates(companyId, stageId, tabId)
                : allCandidates(companyId, stageId, null).stream()
                        .filter(row -> interviewerRoles.containsKey(row.applicationId()))
                        .map(CandidateRow::hideDecision).toList();
        if (interviewerId != null) {
            mentions = mentions.stream().filter(interviewerRoles::containsKey).toList();
            checked = checked.stream().filter(interviewerRoles::containsKey).toList();
        }
        mentions = withNamed(message, mentions, candidates);
        List<ChatContext.Stage> stages = recruitment.stages().stream()
                .map(other -> new ChatContext.Stage(other.id(), other.name(), other.type(), other.status()))
                .toList();
        Map<UUID, InterviewView> interviewViews = stage.type() == StageType.INTERVIEW
                ? interviews.views(companyId, stageId, candidates.stream().map(CandidateRow::applicationId).toList())
                : Map.of();
        Map<UUID, List<InterviewerMemo>> interviewerMemos = new HashMap<>();
        if (stage.type() == StageType.INTERVIEW) {
            candidates.forEach(candidate -> interviewerMemos.put(candidate.applicationId(),
                    interviews.memos(companyId, stageId, candidate.applicationId())));
        }
        Map<UUID, ChatContext.Assessment> assessmentScores = new HashMap<>();
        if (stage.type() == StageType.ASSESSMENT) {
            candidates.forEach(candidate -> assessments.find(companyId, stageId, candidate.applicationId())
                    .ifPresent(result -> assessmentScores.put(candidate.applicationId(),
                            new ChatContext.Assessment(AssessmentAnalysisListener.areas(result), result.grade()))));
        }
        // 대화방은 탭마다 하나이고 같은 기업 담당자가 함께 쓴다. 전형이 끝나도 남는다
        Map<UUID, List<ApplicantDocument>> documents = applications.documents(companyId, recruitment.id());
        if (interviewerId != null) {
            documents = documents.entrySet().stream().filter(entry -> interviewerRoles.containsKey(entry.getKey()))
                    .collect(Collectors.toMap(Map.Entry::getKey, Map.Entry::getValue));
        }
        ChatContext context = new ChatContext(stageId, recruitment.id(), threadId(companyId, stageId, tabId),
                stage.name(),
                interviewerId == null && stage.status() == StageStatus.ACTIVE, stage.type(), stages,
                candidates, documents, interviewViews,
                mentions, checked, companies.profile(companyId),
                postings.draftContext(companyId, recruitment.id()).content(), message, interviewerMemos,
                assessmentScores, asker, interviewerId != null, chatTabs(companyId, stageId, tabId, interviewerId));
        return new ChatInput(companyId, stageId, tabId, asker == null ? null : asker.memberId(), stage.status(),
                candidates, context, interviewerRoles);
    }

    /**
     * 문장에 이름을 그대로 쓴 지원자도 멘션한 것처럼 넘긴다(@ 없이 "신예준 단점 알려줘"). 멘션 뒤에 문장에 나온 순서로
     * 붙인다. 같은 이름이 둘 이상이면 누구인지 알 수 없어 붙이지 않고, 다른 이름 안에 든 짧은 이름(김민 ⊂ 김민수)은 긴
     * 이름만 친다.
     */
    static List<UUID> withNamed(String message, List<UUID> mentions, List<CandidateRow> candidates) {
        if (message == null || message.isBlank()) {
            return mentions;
        }
        Map<String, List<UUID>> byName = new HashMap<>();
        candidates.stream().filter(row -> row.name() != null && row.name().strip().length() >= 2)
                .forEach(row -> byName.computeIfAbsent(row.name().strip(), name -> new ArrayList<>())
                        .add(row.applicationId()));
        // 긴 이름부터 찾고 찾은 자리는 지워, 김민수 속의 김민을 따로 치지 않는다
        List<String> names = byName.keySet().stream()
                .sorted((left, right) -> right.length() - left.length()).toList();
        String rest = message;
        Map<Integer, UUID> named = new TreeMap<>();
        for (String name : names) {
            int index = rest.indexOf(name);
            if (index < 0) {
                continue;
            }
            List<UUID> ids = byName.get(name);
            if (ids.size() == 1) {
                named.put(index, ids.getFirst());
            }
            rest = rest.replace(name, "*".repeat(name.length()));
        }
        if (named.isEmpty()) {
            return mentions;
        }
        List<UUID> merged = new ArrayList<>(mentions);
        named.values().stream().filter(id -> !merged.contains(id)).forEach(merged::add);
        return List.copyOf(merged);
    }

    /** 다른 탭의 선택 지원자를 가리킬 수 있게 HR 공유 탭을 넘긴다. 면접관 모드는 자기 탭만 쓰므로 넘기지 않는다. */
    private List<ChatContext.Tab> chatTabs(UUID companyId, UUID stageId, UUID tabId, UUID interviewerId) {
        if (interviewerId != null) {
            return List.of();
        }
        return tabs.selections(companyId, stageId).stream()
                .map(tab -> new ChatContext.Tab(tab.id(), tab.name(), tab.id().equals(tabId), tab.applicationIds()))
                .toList();
    }

    private List<CandidateRow> allCandidates(UUID companyId, UUID stageId, UUID tabId) {
        List<CandidateRow> all = new ArrayList<>();
        CandidatePage page;
        int pageNumber = 0;
        do {
            page = screening.candidates(companyId, stageId, tabId, null, CandidateFilter.NONE,
                    pageNumber++, CANDIDATE_PAGE_SIZE);
            all.addAll(page.items());
        } while (!page.items().isEmpty() && all.size() < page.total());
        return List.copyOf(all);
    }

    /**
     * Root에 묻고 계획을 반영한다. Root의 진행 알림은 progress로 그대로 넘긴다. 화면 연결이 끊겨 Root 답을 받기 전에
     * progress가 예외를 던지면 거기서 멈춘다. Root가 답한 뒤에는 Root가 대화를 이미 남겼으므로 연결이 끊겨도 반영까지 마친다.
     */
    public ChatAnswer run(ChatInput input, ChatProgress progress) {
        UUID companyId = input.companyId();
        UUID stageId = input.stageId();
        UUID tabId = input.tabId();
        List<CandidateRow> candidates = input.candidates();
        ChatPlan previous = root.plan(input.context(), progress);
        ChatPlan plan = previous;
        ChatProgress after = ChatProgress.quiet(progress);

        boolean changesSelection = plan.intent() == ChatPlan.Intent.FIND || plan.intent() == ChatPlan.Intent.EDIT;
        if (changesSelection && input.interviewer()) {
            return completed(input.context(), previous, ChatPlan.answer(ChatPlan.Intent.CLARIFY, INTERVIEWER_LOCKED,
                    List.of(), List.of(), List.of()), false, 0, candidates.size());
        }
        if (changesSelection && input.status() != StageStatus.ACTIVE) {
            return completed(input.context(), previous, ChatPlan.answer(ChatPlan.Intent.CLARIFY,
                    "결과를 확정한 전형이라 선택 지원자를 바꿀 수 없어요. 분석이나 요약은 계속 물어볼 수 있어요.",
                    List.of(), List.of(), List.of()), false, 0, candidates.size());
        }
        if (!plan.questionTargets().isEmpty()) {
            plan = withQuestions(companyId, stageId, plan, candidates, input.context().message(), after,
                    input.interviewer() ? input.interviewerRoles() : null);
        }
        if (plan.intent() == ChatPlan.Intent.REPORT && plan.report() != null) {
            return completed(input.context(), previous, report(input, plan), false, 0, candidates.size());
        }
        int applied = 0;
        boolean changed = false;
        if (plan.intent() == ChatPlan.Intent.FIND) {
            Map<UUID, Boolean> before = selected(companyId, stageId, tabId);
            List<UUID> targets = List.of();
            if (!plan.targets().isEmpty()) {
                targets = screening.applyAiSelection(companyId, stageId, tabId, plan.mode(), plan.targets());
            }
            Map<UUID, Boolean> current = selected(companyId, stageId, tabId);
            changed = !before.equals(current);
            applied = targets.size();
            plan = appliedFind(plan, targets, before.keySet(), current.keySet());
        } else if (plan.intent() == ChatPlan.Intent.EDIT) {
            Map<UUID, Boolean> before = selected(companyId, stageId, tabId);
            edit(companyId, stageId, tabId, plan);
            Map<UUID, Boolean> current = selected(companyId, stageId, tabId);
            changed = !before.equals(current);
            List<UUID> targets = switch (plan.edit()) {
                case ADD -> plan.targets().stream().distinct()
                        .filter(id -> current.containsKey(id) && !before.containsKey(id)).toList();
                case REMOVE -> plan.targets().stream().distinct()
                        .filter(id -> before.containsKey(id) && !current.containsKey(id)).toList();
                case CLEAR -> before.keySet().stream().filter(id -> !current.containsKey(id)).toList();
            };
            applied = targets.size();
            plan = appliedEdit(plan, targets, current.keySet());
        }
        return completed(input.context(), previous, plan, changed, applied, candidates.size());
    }

    private ChatAnswer completed(ChatContext context, ChatPlan previous, ChatPlan plan, boolean changed,
            int applied, int total) {
        String message = plan.message().replace("{count}", String.valueOf(applied))
                .replace("{total}", String.valueOf(total));
        ChatPlan finalPlan = plan.with(message, plan.items());
        if (!context.threadId().isBlank()) {
            try {
                root.applied(new ChatApplied(context.threadId(), context.message(), previous, finalPlan));
            } catch (ApiException unavailable) {
                log.warn("Could not confirm applied chat plan for stage {}", context.stageId(), unavailable);
            }
        }
        return answer(finalPlan, changed, applied, total);
    }

    /**
     * 리포트 요청을 실행한다. 비교는 현재 전형 지원자 2~5명만 받고, 전형 결과 리포트는 같은 채용에서 결과를 확정하고
     * 안내를 모두 보낸 전형만 받는다.
     * 저장된 전형 결과 리포트가 있으면 다시 만들지 않는다. 이전 전형처럼 다른 전형의 리포트는 저장된 것만 연다.
     * 만든 · 찾은 리포트 ID를 계획에 적어 대화 기록에서도 다시 연다.
     */
    private ChatPlan report(ChatInput input, ChatPlan plan) {
        ChatReport request = plan.report();
        if (request.kind() == ChatReport.Kind.COMPARE) {
            Set<UUID> here = input.candidates().stream().map(CandidateRow::applicationId).collect(Collectors.toSet());
            List<UUID> targets = request.targets().stream().distinct().filter(here::contains).toList();
            if (targets.size() < MIN_COMPARED) {
                return ChatPlan.answer(ChatPlan.Intent.CLARIFY,
                        "비교할 지원자를 현재 전형에서 두 명 이상 알려 주세요. @이름으로 지정하거나 선택 지원자에 넣어 주세요.",
                        List.of(), plan.sources(), plan.agents());
            }
            List<UUID> compared = targets.stream().limit(MAX_COMPARED).toList();
            UUID reportId = composer.request(input.companyId(), input.stageId(), AgentReportKind.COMPARE, compared,
                    request.focus(), request.brief(), input.memberId());
            String message = targets.size() > MAX_COMPARED
                    ? plan.message() + " 비교는 " + MAX_COMPARED + "명까지라 앞의 " + MAX_COMPARED + "명으로 만들어요."
                    : plan.message();
            return withReport(plan.with(message, plan.items()), request.withReport(reportId));
        }
        UUID stageId = request.stageId() != null ? request.stageId() : input.stageId();
        RecruitmentInfo recruitment = recruits.getByStage(input.companyId(), input.stageId());
        StageInfo stage = recruitment.stage(stageId).orElse(null);
        if (stage == null) {
            return ChatPlan.answer(ChatPlan.Intent.CLARIFY, "이 채용의 전형이 아니라 리포트를 열 수 없어요.", List.of(),
                    plan.sources(), plan.agents());
        }
        if (stage.confirmedAt() == null) {
            return ChatPlan.answer(ChatPlan.Intent.CLARIFY,
                    stage.name() + "은 아직 결과를 확정하지 않아 전형 결과 리포트가 없어요. 확정하면 Report Agent가 써요.",
                    List.of(), plan.sources(), plan.agents());
        }
        String title = stageTitle(stage.name());
        if (!composer.stageReportOpen(input.companyId(), stageId)) {
            return ChatPlan.answer(ChatPlan.Intent.CLARIFY,
                    title + " 결과 리포트는 합격 · 불합격 안내를 모두 보낸 뒤에 열 수 있어요.", List.of(),
                    plan.sources(), plan.agents());
        }
        UUID saved = composer.latestStageReport(input.companyId(), stageId);
        if (stageId.equals(input.stageId())) {
            UUID reportId = composer.stageReport(input.companyId(), stageId, input.memberId());
            String message = saved != null ? title + " 결과 리포트를 열어요."
                    : title + " 결과 리포트를 Report Agent가 쓰고 있어요.";
            return withReport(plan.with(message, plan.items()), request.withReport(reportId));
        }
        // 다른 전형의 리포트는 토큰을 아끼려고 저장된 것만 연다 (현재 전형에 남은 지원자로 다시 쓰지 않는다)
        if (saved == null) {
            return ChatPlan.answer(ChatPlan.Intent.CLARIFY,
                    "저장된 " + title + " 결과 리포트가 없어요. " + title + " 종료 화면에서 만들 수 있어요.",
                    List.of(), plan.sources(), plan.agents());
        }
        return withReport(plan.with(title + " 결과 리포트를 열어요.", plan.items()), request.withReport(saved));
    }

    /** 메시지에 쓰는 전형 이름. '서류 전형'처럼 이미 '전형'으로 끝나면 그대로 쓴다. */
    private static String stageTitle(String name) {
        return name.endsWith("전형") ? name : name + " 전형";
    }

    /** 리포트 답. 화면이 답 아래에 리포트를 쓴 Agent를 보여 주도록 Report Agent를 붙인다. */
    private static ChatPlan withReport(ChatPlan plan, ChatReport report) {
        List<String> agents = plan.agents().contains(ReportResults.AGENT) ? plan.agents()
                : Stream.concat(plan.agents().stream(), Stream.of(ReportResults.AGENT)).toList();
        return new ChatPlan(plan.intent(), plan.mode(), plan.edit(), plan.targets(), plan.message(), plan.items(),
                plan.sources(), agents, plan.questionTargets(), plan.questionFocus(), plan.questionMemos(),
                plan.questionReplace(), report, plan.questionNcs());
    }

    private Map<UUID, Boolean> selected(UUID companyId, UUID stageId, UUID tabId) {
        return screening.selection(companyId, stageId, tabId).items().stream()
                .collect(Collectors.toMap(CandidateRow::applicationId, CandidateRow::aiSelected,
                        (first, second) -> first, LinkedHashMap::new));
    }

    private static ChatPlan appliedFind(ChatPlan plan, List<UUID> targets, Set<UUID> before, Set<UUID> current) {
        if (plan.targets().isEmpty()) {
            return ChatPlan.answer(ChatPlan.Intent.ANSWER,
                    "조건에 맞는 지원자를 찾지 못했어요. 선택 지원자는 그대로예요.",
                    List.of(), plan.sources(), plan.agents());
        }
        long existing = plan.targets().stream().distinct().filter(before::contains).count();
        if (targets.isEmpty()) {
            if (plan.mode() == SelectionMode.ADD && existing > 0) {
                return appliedPlan(plan, List.of(), existing + "명은 이미 선택 지원자에 있어요. 새로 추가한 지원자는 없어요.");
            }
            return ChatPlan.answer(ChatPlan.Intent.CLARIFY,
                    "현재 선택 상태나 지원자 기준이 달라 검색 결과를 반영하지 못했어요. 선택 지원자는 그대로예요. 다시 요청해 주세요.",
                    List.of(), plan.sources(), plan.agents());
        }
        String message = plan.message();
        if (plan.mode() == SelectionMode.ADD) {
            message = "검색 결과 " + plan.targets().size() + "명 중 **{count}명**을 새로 추가했어요."
                    + (existing > 0 ? " " + existing + "명은 이미 선택 지원자에 있어요." : "")
                    + " 지금 선택 지원자는 " + current.size() + "명이에요.";
        } else if (targets.size() != plan.targets().size()) {
            message = "검색 결과 " + plan.targets().size() + "명 중 현재 선택 가능한 **{count}명**을 반영했어요.";
        }
        return appliedPlan(plan, targets, message);
    }

    private static ChatPlan appliedEdit(ChatPlan plan, List<UUID> targets, Set<UUID> current) {
        String message = plan.message();
        if (plan.edit() == ChatPlan.EditAction.ADD) {
            long existing = plan.targets().stream().distinct().filter(current::contains).count() - targets.size();
            message = targets.isEmpty() ? "요청한 " + existing + "명은 이미 선택 지원자에 있어요."
                    : "선택 지원자에 **{count}명**을 새로 넣었어요."
                            + (existing > 0 ? " " + existing + "명은 이미 선택 지원자에 있어요." : "");
            message += " 지금 선택 지원자는 " + current.size() + "명이에요.";
            String reasons = plan.items().stream().filter(item -> item.applicationId() == null)
                    .map(ChatItem::text).distinct().collect(Collectors.joining(" "));
            if (!reasons.isBlank()) {
                message += " " + reasons;
            }
        } else if (plan.edit() == ChatPlan.EditAction.REMOVE
                && targets.size() != plan.targets().stream().distinct().count()) {
            long absent = plan.targets().stream().distinct().count() - targets.size();
            message = targets.isEmpty() ? "요청한 " + absent + "명은 현재 선택 지원자에 없어요."
                    : "선택 지원자에서 **{count}명**을 뺐어요. " + absent + "명은 현재 선택 지원자에 없어요.";
            message += " 지금 선택 지원자는 " + current.size() + "명이에요.";
        }
        return appliedPlan(plan, targets, message);
    }

    private static ChatPlan appliedPlan(ChatPlan plan, List<UUID> targets, String message) {
        List<ChatItem> items = plan.items().stream()
                .filter(item -> item.applicationId() == null || targets.contains(item.applicationId())).toList();
        return new ChatPlan(plan.intent(), plan.mode(), plan.edit(), targets, message, items,
                plan.sources(), plan.agents(), plan.questionTargets(), plan.questionFocus(), plan.questionMemos(),
                plan.questionReplace(), plan.report(), plan.questionNcs());
    }

    /**
     * 지원자마다 맞춤 질문을 만들어 카드에 넣는다. Root가 정리한 확인할 점(questionFocus)이 있으면 그것을, 없으면 HR 문장을
     * Interview Agent에 넘긴다. Root가 생성 이유 항목을 주면 답에 그대로 두고, 없을 때만 새로 넣은 첫 질문을 보여 준다.
     *
     * @param interviewerRoles 면접관 모드면 지원자별 그 면접관의 담당. 만든 질문을 그 담당으로 넣고 기존 질문은 지우지 않는다
     */
    private ChatPlan withQuestions(UUID companyId, UUID stageId, ChatPlan plan, List<CandidateRow> candidates,
            String message, ChatProgress progress, Map<UUID, InterviewerRole> interviewerRoles) {
        List<ChatItem> summaries = new ArrayList<>();
        List<String> shortfalls = new ArrayList<>();
        List<String> kept = new ArrayList<>();
        List<String> ncsMissed = new ArrayList<>();
        int limit = requestedQuestionCount(message);
        for (UUID applicationId : plan.questionTargets()) {
            String name = candidates.stream().filter(row -> row.applicationId().equals(applicationId))
                    .map(CandidateRow::name).findFirst().orElse("지원자");
            progress.status(name + " 면접 질문을 만들고 있어요");
            InterviewerRole role = interviewerRoles == null ? null : interviewerRoles.get(applicationId);
            if (interviewerRoles != null && role == null) {
                continue;
            }
            if (plan.questionReplace() && interviewerRoles != null) {
                kept.add(plan.questionTargets().size() > 1 ? name + ": " + INTERVIEWER_REPLACE : INTERVIEWER_REPLACE);
            } else if (plan.questionReplace()) {
                KeptQuestions left = interviews.clearAiQuestions(companyId, stageId, applicationId);
                if (left.any()) {
                    String note = KEPT_QUESTIONS.formatted(left.manual(), left.answered());
                    kept.add(plan.questionTargets().size() > 1 ? name + ": " + note : note);
                }
            }
            Set<UUID> before = interviews.questionIds(companyId, stageId, applicationId);
            String focus = plan.questionFocus().getOrDefault(applicationId, message);
            InterviewerMemo memo = plan.questionMemos().get(applicationId);
            InterviewView view;
            if (memo != null) {
                view = interviews.generateFromMemo(companyId, stageId, applicationId, focus, memo, role);
            } else if (plan.questionNcs() == NcsUse.SKIP) {
                view = interviews.generate(companyId, stageId, applicationId, focus, limit, role);
            } else {
                InterviewAiService.NcsGenerated generated = interviews.generateWithNcs(companyId, stageId,
                        applicationId, focus, limit, role, plan.questionNcs());
                view = generated.view();
                if (plan.questionNcs() == NcsUse.REQUESTED && !generated.cited()) {
                    ncsMissed.add(plan.questionTargets().size() > 1 ? name + ": " + NCS_MISSED : NCS_MISSED);
                }
            }
            List<InterviewView.Question> added = view.questions().stream()
                    .filter(question -> !before.contains(question.questionId()))
                    .filter(question -> !question.text().equals(InterviewService.INTRO)).toList();
            if (memo != null && added.isEmpty()) {
                shortfalls.add(name + ": 메모에서 실제 면접 기록과 연결되는 새 확인 사항을 찾지 못해 질문을 추가하지 않았어요.");
            } else if (added.size() < limit) {
                shortfalls.add(name + (memo != null ? ": 메모 참고 질문은 최대 1개만 추가해요."
                        : ": 중복과 근거를 확인해 요청한 " + limit + "개 중 " + added.size() + "개를 추가했어요."));
            }
            summaries.add(new ChatItem(applicationId, name, added.isEmpty() ? "새로 넣을 질문이 없어요"
                    : added.getFirst().text() + (added.size() > 1 ? " 외 " + (added.size() - 1) + "문항" : ""), null));
        }
        List<ChatItem> items = plan.items().isEmpty() ? summaries : plan.items();
        List<String> notes = new ArrayList<>(shortfalls);
        notes.addAll(ncsMissed);
        notes.addAll(kept);
        String reply = plan.message() + (notes.isEmpty() ? "" : "\n" + String.join("\n", notes));
        return new ChatPlan(plan.intent(), plan.mode(), plan.edit(), plan.targets(), reply, items,
                plan.sources(), plan.agents(), plan.questionTargets(), plan.questionFocus(), plan.questionMemos(),
                plan.questionReplace(), plan.report(), plan.questionNcs());
    }

    static int requestedQuestionCount(String message) {
        Matcher requested = QUESTION_COUNT.matcher(message);
        if (!requested.find()) {
            return 2;
        }
        try {
            int count = Integer.parseInt(requested.group(1));
            if (count > 0) {
                return count;
            }
        } catch (NumberFormatException invalid) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_INPUT", "질문 개수는 지원하는 양의 정수로 입력해 주세요.");
        }
        throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_INPUT", "질문 개수는 1개 이상으로 입력해 주세요.");
    }

    private void edit(UUID companyId, UUID stageId, UUID tabId, ChatPlan plan) {
        switch (plan.edit()) {
            case ADD -> screening.addByAi(companyId, stageId, tabId, plan.targets());
            case REMOVE -> screening.remove(companyId, stageId, tabId, plan.targets());
            case CLEAR -> screening.clear(companyId, stageId, tabId);
            default -> throw new IllegalStateException("Unknown edit " + plan.edit());
        }
    }

    /**
     * 탭의 대화 기록. 같은 기업 담당자 누구의 질문이든 함께 보인다. 다른 기업의 전형이나 다른 전형의 탭이면 찾을 수 없다.
     * 멘션은 지금 이 전형의 지원자 이름으로 보여 준다.
     */
    public List<ChatTurn> history(UUID companyId, UUID stageId, UUID tabId) {
        List<CandidateRow> candidates = allCandidates(companyId, stageId, tabId);
        List<ChatHistoryTurn> turns = root.history(threadId(companyId, stageId, tabId));
        Map<UUID, String> names = turns.stream().anyMatch(turn -> !turn.mentions().isEmpty())
                ? candidates.stream()
                        .collect(Collectors.toMap(CandidateRow::applicationId, CandidateRow::name))
                : Map.of();
        return turns.stream()
                .map(turn -> new ChatTurn(turn.message(),
                        turn.mentions().stream().filter(names::containsKey)
                                .map(id -> new ChatMention(id, names.get(id))).toList(),
                        answer(turn.plan(), false, turn.plan().targets().size(), turn.total()),
                        turn.steps(), turn.seconds(), turn.asker()))
                .toList();
    }

    /**
     * 첫 대화 뒤의 자동 제목. 탭이 아직 자동 제목을 기다리고 답이 차단이 아니면 Root에 제목을 받아 탭 이름을 바꾼다.
     * 그 사이 담당자가 이름을 바꿨거나 제목을 받지 못하면 빈 값이고, 다음 질문에서 다시 한다.
     */
    public Optional<StageTabView> title(ChatInput input, ChatAnswer answer) {
        if (answer.intent() == ChatPlan.Intent.BLOCKED
                || !tabs.autoNamed(input.companyId(), input.stageId(), input.tabId())) {
            return Optional.empty();
        }
        Optional<String> title;
        try {
            title = root.title(input.context().message(), answer.message());
        } catch (ApiException unavailable) {
            log.warn("Could not name tab {}", input.tabId(), unavailable);
            return Optional.empty();
        }
        return title.flatMap(name -> tabs.autoName(input.companyId(), input.stageId(), input.tabId(), name));
    }

    /** 대화방은 탭마다 하나다. 기업과 전형까지 넣어 다른 기업의 대화방과 섞이지 않게 한다. */
    static String threadId(UUID companyId, UUID stageId, UUID tabId) {
        return companyId + ":" + stageId + ":" + tabId;
    }

    private ChatAnswer answer(ChatPlan plan, boolean changed, int applied, int total) {
        String message = plan.message().replace("{count}", String.valueOf(applied))
                .replace("{total}", String.valueOf(total));
        return new ChatAnswer(plan.intent(), plan.mode(), message, plan.items(), plan.sources(), plan.agents(),
                changed, settings.isStub(AiAgent.ROOT), plan.report() == null ? null : plan.report().reportId());
    }
}
