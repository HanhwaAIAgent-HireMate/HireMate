package com.hiremate.apply.domain;

import com.hiremate.apply.DocumentNormalizationStatus;
import com.hiremate.apply.NormalizedDocument;
import com.hiremate.apply.ParsedDocument;
import com.hiremate.posting.DocumentType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@Entity
@Table(name = "application_documents")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class ApplicationDocument {

    @Id
    private UUID id;

    @Column(nullable = false)
    private UUID applicationId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private DocumentType type;

    @Column(nullable = false)
    private UUID fileId;

    @Column(nullable = false)
    private String fileName;

    @Column(nullable = false)
    private long sizeBytes;

    /** PDF에서 추출한 본문. 추출하지 못하면 빈 문자열이다. */
    @Column(nullable = false)
    private String text;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private ParsedDocument parsedDocument;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private NormalizedDocument normalizedDocument;

    @Column(nullable = false)
    private int revision = 1;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private DocumentNormalizationStatus normalizationStatus = DocumentNormalizationStatus.PENDING;

    public void recordParsedDocument(ParsedDocument parsed) {
        this.parsedDocument = parsed;
    }

    public ApplicationDocument(UUID applicationId, DocumentType type, UUID fileId, String fileName, long sizeBytes,
            String text) {
        this.id = UUID.randomUUID();
        this.applicationId = applicationId;
        this.type = type;
        this.fileId = fileId;
        this.fileName = fileName;
        this.sizeBytes = sizeBytes;
        this.text = text;
    }
}
