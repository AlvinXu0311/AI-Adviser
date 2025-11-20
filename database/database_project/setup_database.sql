-- Drop existing tables if they exist
DROP TABLE IF EXISTS specialty_classes;
DROP TABLE IF EXISTS specialties;
DROP TABLE IF EXISTS courses;
DROP TABLE IF EXISTS programs;

-- Create programs table with Requirements field
CREATE TABLE programs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    program_name TEXT NOT NULL UNIQUE,
    program_code TEXT UNIQUE,
    program_type TEXT,
    program_level TEXT,
    description TEXT,
    Requirements INTEGER DEFAULT 0
);

-- Create specialties table (each specialty belongs to one program)
CREATE TABLE specialties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    specialty_name TEXT NOT NULL,
    description TEXT,
    program_id INTEGER NOT NULL,
    Requirements INTEGER DEFAULT 0,
    FOREIGN KEY (program_id) REFERENCES programs(id) ON DELETE CASCADE,
    UNIQUE(specialty_name, program_id)
);

-- Create courses table with structure matching wbs-courses.csv
CREATE TABLE courses (
    course_code TEXT PRIMARY KEY,
    Course_Title TEXT NOT NULL,
    Locations TEXT,
    Instructional_Format TEXT,
    Course_Description TEXT,
    Subject TEXT,
    Delivery_Mode TEXT,
    Academic_Level TEXT,
    Credits INTEGER,
    Section_Details TEXT,
    Instructors TEXT,
    Offering_Period TEXT,
    Academic_Units TEXT
);

-- Create specialty_classes junction table (links courses to specialties with required flag)
CREATE TABLE specialty_classes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    specialty_id INTEGER NOT NULL,
    course_code TEXT NOT NULL,
    is_required BOOLEAN NOT NULL DEFAULT 0,
    FOREIGN KEY (specialty_id) REFERENCES specialties(id) ON DELETE CASCADE,
    FOREIGN KEY (course_code) REFERENCES courses(course_code) ON DELETE CASCADE,
    UNIQUE(specialty_id, course_code)
);

-- Create indexes for better query performance
CREATE INDEX idx_courses_subject ON courses(Subject);
CREATE INDEX idx_courses_academic_level ON courses(Academic_Level);
CREATE INDEX idx_courses_delivery_mode ON courses(Delivery_Mode);
CREATE INDEX idx_specialties_program_id ON specialties(program_id);
CREATE INDEX idx_specialty_classes_specialty_id ON specialty_classes(specialty_id);
CREATE INDEX idx_specialty_classes_course_code ON specialty_classes(course_code);
CREATE INDEX idx_specialty_classes_required ON specialty_classes(is_required);
