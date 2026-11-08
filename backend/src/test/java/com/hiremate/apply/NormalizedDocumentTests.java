package com.hiremate.apply;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class NormalizedDocumentTests {
    @Test
    void acceptsStructuredOutputWithoutCheckingExtractedText() {
        UUID id = UUID.randomUUID();
        var document = new NormalizedDocument("1.0", new NormalizedDocument.Metadata(id, "resume", null, 1),
                List.of(new NormalizedDocument.Paragraph("block-0001", List.of(1), "정리된 문장")));
        assertThat(document.document().id()).isEqualTo(id);
    }

    @Test
    void rejectsPagesOutsideTheDocument() {
        var metadata = new NormalizedDocument.Metadata(UUID.randomUUID(), "resume", null, 1);
        assertThatThrownBy(() -> new NormalizedDocument("1.0", metadata,
                List.of(new NormalizedDocument.Paragraph("block-0001", List.of(2), "내용"))))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
