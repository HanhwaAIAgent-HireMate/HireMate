ALTER TABLE application_documents
    ADD COLUMN normalization_job_id uuid,
    ADD COLUMN normalization_updated_at timestamptz NOT NULL DEFAULT now(),
    ADD COLUMN normalization_request jsonb,
    ADD COLUMN normalized_request jsonb;

CREATE INDEX application_documents_pending_normalization
    ON application_documents (normalization_updated_at)
    WHERE normalization_status = 'PENDING' AND parsed_document IS NOT NULL;
