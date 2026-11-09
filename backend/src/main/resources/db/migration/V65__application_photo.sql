ALTER TABLE applications ADD COLUMN photo_file_id UUID REFERENCES stored_files (id);
