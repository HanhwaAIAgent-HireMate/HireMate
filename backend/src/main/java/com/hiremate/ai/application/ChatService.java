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
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Service;

/**
 * AI Chat. Root Agent의 계획 가운데 선택 지원자 변경은 screening 모듈이 대상과 권한을 검증해 실행한다.
 * 합격 · 불합격 결정은 이 경로로 할 수 없다 (아키텍처 규칙 1, 2).
 */
@Service
public class ChatService {

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

    public ChatAnswer chat(UUID companyId, UUID stageId, String message, List<UUID> mentions, List<UUID> checked) {
        RecruitmentInfo recruitment = recruits.getByStage(companyId, stageId);
        StageInfo stage = recruitment.stage(stageId).orElseThrow();
        List<CandidateRow> candidates = screening.candidates(companyId, stageId, null, 0, 1000).items();
        List<StageType> previous = recruitment.stages().stream()
                .filter(other -> other.seq() < stage.seq())
                .map(StageInfo::type)
                .toList();
        Map<UUID, Integer> documentScores = new HashMap<>();
        applications.applicants(companyId, recruitment.id()).stream()
                .filter(applicant -> applicant.documentScore() != null)
                .forEach(applicant -> documentScores.put(applicant.applicationId(), applicant.documentScore()));
        ChatContext context = new ChatContext(stageId, stage.name(), stage.type(), previous, candidates,
                applications.documents(companyId, recruitment.id()), documentScores, mentions, checked,
                companies.profile(companyId), postings.draftContext(companyId, recruitment.id()).content(), message);
        ChatPlan plan = root.plan(context);

        boolean changesSelection = plan.intent() == ChatPlan.Intent.FIND || plan.intent() == ChatPlan.Intent.EDIT;
        if (changesSelection && stage.status() != StageStatus.ACTIVE) {
            return answer(ChatPlan.answer(ChatPlan.Intent.CLARIFY,
                    "결과를 확정한 전형이라 선택 지원자를 바꿀 수 없어요. 분석이나 요약은 계속 물어볼 수 있어요.",
                    List.of(), List.of(), List.of()), false, 0, candidates.size());
        }
        if (!plan.questionTargets().isEmpty()) {
            plan = withQuestions(companyId, stageId, plan, candidates, message);
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

    /** 지원자마다 맞춤 질문을 만들어 카드에 넣고, 답변에는 새로 넣은 첫 질문을 보여 준다. */
    private ChatPlan withQuestions(UUID companyId, UUID stageId, ChatPlan plan, List<CandidateRow> candidates,
            String focus) {
        List<ChatItem> items = new ArrayList<>();
        for (UUID applicationId : plan.questionTargets()) {
            int before = interviews.count(companyId, stageId, applicationId);
            InterviewView view = interviews.generate(companyId, stageId, applicationId, focus);
            String name = candidates.stream().filter(row -> row.applicationId().equals(applicationId))
                    .map(CandidateRow::name).findFirst().orElse("지원자");
            List<InterviewView.Question> added = view.questions().subList(Math.min(before, view.questions().size()),
                    view.questions().size());
            items.add(new ChatItem(applicationId, name, added.isEmpty() ? "새로 넣을 질문이 없어요"
                    : added.getFirst().text() + (added.size() > 1 ? " 외 " + (added.size() - 1) + "문항" : ""), null));
        }
        return new ChatPlan(plan.intent(), plan.mode(), plan.edit(), plan.targets(), plan.message(), items,
                plan.sources(), plan.agents(), plan.questionTargets());
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

    private ChatAnswer answer(ChatPlan plan, boolean changed, int applied, int total) {
        String message = plan.message().replace("{count}", String.valueOf(applied))
                .replace("{total}", String.valueOf(total));
        return new ChatAnswer(plan.intent(), plan.mode(), message, plan.items(), plan.sources(), plan.agents(),
                changed, settings.isStub(AiAgent.ROOT));
    }
}
