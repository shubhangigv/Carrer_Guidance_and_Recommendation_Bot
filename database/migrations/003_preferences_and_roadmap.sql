-- Migration 003: student preferences on an assessment, and roadmap progress.
--
-- Changes:
--   * assessment.preferred_location (where the student wants to work, for job-search links)
--   * assessment.about_me (optional free text for the semantic matcher)
--   * new table roadmap_progress (which roadmap steps a student has finished)
--
-- Only needed for a database created BEFORE this change (new databases get it from schema.sql).
-- Safe to run again: each step first looks in information_schema. Applied automatically by
-- backend.db.update_schema() (the loader and the API startup call it).
-- Note for editing: statements are split on semicolons, so do not put semicolons inside comments or strings.

SET @missing := (SELECT COUNT(*) = 0 FROM information_schema.COLUMNS
                 WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'assessment' AND COLUMN_NAME = 'preferred_location');
SET @sql := IF(@missing, 'ALTER TABLE assessment ADD COLUMN preferred_location VARCHAR(100) NULL AFTER completed_at',
               'SELECT ''preferred_location already exists''');
PREPARE step FROM @sql;
EXECUTE step;
DEALLOCATE PREPARE step;

SET @missing := (SELECT COUNT(*) = 0 FROM information_schema.COLUMNS
                 WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'assessment' AND COLUMN_NAME = 'about_me');
SET @sql := IF(@missing, 'ALTER TABLE assessment ADD COLUMN about_me TEXT NULL AFTER preferred_location',
               'SELECT ''about_me already exists''');
PREPARE step FROM @sql;
EXECUTE step;
DEALLOCATE PREPARE step;

CREATE TABLE IF NOT EXISTS roadmap_progress (
    student_id INT UNSIGNED NOT NULL,
    career_id  INT UNSIGNED NOT NULL,
    step_key   VARCHAR(150) NOT NULL,
    done_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (student_id, career_id, step_key),
    KEY ix_roadmap_progress_career (career_id),
    CONSTRAINT fk_roadmap_progress_student FOREIGN KEY (student_id) REFERENCES student (student_id) ON DELETE CASCADE,
    CONSTRAINT fk_roadmap_progress_career  FOREIGN KEY (career_id)  REFERENCES career (career_id)   ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
