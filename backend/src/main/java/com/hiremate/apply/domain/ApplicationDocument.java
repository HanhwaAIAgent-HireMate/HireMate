package com.hiremate.apply.domain;

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
