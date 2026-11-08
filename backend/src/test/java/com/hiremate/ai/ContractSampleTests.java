package com.hiremate.ai;

import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.ai.application.CandidateAnalysis;
import com.hiremate.ai.application.CandidateProfileView;
import com.hiremate.ai.application.ChatApplied;
import com.hiremate.ai.application.ChatContext;
import com.hiremate.ai.application.ChatHistoryTurn;
import com.hiremate.ai.application.ChatPlan;
import com.hiremate.ai.application.ChatStatus;
import com.hiremate.ai.application.CitedQuestionDraft;
import com.hiremate.ai.application.CompanyFactors;
import com.hiremate.ai.application.ComposedReport;
import com.hiremate.ai.application.FeatureLabels;
import com.hiremate.ai.application.InterviewAnalysis;
import com.hiremate.ai.application.InterviewAnalysisInput;
import com.hiremate.ai.application.InterviewFollowUps;
import com.hiremate.ai.application.InterviewFollowUpsRequest;
import com.hiremate.ai.application.InterviewQuestionsRequest;
import com.hiremate.ai.application.InterviewerMemo;
import com.hiremate.ai.application.PostingAgent;
import com.hiremate.ai.application.ReportBundle;
import com.hiremate.ai.application.TalentFit;
import com.hiremate.ai.application.TalentFitRequest;
import com.hiremate.apply.ApplicantDetail;
import com.hiremate.apply.ApplicationAnalysis;
import com.hiremate.apply.DocumentNormalizationRequest;
import com.hiremate.apply.NormalizedDocument;
import com.hiremate.company.CompanyProfile;
import com.hiremate.interview.InterviewQuestionDraft;
import com.hiremate.interview.InterviewView;
import com.hiremate.job.Job;
import com.hiremate.job.JobResult;
import com.hiremate.posting.PosterDesign;
import com.hiremate.posting.PosterProposal;
import com.hiremate.posting.PosterTurn;
import com.hiremate.posting.PostingContent;
import com.hiremate.posting.PostingDraftContext;
import com.hiremate.posting.PostingFocus;
import com.hiremate.posting.PostingSuggestion;
import com.hiremate.posting.ScreeningRubric;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.json.JsonTest;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/**
 * 저장소 루트 contract/의 JSON 샘플로 ai 서버와 주고받는 레코드를 왕복 검사한다. ai 쪽 tests/test_contract.py도 같은 샘플을 쓴다.
 */
@JsonTest
class ContractSampleTests {

    private static final Path CONTRACT_DIR = Path.of("..", "contract");

    /** 샘플 파일 이름 → 타입. ai의 tests/test_contract.py SAMPLES와 같게 유지한다. */
    private static final Map<String, Class<?>> SAMPLES = Map.ofEntries(
            Map.entry("ApplicantDetail", ApplicantDetail.class),
            Map.entry("ApplicationAnalysis", ApplicationAnalysis.class),
            Map.entry("DocumentNormalizationRequest", DocumentNormalizationRequest.class),
            Map.entry("NormalizedDocument", NormalizedDocument.class),
            Map.entry("CandidateAnalysis", CandidateAnalysis.class),
            Map.entry("CandidateProfileView", CandidateProfileView.class),
            Map.entry("ChatApplied", ChatApplied.class),
            Map.entry("ChatContext", ChatContext.class),
            Map.entry("ChatHistoryTurn", ChatHistoryTurn.class),
            Map.entry("ChatPlan", ChatPlan.class),
            Map.entry("CitedQuestionDraft", CitedQuestionDraft.class),
            Map.entry("ChatStatus", ChatStatus.class),
            Map.entry("CompanyProfile", CompanyProfile.class),
            Map.entry("ComposedReport", ComposedReport.class),
            Map.entry("FeatureLabels", FeatureLabels.class),
            Map.entry("CompanyFactors", CompanyFactors.class),
            Map.entry("InterviewAnalysis", InterviewAnalysis.class),
            Map.entry("InterviewView", InterviewView.class),
            Map.entry("InterviewFollowUps", InterviewFollowUps.class),
            Map.entry("InterviewFollowUpsRequest", InterviewFollowUpsRequest.class),
            Map.entry("InterviewQuestionDraft", InterviewQuestionDraft.class),
            Map.entry("InterviewerMemo", InterviewerMemo.class),
            Map.entry("InterviewAnalysisInput", InterviewAnalysisInput.class),
            Map.entry("InterviewQuestionsRequest", InterviewQuestionsRequest.class),
            Map.entry("Job", Job.class),
            Map.entry("JobResult", JobResult.class),
            Map.entry("NcsSource", PostingAgent.NcsSource.class),
            Map.entry("PostingContent", PostingContent.class),
            Map.entry("PosterDesign", PosterDesign.class),
            Map.entry("PosterProposal", PosterProposal.class),
            Map.entry("PosterTurn", PosterTurn.class),
            Map.entry("PostingDraftContext", PostingDraftContext.class),
            Map.entry("PostingFocus", PostingFocus.class),
            Map.entry("PostingSuggestion", PostingSuggestion.class),
            Map.entry("ReportBundle", ReportBundle.class),
            Map.entry("ScreeningRubric", ScreeningRubric.class),
            Map.entry("TalentFit", TalentFit.class),
            Map.entry("TalentFitRequest", TalentFitRequest.class));

    @Autowired
    private JsonMapper mapper;

    static Stream<String> samples() {
        return SAMPLES.keySet().stream().sorted();
    }

    @Test
    @DisplayName("contract/의 샘플마다 검사할 타입이 있다")
    void everySampleHasType() throws IOException {
        try (Stream<Path> files = Files.list(CONTRACT_DIR)) {
            Set<String> names = files.map(path -> path.getFileName().toString())
                    .filter(name -> name.endsWith(".json"))
                    .map(name -> name.substring(0, name.length() - ".json".length()))
                    .collect(Collectors.toSet());

            assertThat(names).isEqualTo(SAMPLES.keySet());
        }
    }

    @Test
    @DisplayName("NCS 참고 여부가 없는 면접 질문 요청은 ncs 칸 없이 보낸다 (main과 같은 본문)")
    void missingNcsIsNotSent() throws IOException {
        JsonNode written = mapper.readTree(mapper.writeValueAsString(
                new InterviewQuestionsRequest(null, null, null, null, null, "범위", 2)));

        assertThat(written.has("ncs")).isFalse();
        assertThat(written.has("memo")).isTrue();
    }

    @ParameterizedTest
    @MethodSource("samples")
    @DisplayName("샘플을 레코드로 읽고 다시 쓰면 샘플과 같다")
    void roundTrip(String name) throws IOException {
        JsonNode sample = mapper.readTree(Files.readString(CONTRACT_DIR.resolve(name + ".json")));

        Object record = mapper.treeToValue(sample, SAMPLES.get(name));
        JsonNode written = mapper.readTree(mapper.writeValueAsString(record));

        assertThat(written).isEqualTo(sample);
    }
}
