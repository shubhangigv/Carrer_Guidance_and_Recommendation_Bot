-- Migration 005: students rate their own matches ("Would you consider this career?" 1-5).
--
-- Used for the user test (experiments/user_test.py): the rank and group the career had when it was
-- rated are stored, so ratings can be compared by position (1-10) and by group (your areas / also consider).
-- One row per student, assessment and career; rating again replaces the old rating.
--
-- Only needed for a database created BEFORE this change (new databases get it from schema.sql).
-- Safe to run again. Applied automatically by backend.db.update_schema().
-- Note for editing: statements are split on semicolons, so do not put semicolons inside comments or strings.

CREATE TABLE IF NOT EXISTS career_rating (
    student_id    INT UNSIGNED NOT NULL,
    assessment_id INT UNSIGNED NOT NULL,
    career_id     INT UNSIGNED NOT NULL,
    rating        TINYINT UNSIGNED NOT NULL,
    shown_rank    TINYINT UNSIGNED NOT NULL,
    shown_group   ENUM('your_areas', 'also_consider', 'all') NOT NULL,
    model_version VARCHAR(20) NOT NULL,
    rated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (student_id, assessment_id, career_id),
    KEY ix_career_rating_career (career_id),
    CONSTRAINT ck_career_rating_range CHECK (rating BETWEEN 1 AND 5),
    CONSTRAINT fk_career_rating_student    FOREIGN KEY (student_id)    REFERENCES student (student_id)       ON DELETE CASCADE,
    CONSTRAINT fk_career_rating_assessment FOREIGN KEY (assessment_id) REFERENCES assessment (assessment_id) ON DELETE CASCADE,
    CONSTRAINT fk_career_rating_career     FOREIGN KEY (career_id)     REFERENCES career (career_id)         ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
