package com.hiremate.ai.application;

import com.hiremate.apply.ApplicationService;
import com.hiremate.company.CompanyService;
import com.hiremate.interview.InterviewView;
import com.hiremate.posting.PostingService;
import com.hiremate.recruit.RecruitService;
import com.hiremate.recruit.RecruitmentInfo;
import com.hiremate.recruit.StageInfo;
import com.hiremate.recruit.StageStatus;
import com.hiremate.recruit.StageType;
import com.hiremate.screening.CandidateRow;
import com.hiremate.screening.ScreeningService;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.springframework.stereotype.Service;

/**
 * AI Chat. Root Agent의 계획 가운데 선택 지원자 변경은 screening 모듈이 대상과 권한을 검증해 실행한다.
 * 합격 · 불합격 결정은 이 경로로 할 수 없다 (아키텍처 규칙 1, 2).
 */
@Service
public class ChatService {

    private static final Pattern QUESTION_COUNT = Pattern.compile("(?<!\\d)(\\d{1,2})\\s*(?:개|문항)");

    private final ScreeningService screening;
    private final RecruitService recruits;
    private final ApplicationService applications;
    private final CompanyService companies;
    private final PostingService postings;
    private final RootAgent root;
    private final InterviewAiService interviews;
    private final AiSettings settings;

    public ChatService(ScreeningService screening, RecruitService recruits, ApplicationService applications,
            CompanyService companies, PostingService postings, RootAgent root, InterviewAiService interviews,
            AiSettings settings) {
        this.screening = screening;
        this.recruits = recruits;
        this.applications = applications;
        this.companies = companies;
        this.postings = postings;
        this.root = root;
        this.interviews = interviews;
        this.settings = settings;
    }

    /** 전형을 확인하고 Root에 넘길 자료를 모은다. 다른 기업의 전형이면 찾을 수 없다. 스트림을 열기 전에 부른다. */
    public ChatInput prepare(UUID companyId, UUID stageId, UUID memberId, String message, List<UUID> mentions,
            List<UUID> checked) {
        RecruitmentInfo recruitment = recruits.getByStage(companyId, stageId);
        StageInfo stage = recruitment.stage(stageId).orElseThrow();
        List<CandidateRow> candidates = screening.candidates(companyId, stageId, null, 0, 1000).items();
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
        // 대화는 전형 종료까지만 보관한다. 끝난 전형에서 물으면 대화방 없이 답한다
        String threadId = stage.status() == StageStatus.DONE ? "" : threadId(companyId, stageId, memberId);
        ChatContext context = new ChatContext(stageId, recruitment.id(), threadId, stage.name(),
                stage.status() == StageStatus.ACTIVE, stage.type(), stages,
                candidates, applications.documents(companyId, recruitment.id()), documentScores, interviewViews,
                mentions, checked, companies.profile(companyId),
                postings.draftContext(companyId, recruitment.id()).content(), message);
        return new ChatInput(companyId, stageId, stage.status(), candidates, context);
    }

    /**
     * Root에 묻고 계획을 반영한다. Root의 진행 알림은 progress로 그대로 넘긴다. 화면 연결이 끊겨 Root 답을 받기 전에
     * progress가 예외를 던지면 거기서 멈춘다. Root가 답한 뒤에는 Root가 대화를 이미 남겼으므로 연결이 끊겨도 반영까지 마친다.
     */
    public ChatAnswer run(ChatInput input, ChatProgress progress) {
        UUID companyId = input.companyId();
        UUID stageId = input.stageId();
        List<CandidateRow> candidates = input.candidates();
        ChatPlan plan = root.plan(input.context(), progress);
        ChatProgress after = ChatProgress.quiet(progress);

        boolean changesSelection = plan.intent() == ChatPlan.Intent.FIND || plan.intent() == ChatPlan.Intent.EDIT;
        if (changesSelection && input.status() != StageStatus.ACTIVE) {
            return answer(ChatPlan.answer(ChatPlan.Intent.CLARIFY,
                    "결과를 확정한 전형이라 선택 지원자를 바꿀 수 없어요. 분석이나 요약은 계속 물어볼 수 있어요.",
                    List.of(), List.of(), List.of()), false, 0, candidates.size());
        }
        if (!plan.questionTargets().isEmpty()) {
            plan = withQuestions(companyId, stageId, plan, candidates, input.context().message(), after);
        }
        int applied = 0;
        if (plan.intent() == ChatPlan.Intent.FIND) {
            if (!plan.targets().isEmpty()) {
                applied = screening.applyAiSelection(companyId, stageId, plan.mode(), plan.targets()).size();
            }
        } else if (plan.intent() == ChatPlan.Intent.EDIT) {
            applied = edit(companyId, stageId, plan);
        }
        return answer(plan, changesSelection && (applied > 0 || plan.edit() != null), applied, candidates.size());
    }

    /**
     * 지원자마다 맞춤 질문을 만들어 카드에 넣는다. Root가 정리한 확인할 점(questionFocus)이 있으면 그것을, 없으면 HR 문장을
     * Interview Agent에 넘긴다. Root가 생성 이유 항목을 주면 답에 그대로 두고, 없을 때만 새로 넣은 첫 질문을 보여 준다.
     */
    private ChatPlan withQuestions(UUID companyId, UUID stageId, ChatPlan plan, List<CandidateRow> candidates,
            String message, ChatProgress progress) {
        List<ChatItem> summaries = new ArrayList<>();
        for (UUID applicationId : plan.questionTargets()) {
            String name = candidates.stream().filter(row -> row.applicationId().equals(applicationId))
                    .map(CandidateRow::name).findFirst().orElse("지원자");
            progress.status(name + " 면접 질문을 만들고 있어요");
            int before = interviews.count(companyId, stageId, applicationId);
            String focus = plan.questionFocus().getOrDefault(applicationId, message);
            Matcher requested = QUESTION_COUNT.matcher(message);
            int limit = requested.find() ? Integer.parseInt(requested.group(1)) : Integer.MAX_VALUE;
            InterviewView view = interviews.generate(companyId, stageId, applicationId, focus, limit);
            List<InterviewView.Question> added = view.questions().subList(Math.min(before, view.questions().size()),
                    view.questions().size());
            summaries.add(new ChatItem(applicationId, name, added.isEmpty() ? "새로 넣을 질문이 없어요"
                    : added.getFirst().text() + (added.size() > 1 ? " 외 " + (added.size() - 1) + "문항" : ""), null));
        }
        List<ChatItem> items = plan.items().isEmpty() ? summaries : plan.items();
        return new ChatPlan(plan.intent(), plan.mode(), plan.edit(), plan.targets(), plan.message(), items,
                plan.sources(), plan.agents(), plan.questionTargets(), plan.questionFocus());
    }

    private int edit(UUID companyId, UUID stageId, ChatPlan plan) {
        switch (plan.edit()) {
            case ADD -> screening.add(companyId, stageId, plan.targets());
            case REMOVE -> screening.remove(companyId, stageId, plan.targets());
            case CLEAR -> screening.clear(companyId, stageId);
            case RESTORE -> screening.restore(companyId, stageId);
            default -> throw new IllegalStateException("Unknown edit " + plan.edit());
        }
        return plan.targets().size();
    }

    /** 담당자의 이 전형 대화 기록. 다른 기업의 전형이면 찾을 수 없다. */
    public List<ChatTurn> history(UUID companyId, UUID stageId, UUID memberId) {
        recruits.getByStage(companyId, stageId);
        return root.history(threadId(companyId, stageId, memberId)).stream()
                .map(turn -> new ChatTurn(turn.message(),
                        answer(turn.plan(), false, turn.plan().targets().size(), turn.total())))
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
