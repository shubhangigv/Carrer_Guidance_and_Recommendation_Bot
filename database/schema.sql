-- Pathfinder: MySQL schema (13 tables from the ER diagram).
--
-- How to run (MySQL Workbench or the mysql command line):
--   1. CREATE DATABASE career_guidance CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
--   2. USE career_guidance;
--   3. Run this whole file.
-- scripts/load_onet_to_mysql.py also runs this file automatically before loading.
--
-- Every statement uses CREATE TABLE IF NOT EXISTS, so running the file again is safe.
-- Tables are created parents first, so every foreign key points to a table that exists.
-- Note for editing: statements are split on semicolons, so do not put semicolons inside comments.

-- ------------------------------------------------------------ students and assessments
CREATE TABLE IF NOT EXISTS student (
    student_id      INT UNSIGNED NOT NULL AUTO_INCREMENT,
    name            VARCHAR(100) NOT NULL,
    email           VARCHAR(255) NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,          -- bcrypt hash, never the password itself
    education_level VARCHAR(50)  NULL,
    degree          VARCHAR(100) NULL,
    year_of_study   TINYINT UNSIGNED NULL,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (student_id),
    UNIQUE KEY uq_student_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------ careers and their attributes
CREATE TABLE IF NOT EXISTS career (
    career_id   INT UNSIGNED NOT NULL AUTO_INCREMENT,
    onet_code   VARCHAR(10)  NOT NULL,              -- e.g. 15-2051.00
    title       VARCHAR(255) NOT NULL,
    description TEXT NULL,
    domain      VARCHAR(100) NULL,                  -- SOC major group, e.g. Healthcare Practitioners
    job_zone    TINYINT UNSIGNED NULL,              -- 1 (little preparation) to 5 (extensive)
    source      VARCHAR(50)  NOT NULL DEFAULT 'O*NET 31.0',
    PRIMARY KEY (career_id),
    UNIQUE KEY uq_career_onet_code (onet_code),
    KEY ix_career_title (title)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS skill (
    skill_id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    name     VARCHAR(100) NOT NULL,                 -- O*NET element name, e.g. Critical Thinking
    category VARCHAR(20)  NOT NULL,                 -- essential or transferable
    PRIMARY KEY (skill_id),
    UNIQUE KEY uq_skill_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS interest (
    interest_id TINYINT UNSIGNED NOT NULL AUTO_INCREMENT,
    name        VARCHAR(20) NOT NULL,               -- RIASEC type, e.g. Investigative
    PRIMARY KEY (interest_id),
    UNIQUE KEY uq_interest_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS knowledge (
    knowledge_id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    name         VARCHAR(100) NOT NULL,             -- O*NET knowledge area, e.g. Biology
    PRIMARY KEY (knowledge_id),
    UNIQUE KEY uq_knowledge_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------ link tables (many-to-many)
-- The primary key is the pair of ids, so one career cannot have the same skill twice.
CREATE TABLE IF NOT EXISTS career_skill (
    career_id      INT UNSIGNED NOT NULL,
    skill_id       INT UNSIGNED NOT NULL,
    importance     DECIMAL(5,2) NULL,               -- O*NET IM scale, 1-5
    required_level DECIMAL(5,2) NULL,               -- O*NET LV scale, 0-7
    PRIMARY KEY (career_id, skill_id),
    KEY ix_career_skill_skill (skill_id),
    CONSTRAINT fk_career_skill_career FOREIGN KEY (career_id) REFERENCES career (career_id) ON DELETE CASCADE,
    CONSTRAINT fk_career_skill_skill  FOREIGN KEY (skill_id)  REFERENCES skill (skill_id)   ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS career_interest (
    career_id   INT UNSIGNED NOT NULL,
    interest_id TINYINT UNSIGNED NOT NULL,
    score       DECIMAL(5,2) NULL,                  -- O*NET OI scale, 1-7
    PRIMARY KEY (career_id, interest_id),
    KEY ix_career_interest_interest (interest_id),
    CONSTRAINT fk_career_interest_career   FOREIGN KEY (career_id)   REFERENCES career (career_id)     ON DELETE CASCADE,
    CONSTRAINT fk_career_interest_interest FOREIGN KEY (interest_id) REFERENCES interest (interest_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS career_knowledge (
    career_id    INT UNSIGNED NOT NULL,
    knowledge_id INT UNSIGNED NOT NULL,
    importance   DECIMAL(5,2) NULL,                 -- O*NET IM scale, 1-5
    level        DECIMAL(5,2) NULL,                 -- O*NET LV scale, 0-7
    PRIMARY KEY (career_id, knowledge_id),
    KEY ix_career_knowledge_knowledge (knowledge_id),
    CONSTRAINT fk_career_knowledge_career    FOREIGN KEY (career_id)    REFERENCES career (career_id)       ON DELETE CASCADE,
    CONSTRAINT fk_career_knowledge_knowledge FOREIGN KEY (knowledge_id) REFERENCES knowledge (knowledge_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------ assessments and results
CREATE TABLE IF NOT EXISTS assessment (
    assessment_id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    student_id    INT UNSIGNED NOT NULL,
    completed_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    preferred_location VARCHAR(100) NULL,          -- e.g. Pune, used for job-search links (migration 003)
    about_me      TEXT NULL,                       -- optional free text, used by the semantic matcher
    profile_json  TEXT NULL,                       -- areas, course, strengths ... as JSON (migration 004)
    PRIMARY KEY (assessment_id),
    KEY ix_assessment_student (student_id),
    CONSTRAINT fk_assessment_student FOREIGN KEY (student_id) REFERENCES student (student_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- One row per answer, e.g. (7, 'skill', 'Programming', 4, 'rated').
-- A student can also answer 'No experience' / 'Not studied' / 'Cannot assess' instead of a number:
-- then rating is NULL and answer_status says which. (Existing database: run migrations/002_answer_status.sql)
CREATE TABLE IF NOT EXISTS assessment_rating (
    assessment_id INT UNSIGNED NOT NULL,
    category      VARCHAR(20)  NOT NULL,            -- interest, skill or subject
    item          VARCHAR(100) NOT NULL,            -- questionnaire item, e.g. Programming
    rating        TINYINT UNSIGNED NULL,            -- 1-5, NULL when answer_status is not 'rated'
    answer_status ENUM('rated','no_experience','not_studied','cant_assess') NOT NULL DEFAULT 'rated',
    PRIMARY KEY (assessment_id, category, item),
    CONSTRAINT ck_assessment_rating_range CHECK (rating BETWEEN 1 AND 5),
    CONSTRAINT ck_assessment_rating_status CHECK ((answer_status = 'rated') = (rating IS NOT NULL)),
    CONSTRAINT fk_assessment_rating_assessment FOREIGN KEY (assessment_id) REFERENCES assessment (assessment_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS recommendation (
    rec_id        INT UNSIGNED NOT NULL AUTO_INCREMENT,
    student_id    INT UNSIGNED NOT NULL,
    career_id     INT UNSIGNED NOT NULL,
    assessment_id INT UNSIGNED NOT NULL,
    match_score   DECIMAL(5,2) NOT NULL,            -- 0-100 Profile Match Score
    reasons       TEXT NULL,                        -- the explanation shown to the student (JSON list)
    model_version VARCHAR(50) NOT NULL,             -- e.g. baseline-v1, so results stay comparable
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (rec_id),
    KEY ix_recommendation_student (student_id),
    CONSTRAINT fk_recommendation_student    FOREIGN KEY (student_id)    REFERENCES student (student_id)       ON DELETE CASCADE,
    CONSTRAINT fk_recommendation_career     FOREIGN KEY (career_id)     REFERENCES career (career_id),
    CONSTRAINT fk_recommendation_assessment FOREIGN KEY (assessment_id) REFERENCES assessment (assessment_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------ later phases (empty for now)
CREATE TABLE IF NOT EXISTS course (
    course_id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    skill_id  INT UNSIGNED NOT NULL,
    title     VARCHAR(255) NOT NULL,
    provider  VARCHAR(100) NULL,
    url       VARCHAR(500) NOT NULL,                -- verified by hand before inserting
    PRIMARY KEY (course_id),
    KEY ix_course_skill (skill_id),
    CONSTRAINT fk_course_skill FOREIGN KEY (skill_id) REFERENCES skill (skill_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS job (
    job_id     INT UNSIGNED NOT NULL AUTO_INCREMENT,
    career_id  INT UNSIGNED NOT NULL,
    title      VARCHAR(255) NOT NULL,
    company    VARCHAR(255) NULL,
    location   VARCHAR(255) NULL,
    posted_on  DATE NULL,
    source_url VARCHAR(500) NULL,
    PRIMARY KEY (job_id),
    KEY ix_job_career (career_id),
    CONSTRAINT fk_job_career FOREIGN KEY (career_id) REFERENCES career (career_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Roadmap progress: one row per finished step (migration 003).
CREATE TABLE IF NOT EXISTS roadmap_progress (
    student_id INT UNSIGNED NOT NULL,
    career_id  INT UNSIGNED NOT NULL,
    step_key   VARCHAR(150) NOT NULL,               -- e.g. education, build:Programming
    done_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (student_id, career_id, step_key),
    KEY ix_roadmap_progress_career (career_id),
    CONSTRAINT fk_roadmap_progress_student FOREIGN KEY (student_id) REFERENCES student (student_id) ON DELETE CASCADE,
    CONSTRAINT fk_roadmap_progress_career  FOREIGN KEY (career_id)  REFERENCES career (career_id)   ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- "Not for me": careers a student hid from their matches (migration 004).
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

-- Students rate their own matches 1-5, for the user test (migration 005).
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
