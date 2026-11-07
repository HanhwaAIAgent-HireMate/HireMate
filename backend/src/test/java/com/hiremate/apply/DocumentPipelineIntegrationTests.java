package com.hiremate.apply;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestFixtures.form;
import static com.hiremate.TestFixtures.publishBlind;
import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import com.hiremate.apply.domain.ApplicationDocument;
import com.hiremate.apply.domain.ApplicationDocumentRepository;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.test.context.TestPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.postgresql.PostgreSQLContainer;

/** Opt-in test of backend and the real AI job worker with fictional model output. */
@EnabledIfEnvironmentVariable(named = "HIREMATE_DOCUMENT_WORKER_E2E", matches = "1")
@TestPropertySource(properties = {"hiremate.ai.agents.application=remote", "hiremate.jobs.poll-interval=200ms"})
class DocumentPipelineIntegrationTests extends IntegrationTest {
    @Autowired
    private PostgreSQLContainer postgres;

    @Autowired
    @Qualifier("redisContainer")
    private GenericContainer<?> redis;

    @Autowired
    private ApplicationService applications;

    @Autowired
    private ApplicationDocumentRepository documents;

    @Test
    void uploadedBlindPdfsReachWorkerStorageIndexAndScopedSearch() throws Exception {
        Path log = Files.createTempFile("hiremate-document-e2e-", ".log");
        Process worker = startWorker(log);
        boolean passed = false;
        try {
            TestApi hr = newHr();
            var posting = publishBlind(hr, "");
            Map<String, Object> submitted = form("document-e2e@example.com", true);
            submitted.put("name", "SAMPLE");
            for (var entry : Map.of("resume", "resume", "coverLetter", "cover_letter", "portfolio", "portfolio")
                    .entrySet()) {
                Path pdf = Path.of("..", "ai", "tests", "samples", "document_quality_" + entry.getValue() + ".pdf");
                submitted.put(entry.getKey(), new TestApi.FilePart(entry.getValue() + ".pdf", "application/pdf",
                        Files.readAllBytes(pdf)));
            }
            expect(anonymous().multipart(posting.applyPath(), submitted), 201);
            UUID recruitmentId = UUID.fromString(posting.recruitmentId());
            UUID applicationId = applications.applicants(hr.companyId(), recruitmentId).getFirst().applicationId();
            List<ApplicationDocument> result = waitForDocuments(worker, applicationId);

            assertThat(result).hasSize(3).allSatisfy(document -> {
                assertThat(document.getNormalizationStatus()).isEqualTo(DocumentNormalizationStatus.COMPLETED);
                assertThat(document.getIndexStatus()).isEqualTo(DocumentNormalizationStatus.COMPLETED);
                assertThat(document.getIndexRevision()).isEqualTo(document.getRevision());
                assertThat(document.getNormalizedDocument()).isNotNull();
                assertThat(document.getNormalizedRequest().sources()).anySatisfy(source ->
                        assertThat(source.text()).contains("○○○").doesNotContain("SAMPLE"));
                assertThat(document.getNormalizedRequest().sources()).allSatisfy(source ->
                        assertThat(source.text()).doesNotContain("SAMPLE"));
            });
            passed = true;
        } finally {
            worker.destroy();
            if (!worker.waitFor(10, TimeUnit.SECONDS)) {
                worker.destroyForcibly();
                worker.waitFor();
            }
            if (passed) {
                Files.deleteIfExists(log);
            }
        }
    }

    private Process startWorker(Path log) throws Exception {
        ProcessBuilder builder = new ProcessBuilder("uv", "run", "python", "-m", "worker.document_e2e_worker")
                .directory(Path.of("..", "ai").toFile()).redirectErrorStream(true).redirectOutput(log.toFile());
        Map<String, String> env = builder.environment();
        String database = postgres.getHost() + ":" + postgres.getMappedPort(5432) + "/" + postgres.getDatabaseName();
        env.put("DATABASE_URL", "postgresql+psycopg://" + postgres.getUsername() + ":" + postgres.getPassword()
                + "@" + database);
        env.put("REDIS_URL", "redis://" + redis.getHost() + ":" + redis.getMappedPort(6379) + "/0");
        env.put("PYTHONPATH", "tests");
        env.put("LANGSMITH_TRACING", "false");
        env.put("WORKER_JOB_STREAM", "hiremate:jobs");
        env.put("WORKER_RESULT_STREAM", "hiremate:job-results");
        env.put("WORKER_GROUP", "ai-worker");
        env.put("NCS_MODEL", "document-e2e-fixture");
        return builder.start();
    }

    private List<ApplicationDocument> waitForDocuments(Process worker, UUID applicationId) throws Exception {
        Instant deadline = Instant.now().plus(Duration.ofSeconds(60));
        while (Instant.now().isBefore(deadline)) {
            assertThat(worker.isAlive()).as("test worker exited before processing documents").isTrue();
            List<ApplicationDocument> result = documents.findByApplicationId(applicationId);
            if (result.size() == 3 && result.stream().allMatch(document ->
                    document.getNormalizationStatus() == DocumentNormalizationStatus.COMPLETED
                    && document.getIndexStatus() == DocumentNormalizationStatus.COMPLETED)) {
                return result;
            }
            Thread.sleep(100);
        }
        throw new AssertionError("The fictional documents did not complete normalization and indexing");
    }
}
