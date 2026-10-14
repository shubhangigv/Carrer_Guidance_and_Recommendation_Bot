-- Migration 002: let a student answer "No experience", "Not studied" or "Can't assess".
--
-- Changes assessment_rating:
--   * rating becomes NULL-able (NULL when there is no number)
--   * new column answer_status: rated / no_experience / not_studied / cant_assess
--   * new check: a number is given exactly when answer_status = 'rated'
--
-- Only needed for a database created BEFORE this change (new databases get it from schema.sql).
-- Safe to run again: each step first looks in information_schema and only changes what is missing.
-- Works on MySQL 8.0.16+ and MariaDB 10.2+.
--
-- Run in MySQL Workbench (USE career_guidance first), or from PowerShell:
--   python -c "from backend.db import get_engine, run_sql_file; run_sql_file(get_engine(), 'database/migrations/002_answer_status.sql')"
-- Note for editing: statements are split on semicolons, so do not put semicolons inside comments or strings.

-- 1. rating may now be NULL (running this twice changes nothing)
ALTER TABLE assessment_rating MODIFY rating TINYINT UNSIGNED NULL;

-- 2. add answer_status if it is not there yet (existing rows become 'rated')
SET @missing := (SELECT COUNT(*) = 0 FROM information_schema.COLUMNS
                 WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'assessment_rating'
                   AND COLUMN_NAME = 'answer_status');
SET @sql := IF(@missing,
    'ALTER TABLE assessment_rating ADD COLUMN answer_status ENUM(''rated'',''no_experience'',''not_studied'',''cant_assess'') NOT NULL DEFAULT ''rated'' AFTER rating',
    'SELECT ''answer_status already exists''');
PREPARE step FROM @sql;
EXECUTE step;
DEALLOCATE PREPARE step;

-- 3. add the rating/status check if it is not there yet
SET @missing := (SELECT COUNT(*) = 0 FROM information_schema.TABLE_CONSTRAINTS
                 WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = 'assessment_rating'
                   AND CONSTRAINT_NAME = 'ck_assessment_rating_status');
SET @sql := IF(@missing,
    'ALTER TABLE assessment_rating ADD CONSTRAINT ck_assessment_rating_status CHECK ((answer_status = ''rated'') = (rating IS NOT NULL))',
    'SELECT ''ck_assessment_rating_status already exists''');
PREPARE step FROM @sql;
EXECUTE step;
DEALLOCATE PREPARE step;
