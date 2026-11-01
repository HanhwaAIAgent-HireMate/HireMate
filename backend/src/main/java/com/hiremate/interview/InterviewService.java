package com.hiremate.interview;

import com.hiremate.apply.ApplicationService;
import com.hiremate.global.ApiException;
import com.hiremate.interview.domain.InterviewPreparation;
import com.hiremate.interview.domain.InterviewPreparationRepository;
import com.hiremate.interview.domain.InterviewQuestion;
import com.hiremate.interview.domain.InterviewQuestionRepository;
import com.hiremate.interview.domain.InterviewSchedule;
import com.hiremate.interview.domain.InterviewScheduleRepository;
import com.hiremate.interview.domain.InterviewSessionRepository;
import com.hiremate.recruit.RecruitService;
import com.hiremate.recruit.RecruitmentInfo;
import com.hiremate.recruit.StageInfo;
import com.hiremate.recruit.StageStatus;
import com.hiremate.recruit.StageType;
import com.hiremate.screening.ScreeningService;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.function.Function;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 면접 (FR-27, FR-28). 지원자별 맞춤 질문을 채택하거나 직접 추가하고, 면접관이 질문마다 답변을 기록한다.
 * 이전 면접의 질문과 답변은 다음 면접 화면에서 그대로 보여 준다. 답변이 바뀌면 {@link InterviewAnswersChanged}를 낸다.
 */
@Service
public class InterviewService {

    public static final String INTRO = "1분 자기소개 부탁드립니다.";

    /** 🎤 꼬리질문은 2단계까지 (질문 → 꼬리질문 → 꼬리질문의 꼬리질문). 그 뒤 남은 확인할 점은 다음 면접의 미확인 질문으로 넘긴다. */
    public static final int MAX_FOLLOW_UP_DEPTH = 2;

    private final InterviewQuestionRepository questions;
    private final InterviewScheduleRepository schedules;
    private final InterviewPreparationRepository preparations;
    private final InterviewSessionRepository sessions;
    private final RecruitService recruits;
    private final ScreeningService screening;
    private final ApplicationEventPublisher events;
    private final ApplicationService applications;

    public InterviewService(InterviewQuestionRepository questions, InterviewScheduleRepository schedules,
            RecruitService recruits, ScreeningService screening, ApplicationEventPublisher events,
            ApplicationService applications, InterviewPreparationRepository preparations,
            InterviewSessionRepository sessions) {
        this.questions = questions;
        this.schedules = schedules;
        this.recruits = recruits;
        this.screening = screening;
        this.events = events;
        this.applications = applications;
        this.preparations = preparations;
        this.sessions = sessions;
    }

    @Transactional(readOnly = true)
    public InterviewView view(UUID companyId, UUID stageId, UUID applicationId) {
        StageInfo stage = interviewStage(companyId, stageId, applicationId);
        return view(companyId, stage, applicationId);
    }

    private InterviewView view(UUID companyId, StageInfo stage, UUID applicationId) {
        UUID stageId = stage.id();
        String name = applications.applicants(companyId, List.of(applicationId)).getFirst().name();
        RecruitmentInfo recruitment = recruits.getByStage(companyId, stageId);
        Map<UUID, InterviewSchedule> scheduleByStage = schedules.findByApplicationIdAndCompanyId(applicationId,
                companyId).stream().collect(Collectors.toMap(InterviewSchedule::getStageId, Function.identity()));
        Map<UUID, List<InterviewQuestion>> byStage = questions
                .findByApplicationIdAndCompanyIdOrderBySeq(applicationId, companyId).stream()
                .collect(Collectors.groupingBy(InterviewQuestion::getStageId));
        List<InterviewView.PreviousInterview> previous = recruitment.stages().stream()
                .filter(other -> other.type() == StageType.INTERVIEW && other.seq() < stage.seq())
                .filter(other -> byStage.containsKey(other.id()))
                .map(other -> new InterviewView.PreviousInterview(other.id(), other.name(),
                        toSchedule(scheduleByStage.get(other.id())), toQuestions(byStage.get(other.id()), name)))
                .toList();
        return new InterviewView(applicationId, toSchedule(scheduleByStage.get(stageId)),
                toQuestions(byStage.getOrDefault(stageId, List.of()), name), previous,
                recruitment.stages().stream().filter(other -> other.type() == StageType.INTERVIEW).count() == 1);
    }

    /** 시작 전인 다음 면접의 자료. 바로 앞 전형에서 합격이 확정된 지원자만 준비할 수 있다. */
    @Transactional(readOnly = true)
    public InterviewView preparationView(UUID companyId, UUID stageId, UUID applicationId) {
        return view(companyId, preparationStage(companyId, stageId, applicationId), applicationId);
    }

    /** 대기열 등록 전 자료를 준비하는 시간도 지원자별 생성 상태에 포함한다. */
    @Transactional
    public void startPreparing(UUID companyId, UUID stageId, UUID applicationId) {
        preparationStage(companyId, stageId, applicationId);
        preparations.save(new InterviewPreparation(stageId, applicationId, companyId));
    }

    @Transactional(readOnly = true)
    public boolean preparing(UUID companyId, UUID stageId, UUID applicationId) {
        return preparations.existsByStageIdAndApplicationIdAndCompanyId(stageId, applicationId, companyId);
    }

    @Transactional
    public void finishPreparing(UUID companyId, UUID stageId, UUID applicationId) {
        preparations.deleteByStageIdAndApplicationIdAndCompanyId(stageId, applicationId, companyId);
    }

    /** 맞춤 질문을 카드에 넣는다. 이미 있는 질문은 다시 넣지 않는다. */
    @Transactional
    public InterviewView addQuestions(UUID companyId, UUID stageId, UUID applicationId, List<String> texts,
            QuestionSource source) {
        StageInfo stage = interviewStage(companyId, stageId, applicationId);
        saveQuestions(companyId, stageId, applicationId, texts, source);
        return view(companyId, stage, applicationId);
    }

    @Transactional
    public InterviewView addManualQuestion(UUID companyId, UUID stageId, UUID applicationId,
            String text, InterviewerRole role) {
        StageInfo stage = interviewStage(companyId, stageId, applicationId);
        saveDrafts(companyId, stageId, applicationId,
                List.of(new InterviewQuestionDraft(text, null, role)), QuestionSource.MANUAL);
        return view(companyId, stage, applicationId);
    }

    /** 확정 합격자의 다음 면접 질문을 저장한다. 면접 대상자 등록이나 전형 상태는 바꾸지 않는다. */
    @Transactional
    public void addPreparedQuestions(UUID companyId, UUID stageId, UUID applicationId, List<String> texts) {
        preparationStage(companyId, stageId, applicationId);
        saveQuestions(companyId, stageId, applicationId, texts, QuestionSource.AI);
    }

    private void saveQuestions(UUID companyId, UUID stageId, UUID applicationId, List<String> texts,
            QuestionSource source) {
        saveDrafts(companyId, stageId, applicationId,
                texts.stream().map(text -> new InterviewQuestionDraft(text, null)).toList(), source);
    }

    /** 현재 면접에 생성 당시의 근거와 함께 질문을 추가한다. */
    @Transactional
    public InterviewView addGeneratedQuestions(UUID companyId, UUID stageId, UUID applicationId,
            List<InterviewQuestionDraft> drafts) {
        StageInfo stage = interviewStage(companyId, stageId, applicationId);
        saveDrafts(companyId, stageId, applicationId, drafts, QuestionSource.AI);
        return view(companyId, stage, applicationId);
    }

    /** 시작 전 면접도 기존의 합격자·기업 범위를 검증한 뒤 근거를 함께 저장한다. */
    @Transactional
    public void addPreparedDrafts(UUID companyId, UUID stageId, UUID applicationId,
            List<InterviewQuestionDraft> drafts) {
        preparationStage(companyId, stageId, applicationId);
        saveDrafts(companyId, stageId, applicationId, drafts, QuestionSource.AI);
    }

    private void saveDrafts(UUID companyId, UUID stageId, UUID applicationId, List<InterviewQuestionDraft> drafts,
            QuestionSource source) {
        sessions.lock(companyId, stageId, applicationId).ifPresent(session -> {
            if (session.getStatus() == InterviewSessionStatus.ENDED) {
                throw new ApiException(HttpStatus.CONFLICT, "INTERVIEW_ENDED", "The interview has ended.");
            }
            if (session.getStatus() == InterviewSessionStatus.IN_PROGRESS && drafts.stream()
                    .anyMatch(draft -> draft.interviewerRole() == null && !INTRO.equals(draft.text().strip()))) {
                throw new ApiException(HttpStatus.CONFLICT, "QUESTION_OWNER_REQUIRED",
                        "New questions must have an owner during the interview.");
            }
        });
        List<InterviewQuestion> existing = questions.findByStageIdAndApplicationIdAndCompanyIdOrderBySeq(stageId,
                applicationId, companyId);
        Set<String> seen = existing.stream().map(InterviewQuestion::getText).collect(Collectors.toSet());
        if (source == QuestionSource.AI && seen.add(INTRO)) {
            questions.save(new InterviewQuestion(stageId, applicationId, companyId, 0, INTRO, source,
                    "공통 질문: 모든 면접에서 지원자의 주요 경험과 지원 동기를 먼저 듣기 위한 자기소개입니다.", InterviewerRole.HR));
        }
        int seq = existing.stream().mapToInt(InterviewQuestion::getSeq).max().orElse(0);
        for (InterviewQuestionDraft draft : drafts) {
            String trimmed = draft.text().strip();
            if (!trimmed.isEmpty() && seen.add(trimmed)) {
                questions.save(new InterviewQuestion(stageId, applicationId, companyId, ++seq, trimmed, source,
                        draft.reason(), draft.interviewerRole()));
            }
        }
    }

    /**
     * 🎤 질문 담당(인사 · 실무)을 바꾼다.
     *
     * <p>담당은 면접 전에 정하는 일이라 시작 전(PENDING) 전형에 미리 만든 질문도 바꿀 수 있다.
     * 시작 전 전형의 지원자는 아직 그 전형에 등록되지 않았으므로 preparationStage로 "이전 전형 합격자"인지 확인한다.
     * 결과를 확정(CONFIRMED)했거나 끝난(DONE) 면접은 기록이 바뀌지 않게 막는다.
     */
    @Transactional
    public InterviewView assignRole(UUID companyId, UUID stageId, UUID questionId, InterviewerRole role) {
        InterviewQuestion question = question(companyId, stageId, questionId);
        requirePlanning(companyId, stageId, question.getApplicationId());
        if (!question.getAnswer().isBlank() && question.getInterviewerRole() != null) {
            throw new ApiException(HttpStatus.CONFLICT, "QUESTION_ANSWERED", "An answered question keeps its owner.");
        }
        if (INTRO.equals(question.getText()) && role != InterviewerRole.HR) {
            throw new ApiException(HttpStatus.CONFLICT, "INTRO_OWNER", "HR records the common introduction.");
        }
        if (question.getParentQuestionId() != null) {
            InterviewQuestion parent = question(companyId, stageId, question.getParentQuestionId());
            if (parent.getInterviewerRole() != role) {
                throw new ApiException(HttpStatus.CONFLICT, "FOLLOW_UP_OWNER", "A follow-up keeps its parent's owner.");
            }
        }
        StageInfo stage = preparationStage(companyId, stageId, question.getApplicationId());
        if (stage.status() != StageStatus.PENDING && stage.status() != StageStatus.ACTIVE) {
            throw new ApiException(HttpStatus.CONFLICT, "STAGE_CLOSED",
                    "Roles can only be assigned before or during the interview.");
        }
        question.assignRole(role);
        return view(companyId, stage, question.getApplicationId());
    }

    @Transactional
    public InterviewView answer(UUID companyId, UUID stageId, UUID questionId, String answer) {
        return answer(companyId, stageId, questionId, answer, true);
    }

    /**
     * 질문별 답변 기록.
     *
     * <p>💾 analyze가 false면 자동 저장이다. 면접관이 타이핑을 멈출 때마다 DB에만 저장하고 답변 분석(모델 호출)은 하지 않는다.
     * analyze가 true면 면접관이 그 답변 칸을 떠난(다른 질문으로 넘어간) 때다. 답이 바뀌었거나 자동 저장만 되고 아직
     * 분석에 넘기지 않은 답이 있을 때만 분석을 요청한다. 같은 답으로 칸을 여러 번 드나들어도 다시 분석하지 않는다.
     */
    @Transactional
    public InterviewView answer(UUID companyId, UUID stageId, UUID questionId, String answer, boolean analyze) {
        return answer(companyId, stageId, questionId, answer, analyze, null);
    }

    @Transactional
    public InterviewView answer(UUID companyId, UUID stageId, UUID questionId, String answer, boolean analyze,
            Long expectedVersion) {
        InterviewQuestion question = questions.lock(companyId, stageId, questionId).orElseThrow(
                () -> new ApiException(HttpStatus.NOT_FOUND, "QUESTION_NOT_FOUND", "Question not found."));
        StageInfo stage = interviewStage(companyId, stageId, question.getApplicationId());
        if (stage.status() != StageStatus.ACTIVE) {
            throw new ApiException(HttpStatus.CONFLICT, "STAGE_NOT_ACTIVE", "The interview stage is not active.");
        }
        if (expectedVersion != null && question.getVersion() != expectedVersion) {
            throw new ApiException(HttpStatus.CONFLICT, "ANSWER_CONFLICT",
                    "This answer changed. Reload the latest answer before saving.");
        }
        boolean changed = !question.getAnswer().equals(answer);
        if (!analyze) {
            if (changed) {
                question.saveDraft(answer);
            }
        } else if (changed || question.isAnswerPendingAnalysis()) {
            question.answer(answer);
            question.markAnalyzed();
            events.publishEvent(new InterviewAnswersChanged(companyId, stageId, question.getApplicationId()));
        }
        questions.flush();
        return view(companyId, stageId, question.getApplicationId());
    }

    /**
     * 🎤 꼬리질문 제안 재료: 처음 질문부터 꼬리질문을 받을 질문까지의 사슬 (마지막이 지금 질문).
     *
     * <p>꼬리질문은 진행 중(ACTIVE)인 면접에서, 답변을 적은 질문에만, 질문마다 하나씩, 최대 2단계까지 받는다.
     * 조건에 맞지 않으면 모델을 부르기 전에 409로 막아 토큰을 쓰지 않는다.
     */
    @Transactional(readOnly = true)
    public List<InterviewView.Question> followUpChain(UUID companyId, UUID stageId, UUID questionId) {
        InterviewQuestion question = question(companyId, stageId, questionId);
        List<InterviewQuestion> card = followUpCard(companyId, stageId, question);
        checkFollowUp(question, card);
        List<InterviewQuestion> chain = new ArrayList<>();
        for (InterviewQuestion at = question; at != null; at = parentOf(at, card)) {
            chain.addFirst(at);
        }
        return toQuestions(chain,
                applications.applicants(companyId, List.of(question.getApplicationId())).getFirst().name());
    }

    /**
     * 🎤 면접관이 고른(또는 직접 쓴) 꼬리질문을 원래 질문 아래에 넣는다. 담당(인사 · 실무)은 원래 질문을 잇는다.
     *
     * @param check AI 제안을 골랐으면 그 제안의 확인 포인트. 질문 근거로 저장해 카드에 보인다. 직접 썼으면 null
     */
    @Transactional
    public InterviewView addFollowUp(UUID companyId, UUID stageId, UUID questionId, String text,
            QuestionSource source, String check) {
        InterviewQuestion parent = question(companyId, stageId, questionId);
        List<InterviewQuestion> card = followUpCard(companyId, stageId, parent);
        checkFollowUp(parent, card);
        String trimmed = text.strip();
        if (trimmed.isEmpty()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "EMPTY_FOLLOW_UP", "Follow-up question is empty.");
        }
        int seq = card.stream().mapToInt(InterviewQuestion::getSeq).max().orElse(0) + 1;
        // 카드의 '근거'가 읽는 형식(항목: 값)으로 남긴다. 유형 배지는 '꼬리질문', 확인 포인트는 '면접 확인 부분'에 보인다
        StringBuilder reason = new StringBuilder("질문 유형: 꼬리질문\n앞 질문: ").append(parent.getText().strip());
        if (check != null && !check.isBlank()) {
            reason.append("\n확인할 내용: ").append(check.strip());
        }
        reason.append(source == QuestionSource.AI
                ? "\n생성 방식: 앞 질문의 답변을 보고 AI가 제안한 질문을 면접관이 골랐습니다."
                : "\n생성 방식: 앞 질문의 답변을 듣고 면접관이 직접 쓴 질문입니다.");
        questions.save(new InterviewQuestion(stageId, parent.getApplicationId(), companyId, seq, trimmed, source,
                reason.toString(), parent.getInterviewerRole(), parent.getId()));
        return view(companyId, stageId, parent.getApplicationId());
    }

    /** 꼬리질문을 받을 질문이 있는 카드(같은 전형 · 지원자의 질문 전체). 진행 중인 면접만 꼬리질문을 받는다. */
    private List<InterviewQuestion> followUpCard(UUID companyId, UUID stageId, InterviewQuestion question) {
        StageInfo stage = interviewStage(companyId, stageId, question.getApplicationId());
        if (stage.status() != StageStatus.ACTIVE) {
            throw new ApiException(HttpStatus.CONFLICT, "STAGE_NOT_ACTIVE",
                    "Follow-up questions are only available during the interview.");
        }
        return questions.findByStageIdAndApplicationIdAndCompanyIdOrderBySeq(stageId, question.getApplicationId(),
                companyId);
    }

    private static void checkFollowUp(InterviewQuestion question, List<InterviewQuestion> card) {
        if (question.getAnswer().isBlank()) {
            throw new ApiException(HttpStatus.CONFLICT, "ANSWER_REQUIRED", "Write the answer first.");
        }
        if (depth(question, card) >= MAX_FOLLOW_UP_DEPTH) {
            throw new ApiException(HttpStatus.CONFLICT, "FOLLOW_UP_TOO_DEEP",
                    "Follow-up questions go up to two levels.");
        }
        if (card.stream().anyMatch(other -> question.getId().equals(other.getParentQuestionId()))) {
            throw new ApiException(HttpStatus.CONFLICT, "FOLLOW_UP_EXISTS",
                    "This question already has a follow-up question.");
        }
    }

    /** 처음 질문은 0, 꼬리질문은 1, 꼬리질문의 꼬리질문은 2. */
    private static int depth(InterviewQuestion question, List<InterviewQuestion> card) {
        int depth = 0;
        for (InterviewQuestion at = parentOf(question, card); at != null; at = parentOf(at, card)) {
            depth++;
        }
        return depth;
    }

    private static boolean descends(InterviewQuestion question, InterviewQuestion ancestor,
            List<InterviewQuestion> card) {
        for (InterviewQuestion at = parentOf(question, card); at != null; at = parentOf(at, card)) {
            if (at == ancestor) {
                return true;
            }
        }
        return false;
    }

    private static InterviewQuestion parentOf(InterviewQuestion question, List<InterviewQuestion> card) {
        UUID parentId = question.getParentQuestionId();
        return parentId == null ? null
                : card.stream().filter(other -> other.getId().equals(parentId)).findFirst().orElse(null);
    }

    @Transactional
    public InterviewView deleteQuestion(UUID companyId, UUID stageId, UUID questionId) {
        InterviewQuestion question = question(companyId, stageId, questionId);
        List<InterviewQuestion> card = questions.findByStageIdAndApplicationIdAndCompanyIdOrderBySeq(stageId,
                question.getApplicationId(), companyId);
        // 🎤 딸린 꼬리질문은 DB가 함께 지운다(ON DELETE CASCADE). 꼬리질문에 적은 답이 있어도 분석을 다시 한다
        boolean answered = card.stream().anyMatch(other -> !other.getAnswer().isBlank()
                && (other == question || descends(other, question, card)));
        questions.delete(question);
        if (answered) {
            events.publishEvent(new InterviewAnswersChanged(companyId, stageId, question.getApplicationId()));
        }
        return view(companyId, stageId, question.getApplicationId());
    }

    /** Chat의 질문 교체. 답변이 없는 AI 질문만 지우고, 직접 넣은 질문과 답변을 기록한 질문은 남긴다. */
    @Transactional
    public KeptQuestions clearAiQuestions(UUID companyId, UUID stageId, UUID applicationId) {
        requirePlanning(companyId, stageId, applicationId);
        StageInfo stage = interviewStage(companyId, stageId, applicationId);
        if (stage.status() != StageStatus.ACTIVE) {
            throw new ApiException(HttpStatus.CONFLICT, "STAGE_NOT_ACTIVE", "Only active interviews can regenerate.");
        }
        List<InterviewQuestion> existing = questions.findByStageIdAndApplicationIdAndCompanyIdOrderBySeq(stageId,
                applicationId, companyId);
        // 🎤 꼬리질문은 면접관이 고른 질문이라 남긴다. 꼬리질문이 딸린 질문도 지우면 꼬리질문까지 함께 지워져 남긴다
        Set<UUID> parents = existing.stream().map(InterviewQuestion::getParentQuestionId).filter(Objects::nonNull)
                .collect(Collectors.toSet());
        questions.deleteAll(existing.stream()
                .filter(question -> question.getSource() == QuestionSource.AI && question.getAnswer().isBlank())
                .filter(question -> question.getParentQuestionId() == null && !parents.contains(question.getId()))
                .toList());
        int manual = (int) existing.stream().filter(question -> question.getSource() == QuestionSource.MANUAL).count();
        int answered = (int) existing.stream()
                .filter(question -> question.getSource() == QuestionSource.AI && !question.getAnswer().isBlank())
                .count();
        return new KeptQuestions(manual, answered);
    }

    /** 담당자가 요청한 현재 면접 질문만 백업 없이 제거한다. 이전 면접 기록은 유지한다. */
    @Transactional
    public void clearQuestions(UUID companyId, UUID stageId, UUID applicationId) {
        requirePlanning(companyId, stageId, applicationId);
        StageInfo stage = interviewStage(companyId, stageId, applicationId);
        if (stage.status() != StageStatus.ACTIVE) {
            throw new ApiException(HttpStatus.CONFLICT, "STAGE_NOT_ACTIVE", "Only active interviews can regenerate.");
        }
        List<InterviewQuestion> existing = questions.findByStageIdAndApplicationIdAndCompanyIdOrderBySeq(stageId,
                applicationId, companyId);
        questions.deleteAll(existing);
        if (existing.stream().anyMatch(question -> !question.getAnswer().isBlank())) {
            events.publishEvent(new InterviewAnswersChanged(companyId, stageId, applicationId));
        }
    }

    @Transactional
    public InterviewView schedule(UUID companyId, UUID stageId, UUID applicationId, Instant scheduledAt,
            String interviewers) {
        interviewStage(companyId, stageId, applicationId);
        InterviewSchedule schedule = schedules.findById(new InterviewSchedule.Key(stageId, applicationId))
                .orElseGet(() -> schedules.save(new InterviewSchedule(stageId, applicationId, companyId)));
        schedule.change(scheduledAt, interviewers == null ? "" : interviewers.strip());
        return view(companyId, stageId, applicationId);
    }

    /** 종료할 때 자동 저장만 된 답변도 한 번의 분석 이벤트로 넘긴다. */
    @Transactional
    public void submitPendingAnswers(UUID companyId, UUID stageId, UUID applicationId) {
        List<InterviewQuestion> card = questions.findByStageIdAndApplicationIdAndCompanyIdOrderBySeq(stageId,
                applicationId, companyId);
        boolean pending = card.stream().anyMatch(InterviewQuestion::isAnswerPendingAnalysis);
        if (pending) {
            card.forEach(InterviewQuestion::markAnalyzed);
            events.publishEvent(new InterviewAnswersChanged(companyId, stageId, applicationId));
        }
    }

    private void requirePlanning(UUID companyId, UUID stageId, UUID applicationId) {
        sessions.lock(companyId, stageId, applicationId).ifPresent(session -> {
            if (session.getStatus() != InterviewSessionStatus.SCHEDULED) {
                throw new ApiException(HttpStatus.CONFLICT, "INTERVIEW_STARTED",
                        "Interview assignments and question replacements are locked after the interview starts.");
            }
        });
    }

    private InterviewQuestion question(UUID companyId, UUID stageId, UUID questionId) {
        return questions.findByIdAndStageIdAndCompanyId(questionId, stageId, companyId).orElseThrow(
                () -> new ApiException(HttpStatus.NOT_FOUND, "QUESTION_NOT_FOUND", "Question not found."));
    }

    private StageInfo interviewStage(UUID companyId, UUID stageId, UUID applicationId) {
        StageInfo stage = recruits.getByStage(companyId, stageId).stage(stageId).orElseThrow();
        if (stage.type() != StageType.INTERVIEW) {
            throw new ApiException(HttpStatus.CONFLICT, "NOT_INTERVIEW_STAGE", "Only interview stages have questions.");
        }
        screening.detail(companyId, stageId, applicationId);
        return stage;
    }

    private StageInfo preparationStage(UUID companyId, UUID stageId, UUID applicationId) {
        RecruitmentInfo recruitment = recruits.getByStage(companyId, stageId);
        StageInfo stage = recruitment.stage(stageId).orElseThrow();
        if (stage.status() != StageStatus.PENDING) {
            return interviewStage(companyId, stageId, applicationId);
        }
        if (stage.type() != StageType.INTERVIEW) {
            throw new ApiException(HttpStatus.CONFLICT, "NOT_INTERVIEW_STAGE", "Only interview stages have questions.");
        }
        StageInfo previous = recruitment.stages().stream()
                .filter(other -> other.seq() < stage.seq())
                .max(Comparator.comparingInt(StageInfo::seq))
                .orElseThrow(() -> new ApiException(HttpStatus.CONFLICT, "NO_PREVIOUS_STAGE",
                        "Confirm the previous stage first."));
        if (!screening.results(companyId, previous.id()).passed().contains(applicationId)) {
            throw new ApiException(HttpStatus.NOT_FOUND, "INTERVIEW_CANDIDATE_NOT_FOUND",
                    "Only confirmed successful applicants can have prepared questions.");
        }
        return stage;
    }

    private static InterviewView.Schedule toSchedule(InterviewSchedule schedule) {
        return schedule == null ? null : new InterviewView.Schedule(schedule.getScheduledAt(),
                schedule.getInterviewers());
    }

    /** 🎤 질문은 순서대로 두되, 꼬리질문은 원래 질문 바로 뒤에 둔다 (질문 → 꼬리질문 → 꼬리질문의 꼬리질문 → 다음 질문). */
    private static List<InterviewView.Question> toQuestions(List<InterviewQuestion> found, String name) {
        Set<UUID> ids = found.stream().map(InterviewQuestion::getId).collect(Collectors.toSet());
        Map<UUID, List<InterviewQuestion>> children = found.stream()
                .filter(question -> question.getParentQuestionId() != null
                        && ids.contains(question.getParentQuestionId()))
                .collect(Collectors.groupingBy(InterviewQuestion::getParentQuestionId));
        List<InterviewQuestion> ordered = new ArrayList<>();
        found.stream()
                .filter(question -> question.getParentQuestionId() == null
                        || !ids.contains(question.getParentQuestionId()))
                .forEach(root -> addWithFollowUps(root, children, ordered));
        return ordered.stream()
                .map(question -> new InterviewView.Question(question.getId(),
                        question.getText().replaceFirst("^([\"“]?)" + Pattern.quote(name) + "\\s*[|｜]\\s*", "$1"),
                        question.getSource(),
                        question.getAnswer(), question.getReason(), question.getInterviewerRole(),
                        question.getParentQuestionId(), question.getVersion()))
                .toList();
    }

    private static void addWithFollowUps(InterviewQuestion question, Map<UUID, List<InterviewQuestion>> children,
            List<InterviewQuestion> ordered) {
        ordered.add(question);
        children.getOrDefault(question.getId(), List.of())
                .forEach(child -> addWithFollowUps(child, children, ordered));
    }
}
