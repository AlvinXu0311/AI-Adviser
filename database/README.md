# Database

This directory contains the SQLite database and related scripts for the WPI Business School Adviser system.

## Directory Structure

```
database/
├── README.md                     # This file
├── import_courses_from_csv.py    # Script to import courses from CSV
└── database_project/
    ├── bus_school.db             # SQLite database (production)
    ├── wbs-courses-updated.csv   # Course data source (CSV)
    ├── setup_database.sql        # Database schema DDL
    ├── create_database.py        # Database initialization script
    ├── query_degree.py           # Visualization & query utilities
    ├── test_degree_query.py      # Query tests
    └── README.md                 # Database project documentation
```

## Database Schema

### Tables

1. **programs** - Academic degree programs
   - `id`: Primary key
   - `program_name`: Full program name (e.g., "Master of Science in Information Technology")
   - `program_code`: Short code (e.g., "MSIT")
   - `program_type`, `program_level`, `description`
   - `Requirements`: Credit requirements

2. **specialties** - Program specializations/concentrations
   - `id`: Primary key
   - `specialty_name`: Name of the specialty
   - `description`: Specialty description
   - `program_id`: FK to programs
   - `Requirements`: Credit requirements for specialty

3. **courses** - All WPI Business School courses
   - `course_code`: Primary key (e.g., "MIS 500")
   - `Course_Title`: Course name
   - `Course_Description`: Full course description
   - `Credits`: Credit hours
   - `Subject`: Department/Subject area
   - `Instructors`: Faculty teaching the course
   - `Locations`, `Delivery_Mode`, `Academic_Level`, etc.

4. **specialty_classes** - Junction table linking courses to specialties
   - `specialty_id`: FK to specialties
   - `course_code`: FK to courses
   - `is_required`: Boolean flag for required vs elective

## Current Data

- **Programs**: 3 (MSIT, MSBA, MSM)
- **Specialties**: 7
- **Courses**: 103 (imported from WPI catalog)

### Courses by Subject
- Operations and Industrial Engineering: 22
- Management Information Systems: 20
- Business: 13
- Finance: 10
- Marketing: 8
- Entrepreneurship: 6
- Organizational Behavior and Change: 5
- Accounting: 1

## Usage

### Import/Update Courses from CSV

```bash
cd /home/owner/Documents/AI-Adviser
python database/import_courses_from_csv.py
```

### Reset Database

```bash
cd /home/owner/Documents/AI-Adviser/database/database_project
python create_database.py
```

### Query Visualization

```bash
cd /home/owner/Documents/AI-Adviser/database/database_project
python query_degree.py
```

## Integration

The database is accessed by the backend via:
- **`backend/app/agents/tools.py`** - `business_school_database` tool for LangChain agent
- Direct SQLite queries for program, specialty, and course lookups
