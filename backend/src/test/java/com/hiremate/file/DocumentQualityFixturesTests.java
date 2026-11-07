package com.hiremate.file;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.hiremate.apply.DocumentIndexRequest;
import com.hiremate.apply.DocumentNormalizationRequest;
import com.hiremate.apply.NormalizedDocument;
import com.hiremate.apply.ParsedDocument;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class DocumentQualityFixturesTests {

    @Test
    void sharedSyntheticSourcesMatchPdfExtractionAndBlindProcessing() throws Exception {
        ObjectMapper json = new ObjectMapper();
        Path sources = Path.of("..", "ai", "tests", "samples", "document_quality_sources.json");
        JsonNode expected = json.readTree(Files.readString(sources));
        for (String name : List.of("resume", "cover_letter", "portfolio", "korean")) {
            Path pdf = Path.of("..", "ai", "tests", "samples", "document_quality_" + name + ".pdf");
            PdfText.Result result = PdfText.parse(Files.readAllBytes(pdf));
            ParsedDocument parsed = ParsedDocument.from(result, true);
            JsonNode actual = json.valueToTree(parsed.sources());
            assertThat(actual).as(name).isEqualTo(expected.get(name));
        }
    }

    @Test
    void acceptsLunaFixtureResultsAgainstSourcesExtractedFromThePdfs() throws Exception {
        ObjectMapper json = new ObjectMapper();
        Path output = Path.of("..", "ai", "tests", "eval", "document_quality_luna_documents.json");
        JsonNode documents = json.readTree(Files.readString(output));
        for (String name : List.of("resume", "cover_letter", "portfolio")) {
            Path pdf = Path.of("..", "ai", "tests", "samples", "document_quality_" + name + ".pdf");
            ParsedDocument parsed = ParsedDocument.from(PdfText.parse(Files.readAllBytes(pdf)), true);
            NormalizedDocument document = json.treeToValue(documents.get(name), NormalizedDocument.class);
            DocumentNormalizationRequest request = new DocumentNormalizationRequest(UUID.randomUUID(),
                    UUID.randomUUID(), UUID.randomUUID(), document.documentId(), document.revision(),
                    document.documentType(), parsed.sources());
            DocumentIndexRequest indexed = new DocumentIndexRequest(request, document);
            assertThat(indexed.document().blocks()).as(name).isNotEmpty();
        }
    }

    /** Prints only fictional fixture text to make the actual parser output reusable by the evaluator. */
    @Test
    void extractsEachSyntheticDocumentWithoutChangingTheSource() throws Exception {
        ObjectMapper json = new ObjectMapper();
        for (var fixture : Map.of("resume", 1, "cover_letter", 1, "portfolio", 2, "korean", 1).entrySet()) {
            Path pdf = Path.of("..", "ai", "tests", "samples", "document_quality_" + fixture.getKey() + ".pdf");
            PdfText.Result result = PdfText.parse(Files.readAllBytes(pdf));
            assertThat(result.pageCount()).isEqualTo(fixture.getValue());
            assertThat(result.pages()).allSatisfy(page -> assertThat(page.text()).isNotBlank());
            assertThat(result.issues()).isEmpty();
            if (fixture.getKey().equals("korean")) {
                assertThat(result.text()).contains("지원동기", "예약 변경 정책을", "데이터로 확인했습니다.", "지원서 1");
            }
            ParsedDocument parsed = ParsedDocument.from(result, false);
            System.out.println("DOCUMENT_QUALITY_SOURCE " + fixture.getKey() + " "
                    + json.writeValueAsString(parsed.sources()));
        }
    }
}
