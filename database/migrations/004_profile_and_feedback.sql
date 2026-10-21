-- Migration 004: the new quiz answers, and "not for me" feedback on careers.
--
-- Changes:
--   * assessment.profile_json  the extra quiz answers as JSON text: areas, course, strengths, weaknesses,
--                              work_setting, further_study (checked by ml/preferences.clean_profile)
--   * new table career_feedback  careers a student marked "not for me" (hidden from their matches)
--
-- Only needed for a database created BEFORE this change (new databases get it from schema.sql).
-- Safe to run again: each step first looks in information_schema. Applied automatically by
-- backend.db.update_schema() (the loader and the API startup call it).
-- Note for editing: statements are split on semicolons, so do not put semicolons inside comments or strings.

SET @missing := (SELECT COUNT(*) = 0 FROM information_schema.COLUMNS
                 WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'assessment' AND COLUMN_NAME = 'profile_json');
SET @sql := IF(@missing, 'ALTER TABLE assessment ADD COLUMN profile_json TEXT NULL AFTER about_me',
               'SELECT ''profile_json already exists''');
PREPARE step FROM @sql;
EXECUTE step;
DEALLOCATE PREPARE step;

CREATE TABLE IF NOT EXISTS career_feedback (
    student_id INT UNSIGNED NOT NULL,
    career_id  INT UNSIGNED NOT NULL,
    verdict    ENUM('not_for_me') NOT NULL DEFAULT 'not_for_me',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (student_id, career_id),
    KEY ix_career_feedback_career (career_id),
    CONSTRAINT fk_career_feedback_student FOREIGN KEY (student_id) REFERENCES student (student_id) ON DELETE CASCADE,
    CONSTRAINT fk_career_feedback_career  FOREIGN KEY (career_id)  REFERENCES career (career_id)   ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
