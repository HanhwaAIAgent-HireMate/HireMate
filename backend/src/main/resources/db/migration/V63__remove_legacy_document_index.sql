-- 이미 적용된 마이그레이션 이력은 유지하고 이전 정책으로 만든 결과를 비운다.
UPDATE application_documents
SET normalized_document = NULL,
    normalization_job_id = NULL,
    normalization_status = 'FAILED',
    normalization_updated_at = now();

DROP INDEX application_documents_pending_normalization;
ALTER TABLE application_documents
    DROP COLUMN parsed_document,
    DROP COLUMN normalization_request,
    DROP COLUMN normalized_request,
    DROP COLUMN index_job_id,
    DROP COLUMN index_revision,
    DROP COLUMN index_status;

CREATE INDEX application_documents_pending_normalization
    ON application_documents (normalization_updated_at)
    WHERE normalization_status = 'PENDING';
