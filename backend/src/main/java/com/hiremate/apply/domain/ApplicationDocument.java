package com.hiremate.apply.domain;

import com.hiremate.apply.DocumentNormalizationRequest;
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
import java.time.Instant;
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

    private UUID normalizationJobId;

    @Column(nullable = false)
    private Instant normalizationUpdatedAt = Instant.now();

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private DocumentNormalizationRequest normalizationRequest;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private DocumentNormalizationRequest normalizedRequest;

    public void queueNormalization(UUID jobId, DocumentNormalizationRequest request) {
        this.normalizationJobId = jobId;
        this.normalizationRequest = request;
        this.normalizationUpdatedAt = Instant.now();
    }

    public boolean awaitsNormalization(UUID jobId) {
        return normalizationStatus == DocumentNormalizationStatus.PENDING
                && jobId != null && jobId.equals(normalizationJobId);
    }

    public void completeNormalization(NormalizedDocument document) {
        this.normalizedDocument = document;
        this.normalizedRequest = normalizationRequest;
        this.normalizationStatus = DocumentNormalizationStatus.COMPLETED;
        this.normalizationUpdatedAt = Instant.now();
    }

    public void failNormalization() {
        this.normalizationStatus = DocumentNormalizationStatus.FAILED;
        this.normalizationUpdatedAt = Instant.now();
    }

    public void requestNormalization() {
        this.revision++;
        this.normalizationStatus = DocumentNormalizationStatus.PENDING;
        this.normalizationJobId = null;
        this.normalizationRequest = null;
        this.normalizationUpdatedAt = Instant.now();
    }

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
