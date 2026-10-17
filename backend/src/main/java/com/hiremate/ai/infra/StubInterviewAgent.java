package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import com.hiremate.ai.application.CandidateAnalysis;
import com.hiremate.ai.application.InterviewAgent;
import com.hiremate.apply.ApplicantDetail;
import com.hiremate.interview.InterviewView;
import com.hiremate.posting.PostingContent;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
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

    @Override
    public List<String> questions(ApplicantDetail applicant, PostingContent posting, CandidateAnalysis analysis,
            InterviewView interview, String focus) {
        Set<String> questions = new LinkedHashSet<>();
        String scope = focus == null ? "" : focus;
        boolean onlyUnchecked = scope.contains("확인 안") || scope.contains("아직");
        for (InterviewView.PreviousInterview previous : interview.previous()) {
            for (InterviewView.Question question : previous.questions()) {
                if (question.answer().strip().length() < SHORT_ANSWER) {
                    questions.add(previous.stageName() + "에서 충분히 확인하지 못한 \"" + shorten(question.text())
                            + "\"을 조금 더 구체적으로 이야기해 주세요.");
                }
            }
        }
        if (scope.contains("협업")) {
            questions.add("동료와 의견이 달랐을 때 어떻게 조율했는지 사례로 말씀해 주세요.");
        }
        if (scope.contains("리더") || onlyUnchecked) {
            questions.add("팀의 기술 방향을 정할 때 동료를 설득한 경험이 있나요?");
        }
        if (scope.contains("커리어") || scope.contains("성장") || onlyUnchecked) {
            questions.add("3년 뒤 우리 팀에서 하고 싶은 일은 무엇인가요?");
        }
        if (!onlyUnchecked) {
            analysis.notable().stream().limit(2).forEach(found -> questions.add(
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
        return fresh.stream().limit(3).toList();
    }

    private static String shorten(String text) {
        // 질문 안에 다시 따옴표로 인용하므로 원문의 따옴표는 뺀다
        String trimmed = text.strip().replaceAll("[\"“”]", "").replaceAll("\\s+", " ");
        return trimmed.length() > 36 ? trimmed.substring(0, 35) + "…" : trimmed;
    }
}
