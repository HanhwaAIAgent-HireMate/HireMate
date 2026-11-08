package com.hiremate.apply.domain;

import com.hiremate.apply.DocumentNormalizationStatus;
import com.hiremate.apply.NormalizedDocument;
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
    private NormalizedDocument normalizedDocument;

    @Column(nullable = false)
    private int revision = 1;

    @Enumerated(EnumType.STRING)
    @Column(length = 20)
    private DocumentNormalizationStatus indexStatus;

    private UUID indexJobId;

    @Column(nullable = false)
    private Instant indexUpdatedAt = Instant.now();

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private DocumentNormalizationStatus normalizationStatus = DocumentNormalizationStatus.PENDING;

    private UUID normalizationJobId;

    @Column(nullable = false)
    private Instant normalizationUpdatedAt = Instant.now();

    public void queueNormalization(UUID jobId) {
        normalizationJobId = jobId;
        normalizationUpdatedAt = Instant.now();
    }

    public void completeNormalization(UUID jobId, NormalizedDocument result) {
        if (!awaitsNormalization(jobId)) {
            return;
        }
        if (result == null || !id.equals(result.document().id())
                || !type.name().equalsIgnoreCase(result.document().type())) {
            failNormalization(jobId);
            return;
        }
        normalizedDocument = result;
        normalizationStatus = DocumentNormalizationStatus.COMPLETED;
        normalizationUpdatedAt = Instant.now();
        indexStatus = DocumentNormalizationStatus.PENDING;
        indexJobId = null;
        indexUpdatedAt = Instant.now();
    }

    public boolean awaitsNormalization(UUID jobId) {
        return normalizationStatus == DocumentNormalizationStatus.PENDING
                && jobId != null && jobId.equals(normalizationJobId);
    }

    public void failNormalization(UUID jobId) {
        if (awaitsNormalization(jobId)) {
            normalizationStatus = DocumentNormalizationStatus.FAILED;
            normalizationUpdatedAt = Instant.now();
        }
    }

    public void failUnqueuedNormalization() {
        if (normalizationStatus == DocumentNormalizationStatus.PENDING) {
            normalizationStatus = DocumentNormalizationStatus.FAILED;
            normalizationUpdatedAt = Instant.now();
        }
    }

    public void queueIndex(UUID jobId) {
        indexJobId = jobId;
        indexUpdatedAt = Instant.now();
    }

    public void finishIndex(UUID jobId, boolean success) {
        if (indexStatus == DocumentNormalizationStatus.PENDING && jobId != null && jobId.equals(indexJobId)) {
            indexStatus = success ? DocumentNormalizationStatus.COMPLETED : DocumentNormalizationStatus.FAILED;
            indexUpdatedAt = Instant.now();
        }
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
