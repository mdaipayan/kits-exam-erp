-- 1. Table for Course Schemes
-- Stores the rules (Max Marks and Credits) for each subject.
CREATE TABLE subjects (
    code VARCHAR(20) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    course_type VARCHAR(20) CHECK (course_type IN ('Theory', 'Practical')),
    cie_max REAL DEFAULT 20, -- Continuous Internal Evaluation
    ise_max REAL DEFAULT 20, -- Internal Semester Examination
    ese_max REAL DEFAULT 60, -- End Semester Examination
    credits INTEGER DEFAULT 3
);

-- 2. Table for Faculty Assignments
-- Links designated faculty IDs to specific subject codes.
CREATE TABLE assignments (
    faculty_id VARCHAR(50),
    subject_code VARCHAR(20) REFERENCES subjects(code),
    role VARCHAR(20) CHECK (role IN ('Faculty', 'Deputy COE')),
    PRIMARY KEY (faculty_id, subject_code)
);

-- 3. Unified Master Marks Table
-- This table stores all components. Different roles will update different columns.
CREATE TABLE marks_master (
    student_id VARCHAR(50),
    subject_code VARCHAR(20) REFERENCES subjects(code),
    cie_marks REAL DEFAULT 0,
    ise_marks REAL DEFAULT 0,
    ese_marks VARCHAR(10) DEFAULT '0', -- VARCHAR to handle 'AB' (Absent)
    attendance REAL DEFAULT 0,
    is_locked BOOLEAN DEFAULT FALSE,  -- To prevent editing after final submission
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (student_id, subject_code)
);

-- 4. Sample Subjects for Civil Engineering (KITS Ramtek)
-- This pre-fills your database so the app has data to show immediately.
INSERT INTO subjects (code, name, course_type, cie_max, ise_max, ese_max, credits) VALUES
('CE101', 'Structural Analysis-I', 'Theory', 20, 20, 60, 4),
('CE102', 'Fluid Mechanics', 'Theory', 20, 20, 60, 4),
('CE103', 'Concrete Technology', 'Theory', 20, 20, 60, 3),
('CE104', 'Fluid Mechanics Lab', 'Practical', 0, 25, 25, 1),
('CE105', 'Concrete Lab', 'Practical', 0, 25, 25, 1);
