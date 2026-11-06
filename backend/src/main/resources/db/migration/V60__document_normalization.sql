ALTER TABLE application_documents
    ADD COLUMN parsed_document jsonb,
    ADD COLUMN normalized_document jsonb,
    ADD COLUMN revision integer NOT NULL DEFAULT 1,
    ADD COLUMN normalization_status varchar(20) NOT NULL DEFAULT 'PENDING';

ALTER TABLE application_documents
    ADD CONSTRAINT application_document_revision_positive CHECK (revision > 0),
    ADD CONSTRAINT application_document_normalization_status_valid
        CHECK (normalization_status IN ('PENDING', 'COMPLETED', 'FAILED'));
