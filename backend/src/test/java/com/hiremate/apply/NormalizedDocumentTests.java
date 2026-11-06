package com.hiremate.apply;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.hiremate.posting.DocumentType;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class NormalizedDocumentTests {
    @Test
    void rejectsInvalidSourcePage() {
        assertThatThrownBy(() -> new DocumentSource("s1", 0, "text"))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void rejectsUntitledSectionSources() {
        assertThatThrownBy(() -> new NormalizedDocument.Section("b1", List.of("s1"), null, List.of()))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void rejectsDuplicateBlockIdsAndUnknownSources() {
        var block = new NormalizedDocument.Paragraph("b1", List.of("s1"), "body", "text");
        assertThatThrownBy(() -> new NormalizedDocument(1, UUID.randomUUID(), 1,
                DocumentType.RESUME, List.of(block, block))).isInstanceOf(IllegalArgumentException.class);
        var document = new NormalizedDocument(1, UUID.randomUUID(), 1, DocumentType.RESUME, List.of(block));
        assertThatThrownBy(() -> document.validateSources(List.of())).isInstanceOf(IllegalArgumentException.class);
        document.validateSources(List.of(new DocumentSource("s1", null, "text")));
    }

    @Test
    void rejectsUnknownRolesAndUntrustedNotice() {
        assertThatThrownBy(() -> new NormalizedDocument.Paragraph("b1", List.of(), "unknown", "text"))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new NormalizedDocument.Reference("b1", List.of(),
                "possible_visual", null, "generated notice")).isInstanceOf(IllegalArgumentException.class);
    }
}
