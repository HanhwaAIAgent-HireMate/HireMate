package com.hiremate.ai;

import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.ai.application.CandidateAnalysis;
import com.hiremate.ai.application.ChatContext;
import com.hiremate.ai.application.ChatHistoryTurn;
import com.hiremate.ai.application.ChatPlan;
import com.hiremate.apply.ApplicantDetail;
import com.hiremate.apply.ApplicationAnalysis;
import com.hiremate.company.CompanyProfile;
import com.hiremate.job.Job;
import com.hiremate.job.JobResult;
import com.hiremate.posting.PostingContent;
import com.hiremate.posting.PostingDraftContext;
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
            Map.entry("CandidateAnalysis", CandidateAnalysis.class),
            Map.entry("ChatContext", ChatContext.class),
            Map.entry("ChatHistoryTurn", ChatHistoryTurn.class),
            Map.entry("ChatPlan", ChatPlan.class),
            Map.entry("CompanyProfile", CompanyProfile.class),
            Map.entry("Job", Job.class),
            Map.entry("JobResult", JobResult.class),
            Map.entry("PostingContent", PostingContent.class),
            Map.entry("PostingDraftContext", PostingDraftContext.class),
            Map.entry("PostingSuggestion", PostingSuggestion.class),
            Map.entry("ScreeningRubric", ScreeningRubric.class));

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
