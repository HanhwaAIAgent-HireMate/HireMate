package com.hiremate.interview;

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

    private final InterviewQuestionRepository questions;
    private final InterviewScheduleRepository schedules;
    private final RecruitService recruits;
    private final ScreeningService screening;
    private final ApplicationEventPublisher events;

    public InterviewService(InterviewQuestionRepository questions, InterviewScheduleRepository schedules,
            RecruitService recruits, ScreeningService screening, ApplicationEventPublisher events) {
        this.questions = questions;
        this.schedules = schedules;
        this.recruits = recruits;
        this.screening = screening;
        this.events = events;
    }

    @Transactional(readOnly = true)
    public InterviewView view(UUID companyId, UUID stageId, UUID applicationId) {
        StageInfo stage = interviewStage(companyId, stageId, applicationId);
        return view(companyId, stage, applicationId);
    }

    private InterviewView view(UUID companyId, StageInfo stage, UUID applicationId) {
        UUID stageId = stage.id();
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
                        toSchedule(scheduleByStage.get(other.id())), toQuestions(byStage.get(other.id()))))
                .toList();
        return new InterviewView(applicationId, toSchedule(scheduleByStage.get(stageId)),
                toQuestions(byStage.getOrDefault(stageId, List.of())), previous);
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
        List<InterviewQuestion> existing = questions.findByStageIdAndApplicationIdAndCompanyIdOrderBySeq(stageId,
                applicationId, companyId);
        Set<String> seen = existing.stream().map(InterviewQuestion::getText).collect(Collectors.toSet());
        int seq = existing.stream().mapToInt(InterviewQuestion::getSeq).max().orElse(0);
        for (String text : texts) {
            String trimmed = text.strip();
            if (!trimmed.isEmpty() && seen.add(trimmed)) {
                questions.save(new InterviewQuestion(stageId, applicationId, companyId, ++seq, trimmed, source));
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

    private static List<InterviewView.Question> toQuestions(List<InterviewQuestion> found) {
        return found.stream()
                .map(question -> new InterviewView.Question(question.getId(), question.getText(), question.getSource(),
                        question.getAnswer()))
                .toList();
    }
}
