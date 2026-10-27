package com.hiremate.interview;

import com.hiremate.apply.ApplicationService;
import com.hiremate.global.ApiException;
import com.hiremate.interview.domain.InterviewQuestion;
import com.hiremate.interview.domain.InterviewQuestionRepository;
import com.hiremate.interview.domain.InterviewSchedule;
import com.hiremate.interview.domain.InterviewScheduleRepository;
import com.hiremate.recruit.RecruitService;
import com.hiremate.recruit.RecruitmentInfo;
import com.hiremate.recruit.StageInfo;
import com.hiremate.recruit.StageStatus;
import com.hiremate.recruit.StageType;
import com.hiremate.screening.ScreeningService;
import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
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

    private final InterviewQuestionRepository questions;
    private final InterviewScheduleRepository schedules;
    private final RecruitService recruits;
    private final ScreeningService screening;
    private final ApplicationEventPublisher events;
    private final ApplicationService applications;

    public InterviewService(InterviewQuestionRepository questions, InterviewScheduleRepository schedules,
            RecruitService recruits, ScreeningService screening, ApplicationEventPublisher events,
            ApplicationService applications) {
        this.questions = questions;
        this.schedules = schedules;
        this.recruits = recruits;
        this.screening = screening;
        this.events = events;
        this.applications = applications;
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
                toQuestions(byStage.getOrDefault(stageId, List.of()), name), previous);
    }

    /** 시작 전인 다음 면접의 자료. 바로 앞 전형에서 합격이 확정된 지원자만 준비할 수 있다. */
    @Transactional(readOnly = true)
    public InterviewView preparationView(UUID companyId, UUID stageId, UUID applicationId) {
        return view(companyId, preparationStage(companyId, stageId, applicationId), applicationId);
    }

    /** 맞춤 질문을 카드에 넣는다. 이미 있는 질문은 다시 넣지 않는다. */
    @Transactional
    public InterviewView addQuestions(UUID companyId, UUID stageId, UUID applicationId, List<String> texts,
            QuestionSource source) {
        StageInfo stage = interviewStage(companyId, stageId, applicationId);
        saveQuestions(companyId, stageId, applicationId, texts, source);
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
        List<InterviewQuestion> existing = questions.findByStageIdAndApplicationIdAndCompanyIdOrderBySeq(stageId,
                applicationId, companyId);
        Set<String> seen = existing.stream().map(InterviewQuestion::getText).collect(Collectors.toSet());
        if (source == QuestionSource.AI && seen.add(INTRO)) {
            questions.save(new InterviewQuestion(stageId, applicationId, companyId, 0, INTRO, source,
                    "공통 질문: 모든 면접에서 지원자의 주요 경험과 지원 동기를 먼저 듣기 위한 자기소개입니다."));
        }
        int seq = existing.stream().mapToInt(InterviewQuestion::getSeq).max().orElse(0);
        for (InterviewQuestionDraft draft : drafts) {
            String trimmed = draft.text().strip();
            if (!trimmed.isEmpty() && seen.add(trimmed)) {
                questions.save(new InterviewQuestion(stageId, applicationId, companyId, ++seq, trimmed, source,
                        draft.reason()));
            }
        }
    }

    @Transactional
    public InterviewView answer(UUID companyId, UUID stageId, UUID questionId, String answer) {
        InterviewQuestion question = question(companyId, stageId, questionId);
        if (!question.getAnswer().equals(answer)) {
            question.answer(answer);
            events.publishEvent(new InterviewAnswersChanged(companyId, stageId, question.getApplicationId()));
        }
        return view(companyId, stageId, question.getApplicationId());
    }

    @Transactional
    public InterviewView deleteQuestion(UUID companyId, UUID stageId, UUID questionId) {
        InterviewQuestion question = question(companyId, stageId, questionId);
        questions.delete(question);
        if (!question.getAnswer().isBlank()) {
            events.publishEvent(new InterviewAnswersChanged(companyId, stageId, question.getApplicationId()));
        }
        return view(companyId, stageId, question.getApplicationId());
    }

    /** 담당자가 요청한 현재 면접 질문만 백업 없이 제거한다. 이전 면접 기록은 유지한다. */
    @Transactional
    public void clearQuestions(UUID companyId, UUID stageId, UUID applicationId) {
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

    private static List<InterviewView.Question> toQuestions(List<InterviewQuestion> found, String name) {
        return found.stream()
                .map(question -> new InterviewView.Question(question.getId(),
                        question.getText().replaceFirst("^([\"“]?)" + Pattern.quote(name) + "\\s*[|｜]\\s*", "$1"),
                        question.getSource(),
                        question.getAnswer(), question.getReason()))
                .toList();
    }
}
