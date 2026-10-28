package com.hiremate.ai.application;

import com.hiremate.apply.ApplicationService;
import com.hiremate.assessment.AssessmentService;
import com.hiremate.company.CompanyService;
import com.hiremate.global.ApiException;
import com.hiremate.interview.InterviewView;
import com.hiremate.posting.PostingService;
import com.hiremate.recruit.RecruitService;
import com.hiremate.recruit.RecruitmentInfo;
import com.hiremate.recruit.StageInfo;
import com.hiremate.recruit.StageStatus;
import com.hiremate.recruit.StageType;
import com.hiremate.screening.CandidatePage;
import com.hiremate.screening.CandidateRow;
import com.hiremate.screening.CandidateSort;
import com.hiremate.screening.ScreeningService;
import com.hiremate.screening.SelectionMode;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
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

    private static final Logger log = LoggerFactory.getLogger(ChatService.class);
    private static final Pattern QUESTION_COUNT = Pattern.compile("(?<!\\d)(\\d+)\\s*(?:개|문항)");
    private static final int CANDIDATE_PAGE_SIZE = 200;

    private final ScreeningService screening;
    private final RecruitService recruits;
    private final ApplicationService applications;
    private final CompanyService companies;
    private final PostingService postings;
    private final RootAgent root;
    private final InterviewAiService interviews;
    private final AiSettings settings;
    private final AssessmentService assessments;

    public ChatService(ScreeningService screening, RecruitService recruits, ApplicationService applications,
            CompanyService companies, PostingService postings, RootAgent root, InterviewAiService interviews,
            AiSettings settings, AssessmentService assessments) {
        this.screening = screening;
        this.recruits = recruits;
        this.applications = applications;
        this.companies = companies;
        this.postings = postings;
        this.root = root;
        this.interviews = interviews;
        this.settings = settings;
        this.assessments = assessments;
    }

    /** 전형을 확인하고 Root에 넘길 자료를 모은다. 다른 기업의 전형이면 찾을 수 없다. 스트림을 열기 전에 부른다. */
    public ChatInput prepare(UUID companyId, UUID stageId, UUID memberId, String message, List<UUID> mentions,
            List<UUID> checked) {
        RecruitmentInfo recruitment = recruits.getByStage(companyId, stageId);
        StageInfo stage = recruitment.stage(stageId).orElseThrow();
        List<CandidateRow> candidates = allCandidates(companyId, stageId);
        List<ChatContext.Stage> stages = recruitment.stages().stream()
                .map(other -> new ChatContext.Stage(other.id(), other.name(), other.type(), other.status()))
                .toList();
        Map<UUID, BigDecimal> documentScores = new HashMap<>();
        applications.applicants(companyId, recruitment.id()).stream()
                .filter(applicant -> applicant.documentScore() != null)
                .forEach(applicant -> documentScores.put(applicant.applicationId(), applicant.documentScore()));
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
        // 대화는 전형 종료까지만 보관한다. 끝난 전형에서 물으면 대화방 없이 답한다
        String threadId = stage.status() == StageStatus.DONE ? "" : threadId(companyId, stageId, memberId);
        ChatContext context = new ChatContext(stageId, recruitment.id(), threadId, stage.name(),
                stage.status() == StageStatus.ACTIVE, stage.type(), stages,
                candidates, applications.documents(companyId, recruitment.id()), documentScores, interviewViews,
                mentions, checked, companies.profile(companyId),
                postings.draftContext(companyId, recruitment.id()).content(), message, interviewerMemos,
                assessmentScores);
        return new ChatInput(companyId, stageId, stage.status(), candidates, context);
    }

    private List<CandidateRow> allCandidates(UUID companyId, UUID stageId) {
        List<CandidateRow> all = new ArrayList<>();
        CandidatePage page;
        int pageNumber = 0;
        do {
            page = screening.candidates(companyId, stageId, null, CandidateSort.QUALIFICATION,
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
        List<CandidateRow> candidates = input.candidates();
        ChatPlan previous = root.plan(input.context(), progress);
        ChatPlan plan = previous;
        ChatProgress after = ChatProgress.quiet(progress);

        boolean changesSelection = plan.intent() == ChatPlan.Intent.FIND || plan.intent() == ChatPlan.Intent.EDIT;
        if (changesSelection && input.status() != StageStatus.ACTIVE) {
            return completed(input.context(), previous, ChatPlan.answer(ChatPlan.Intent.CLARIFY,
                    "결과를 확정한 전형이라 선택 지원자를 바꿀 수 없어요. 분석이나 요약은 계속 물어볼 수 있어요.",
                    List.of(), List.of(), List.of()), false, 0, candidates.size());
        }
        if (!plan.questionTargets().isEmpty()) {
            plan = withQuestions(companyId, stageId, plan, candidates, input.context().message(), after);
        }
        int applied = 0;
        boolean changed = false;
        if (plan.intent() == ChatPlan.Intent.FIND) {
            Map<UUID, Boolean> before = selected(companyId, stageId);
            List<UUID> targets = List.of();
            if (!plan.targets().isEmpty()) {
                targets = screening.applyAiSelection(companyId, stageId, plan.mode(), plan.targets());
            }
            Map<UUID, Boolean> current = selected(companyId, stageId);
            changed = !before.equals(current);
            applied = targets.size();
            plan = appliedFind(plan, targets, before.keySet(), current.keySet());
        } else if (plan.intent() == ChatPlan.Intent.EDIT) {
            Map<UUID, Boolean> before = selected(companyId, stageId);
            edit(companyId, stageId, plan);
            Map<UUID, Boolean> current = selected(companyId, stageId);
            changed = !before.equals(current);
            List<UUID> targets = switch (plan.edit()) {
                case ADD -> plan.targets().stream().distinct()
                        .filter(id -> current.containsKey(id) && !before.containsKey(id)).toList();
                case REMOVE -> plan.targets().stream().distinct()
                        .filter(id -> before.containsKey(id) && !current.containsKey(id)).toList();
                case RESTORE -> current.keySet().stream().filter(id -> !before.containsKey(id)).toList();
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
        ChatPlan finalPlan = new ChatPlan(plan.intent(), plan.mode(), plan.edit(), plan.targets(), message,
                plan.items(), plan.sources(), plan.agents(), plan.questionTargets(), plan.questionFocus(),
                plan.questionMemos());
        if (!context.threadId().isBlank()) {
            try {
                root.applied(new ChatApplied(context.threadId(), context.message(), previous, finalPlan));
            } catch (ApiException unavailable) {
                log.warn("Could not confirm applied chat plan for stage {}", context.stageId(), unavailable);
            }
        }
        return answer(finalPlan, changed, applied, total);
    }

    private Map<UUID, Boolean> selected(UUID companyId, UUID stageId) {
        return screening.selection(companyId, stageId).items().stream()
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
                plan.sources(), plan.agents(), plan.questionTargets(), plan.questionFocus(), plan.questionMemos());
    }

    /**
     * 지원자마다 맞춤 질문을 만들어 카드에 넣는다. Root가 정리한 확인할 점(questionFocus)이 있으면 그것을, 없으면 HR 문장을
     * Interview Agent에 넘긴다. Root가 생성 이유 항목을 주면 답에 그대로 두고, 없을 때만 새로 넣은 첫 질문을 보여 준다.
     */
    private ChatPlan withQuestions(UUID companyId, UUID stageId, ChatPlan plan, List<CandidateRow> candidates,
            String message, ChatProgress progress) {
        List<ChatItem> summaries = new ArrayList<>();
        List<String> shortfalls = new ArrayList<>();
        int limit = requestedQuestionCount(message);
        for (UUID applicationId : plan.questionTargets()) {
            String name = candidates.stream().filter(row -> row.applicationId().equals(applicationId))
                    .map(CandidateRow::name).findFirst().orElse("지원자");
            progress.status(name + " 면접 질문을 만들고 있어요");
            int before = interviews.count(companyId, stageId, applicationId);
            String focus = plan.questionFocus().getOrDefault(applicationId, message);
            InterviewerMemo memo = plan.questionMemos().get(applicationId);
            InterviewView view = memo == null
                    ? interviews.generate(companyId, stageId, applicationId, focus, limit)
                    : interviews.generateFromMemo(companyId, stageId, applicationId, focus, memo);
            List<InterviewView.Question> added = view.questions().subList(Math.min(before, view.questions().size()),
                    view.questions().size());
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
        String reply = plan.message() + (shortfalls.isEmpty() ? "" : "\n" + String.join("\n", shortfalls));
        return new ChatPlan(plan.intent(), plan.mode(), plan.edit(), plan.targets(), reply, items,
                plan.sources(), plan.agents(), plan.questionTargets(), plan.questionFocus(), plan.questionMemos());
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

    private void edit(UUID companyId, UUID stageId, ChatPlan plan) {
        switch (plan.edit()) {
            case ADD -> screening.addByAi(companyId, stageId, plan.targets());
            case REMOVE -> screening.remove(companyId, stageId, plan.targets());
            case CLEAR -> screening.clear(companyId, stageId);
            case RESTORE -> screening.restore(companyId, stageId);
            default -> throw new IllegalStateException("Unknown edit " + plan.edit());
        }
    }

    /** 담당자의 이 전형 대화 기록. 다른 기업의 전형이면 찾을 수 없다. 멘션은 지금 이 전형의 지원자 이름으로 보여 준다. */
    public List<ChatTurn> history(UUID companyId, UUID stageId, UUID memberId) {
        recruits.getByStage(companyId, stageId);
        List<ChatHistoryTurn> turns = root.history(threadId(companyId, stageId, memberId));
        Map<UUID, String> names = turns.stream().anyMatch(turn -> !turn.mentions().isEmpty())
                ? allCandidates(companyId, stageId).stream()
                        .collect(Collectors.toMap(CandidateRow::applicationId, CandidateRow::name))
                : Map.of();
        return turns.stream()
                .map(turn -> new ChatTurn(turn.message(),
                        turn.mentions().stream().filter(names::containsKey)
                                .map(id -> new ChatMention(id, names.get(id))).toList(),
                        answer(turn.plan(), false, turn.plan().targets().size(), turn.total()),
                        turn.steps(), turn.seconds()))
                .toList();
    }

    /** [대화 지우기]: 담당자의 이 전형 대화방을 지운다. */
    public void forget(UUID companyId, UUID stageId, UUID memberId) {
        recruits.getByStage(companyId, stageId);
        root.forget(threadId(companyId, stageId, memberId));
    }

    /** 대화방은 담당자별 · 전형별이다. 기업까지 넣어 다른 기업의 대화방과 섞이지 않게 한다. */
    private static String threadId(UUID companyId, UUID stageId, UUID memberId) {
        return companyId + ":" + stageId + ":" + memberId;
    }

    private ChatAnswer answer(ChatPlan plan, boolean changed, int applied, int total) {
        String message = plan.message().replace("{count}", String.valueOf(applied))
                .replace("{total}", String.valueOf(total));
        return new ChatAnswer(plan.intent(), plan.mode(), message, plan.items(), plan.sources(), plan.agents(),
                changed, settings.isStub(AiAgent.ROOT));
    }
}
