ALTER TABLE application_documents
    ADD COLUMN index_status varchar(20),
    ADD COLUMN index_job_id uuid,
    ADD COLUMN index_updated_at timestamptz NOT NULL DEFAULT now();

UPDATE application_documents
SET index_status = 'PENDING'
WHERE normalization_status = 'COMPLETED' AND normalized_document IS NOT NULL;

CREATE INDEX application_documents_pending_index
    ON application_documents (index_updated_at)
    WHERE index_status = 'PENDING';
