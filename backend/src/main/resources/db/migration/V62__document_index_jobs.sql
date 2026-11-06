ALTER TABLE application_documents
    ADD COLUMN index_job_id UUID,
    ADD COLUMN index_revision INTEGER,
    ADD COLUMN index_status VARCHAR(20);
