ALTER TABLE notices
    ADD COLUMN onboarding_start VARCHAR(200) NOT NULL DEFAULT '',
    ADD COLUMN onboarding_place VARCHAR(500) NOT NULL DEFAULT '',
    ADD COLUMN onboarding_documents VARCHAR(1000) NOT NULL DEFAULT '',
    ADD COLUMN onboarding_preparation VARCHAR(1000) NOT NULL DEFAULT '',
    ADD COLUMN onboarding_note VARCHAR(1000) NOT NULL DEFAULT '';
