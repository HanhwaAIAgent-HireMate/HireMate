package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import com.hiremate.ai.application.CandidateAnalysis;
import com.hiremate.ai.application.InterviewAgent;
import com.hiremate.ai.application.InterviewFollowUps;
import com.hiremate.ai.application.InterviewFollowUpsRequest;
import com.hiremate.apply.ApplicantDetail;
import com.hiremate.company.CompanyProfile;
import com.hiremate.interview.InterviewQuestionDraft;
import com.hiremate.interview.InterviewView;
import com.hiremate.interview.InterviewerRole;
import com.hiremate.posting.PostingContent;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import org.springframework.stereotype.Component;

/**
 * 개발용 Interview Agent. 분석의 눈여겨볼 점은 역할 확인 질문으로, 확인 필요는 경험 확인 질문으로 바꾸고,
 * 이전 면접에서 답이 짧았던 질문은 다시 확인하는 질문으로 만든다.
 */
@Component
@ConditionalOnAiMode(agent = AiAgent.INTERVIEW, mode = AiMode.STUB)
class StubInterviewAgent implements InterviewAgent {

    private static final int SHORT_ANSWER = 15;
    private static final int FOLLOW_UP_ANSWER = 40;

    @Override
    public List<InterviewQuestionDraft> questions(ApplicantDetail applicant, PostingContent posting,
            CandidateAnalysis analysis,
            InterviewView interview, CompanyProfile company, String focus,
            Integer questionCount) {
        Set<String> questions = new LinkedHashSet<>();
        Map<String, InterviewerRole> roles = new HashMap<>();
        String scope = focus == null ? "" : focus;
        boolean onlyUnchecked = scope.contains("확인 안") || scope.contains("아직");
        if (scope.contains("프로젝트")) {
            questions.add("지원서의 대표 프로젝트에서 본인이 직접 맡은 작업과 가장 어려웠던 판단을 설명해 주세요.");
        }
        for (InterviewView.PreviousInterview previous : interview.previous()) {
            for (InterviewView.Question question : previous.questions()) {
                if (question.answer().strip().length() < SHORT_ANSWER) {
                    String followUp = previous.stageName() + "에서 충분히 확인하지 못한 \"" + shorten(question.text())
                            + "\"을 조금 더 구체적으로 이야기해 주세요.";
                    questions.add(followUp);
                    // 🎤 후속 질문은 원래 질문의 담당이 잇는다. 원래 담당이 비어 있으면 실무 (AI 워커와 같은 규칙)
                    //   null을 그대로 넣으면 아래 getOrDefault가 기본값 대신 null을 돌려준다
                    roles.put(followUp,
                            Objects.requireNonNullElse(question.interviewerRole(), InterviewerRole.PRACTICAL));
                }
            }
        }
        if (scope.contains("협업")) {
            questions.add("동료와 의견이 달랐을 때 어떻게 조율했는지 사례로 말씀해 주세요.");
            roles.put("동료와 의견이 달랐을 때 어떻게 조율했는지 사례로 말씀해 주세요.", InterviewerRole.HR);
        }
        if (scope.contains("리더") || onlyUnchecked) {
            questions.add("팀의 기술 방향을 정할 때 동료를 설득한 경험이 있나요?");
        }
        if (scope.contains("커리어") || scope.contains("성장") || onlyUnchecked) {
            questions.add("3년 뒤 우리 팀에서 하고 싶은 일은 무엇인가요?");
            roles.put("3년 뒤 우리 팀에서 하고 싶은 일은 무엇인가요?", InterviewerRole.HR);
        }
        if (!onlyUnchecked) {
            analysis.notable().stream().filter(found -> !documentHeader(found.text(), applicant.info().name()))
                    .limit(2).forEach(found -> questions.add(
                    "\"" + shorten(found.text()) + "\"에서 본인이 맡은 역할과 판단 근거를 말해 주세요."));
            analysis.conditions().stream().filter(condition -> !condition.met()).limit(1)
                    .forEach(condition -> questions.add(
                            "\"" + condition.requirement() + "\"와 관련해 직접 해 본 경험을 사례로 설명해 주세요."));
        }
        if (questions.isEmpty()) {
            questions.add("지원서에 적은 대표 경험에서 가장 어려웠던 결정은 무엇이었나요?");
        }
        Set<String> existing = new LinkedHashSet<>(interview.questions().stream()
                .map(InterviewView.Question::text).toList());
        List<String> fresh = new ArrayList<>(questions);
        fresh.removeAll(existing);
        if (interview.singleInterview() && questionCount == null && scope.isBlank() && existing.isEmpty()) {
            List<String> core = new ArrayList<>(fresh.stream().limit(3).toList());
            for (String fallback : List.of("직무와 관련해 직접 맡은 일과 선택한 방법의 이유를 말해 주세요.",
                    "이 직무의 결과가 좋은지 판단할 기준을 설명해 주세요.",
                    "업무 결과가 예상과 다를 때 먼저 확인할 자료와 그 이유를 설명해 주세요.")) {
                if (core.size() < 3 && !core.contains(fallback)) {
                    core.add(fallback);
                }
            }
            core.add("동료의 피드백을 반영해 일하는 방식을 바꾼 경험이 있다면 말해 주세요.");
            roles.put("동료의 피드백을 반영해 일하는 방식을 바꾼 경험이 있다면 말해 주세요.", InterviewerRole.HR);
            core.add("이 회사와 직무에 지원한 이유와 입사 후 하고 싶은 일을 말해 주세요.");
            roles.put("이 회사와 직무에 지원한 이유와 입사 후 하고 싶은 일을 말해 주세요.", InterviewerRole.HR);
            return core.stream().map(text -> new InterviewQuestionDraft(text,
                    "개발용 기본 질문입니다. 실제 모델의 생성 근거가 아닙니다.",
                        roles.getOrDefault(text, InterviewerRole.PRACTICAL))).toList();
        }
        return fresh.stream().limit(questionCount == null ? 3 : questionCount)
                .map(text -> new InterviewQuestionDraft(text, "개발용 기본 질문입니다. 실제 모델의 생성 근거가 아닙니다.",
                        roles.getOrDefault(text, InterviewerRole.PRACTICAL)))
                .toList();
    }

    @Override
    public Optional<List<InterviewQuestionDraft>> prepare(String target, ApplicantDetail applicant,
            PostingContent posting,
            CandidateAnalysis analysis, InterviewView interview, CompanyProfile company) {
        return Optional.of(questions(applicant, posting, analysis, interview, company, null, null));
    }

    /**
     * 🎤 개발용 꼬리질문: 답이 짧으면(40자 미만) 구체적인 사례와 본인 역할을 묻는 두 질문을, 길면 확인할 점이 없다고 돌려준다.
     * [다시 제안]이면 앞서 보여 준 제안을 빼고 다른 문장을 낸다.
     */
    @Override
    public InterviewFollowUps followUps(InterviewFollowUpsRequest request) {
        InterviewView.Question last = request.chain().getLast();
        if (last.answer().strip().length() >= FOLLOW_UP_ANSWER) {
            return InterviewFollowUps.none();
        }
        List<InterviewFollowUps.Suggestion> candidates = List.of(
                new InterviewFollowUps.Suggestion("방금 말씀하신 내용을 실제 사례 하나로 조금 더 구체적으로 설명해 주시겠어요?",
                        "답변에 구체적인 사례가 없습니다."),
                new InterviewFollowUps.Suggestion("그 일에서 본인이 직접 맡은 부분과 결과는 무엇이었나요?",
                        "본인 역할과 결과가 드러나지 않았습니다."),
                new InterviewFollowUps.Suggestion("그때 다른 방법도 고려했다면 지금 방법을 고른 이유는 무엇인가요?",
                        "판단 근거가 드러나지 않았습니다."),
                new InterviewFollowUps.Suggestion("다시 같은 상황이 온다면 무엇을 다르게 하시겠어요?",
                        "경험에서 배운 점이 드러나지 않았습니다."));
        return new InterviewFollowUps(true, candidates.stream()
                .filter(candidate -> !request.avoid().contains(candidate.text())).limit(2).toList());
    }

    private static String shorten(String text) {
        // 질문 안에 다시 따옴표로 인용하므로 원문의 따옴표는 뺀다
        String trimmed = text.strip().replaceAll("[\"“”]", "").replaceAll("\\s+", " ");
        return trimmed.length() > 36 ? trimmed.substring(0, 35) + "…" : trimmed;
    }

    private static boolean documentHeader(String text, String name) {
        return text.strip().matches("(?is)^" + java.util.regex.Pattern.quote(name) + "\\s*[|｜].*")
                || text.strip().startsWith("SYNTHETIC SAMPLE");
    }
}
