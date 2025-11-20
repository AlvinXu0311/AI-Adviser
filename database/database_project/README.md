# WPI Business School Database Guide

## Database Overview

This database manages the WPI Business School's academic programs, specialties, and courses. It provides a flexible structure to track program requirements, specialty courses, and student progress.

## Database Structure

### Tables

#### 1. **programs**
Stores graduate and undergraduate programs offered by the business school.

**Fields:**
- `id` - Primary key (auto-generated unique identifier)
- `program_name` - Name of the program (e.g., "MBA", "MS in Business Analytics")
- `program_code` - Unique program code (e.g., "MBA-001", "MSBA-001") - different from the ID
- `program_type` - Type of program (e.g., "MBA", "MSC", "DBA", "BSC")
- `program_level` - Academic level (Graduate, Undergraduate)
- `description` - Program description
- `Requirements` - **Number of OPTIONAL specialties required**

#### 2. **specialties**
Stores specializations within each program. Each specialty belongs to one program.

**Fields:**
- `id` - Primary key
- `specialty_name` - Name of the specialty
- `description` - Specialty description
- `program_id` - Foreign key to programs table
- `Requirements` - **Number of OPTIONAL courses required for this specialty**

#### 3. **courses**
Stores all available courses.

**Fields:**
- `course_code` - **Primary key** - Unique course code (e.g., "BUS-501", "MKT-601")
- `Course_Title` - Full course title (without course code)
- `Locations` - Where the course is offered
- `Instructional_Format` - Format of instruction
- `Course_Description` - Detailed course description
- `Subject` - Course subject code
- `Delivery_Mode` - How the course is delivered
- `Academic_Level` - Academic level
- `Credits` - Number of credits
- `Section_Details` - Section information
- `Instructors` - Course instructors
- `Offering_Period` - When the course is offered
- `Academic_Units` - Academic units offering the course

#### 4. **specialty_classes**
Junction table linking courses to specialties with requirement status.

**Fields:**
- `id` - Primary key
- `specialty_id` - Foreign key to specialties table
- `course_code` - Foreign key to courses table (references course_code)
- `is_required` - Boolean flag (1 = required, 0 = optional)

## Understanding Requirements

### ⚠️ IMPORTANT: How Requirements Work

#### Program Requirements Field

The `Requirements` field in the **programs** table indicates **how many OPTIONAL specialties** a student must complete.

**Key Points:**
- This field ONLY counts optional specialties
- **Required courses must be grouped into a specialty with the same name as the program**
- Example: For "MBA" program, create a specialty called "MBA" containing all required core courses
- The Requirements field tells students how many additional (optional) specialties they must choose

**Example Structure:**
```
Program: MBA (Requirements = 1)
├── Specialty: MBA [Required - same name as program]
│   ├── Required Course 1
│   ├── Required Course 2
│   └── Required Course 3
├── Specialty: Finance [Optional]
│   ├── Required Course A
│   └── Optional Course B
├── Specialty: Marketing [Optional]
│   ├── Required Course X
│   └── Optional Course Y
└── Specialty: Operations [Optional]
    ├── Required Course M
    └── Optional Course N

Student must complete:
1. ALL courses in "MBA" specialty (required core)
2. ONE additional specialty (Finance, Marketing, or Operations)
```

#### Specialty Requirements Field

The `Requirements` field in the **specialties** table indicates **how many OPTIONAL courses** must be completed within that specialty.

**Key Points:**
- All courses marked as `is_required = 1` in specialty_classes are mandatory
- The Requirements field specifies how many additional courses from `is_required = 0` must be taken
- This allows flexible elective requirements within specialties

**Example:**
```
Specialty: Finance (Requirements = 2)
├── Required Courses (is_required = 1)
│   ├── Financial Accounting
│   └── Corporate Finance
└── Optional Courses (is_required = 0)
    ├── Investment Analysis
    ├── Risk Management
    └── Financial Modeling

Student must complete:
1. BOTH required courses (Financial Accounting + Corporate Finance)
2. TWO optional courses from the three available
```

## Database Relationships

```
programs (1) ──→ (many) specialties
                           │
                           │ (many)
                           ↓
                    specialty_classes
                           │
                           │ (many)
                           ↓
                        courses
```

## Setup Instructions

### 1. Create the Database

Run the setup script to create and populate the database:

```bash
python create_database.py
```

This will:
- Create the database file `wpi_bus_school.db`
- Set up all tables with proper relationships
- Insert sample programs and specialties
- Create indexes for performance

### 2. Populate with Course Data

Import course data from the wbs-courses.csv file:

```bash
python import_courses.py
```

### 3. Link Courses to Specialties

After importing courses, you need to:
1. Create a specialty with the same name as each program for required core courses
2. Link required core courses to the program-named specialty with `is_required = 1`
3. Link specialty-specific courses with appropriate `is_required` flags
4. Update the `Requirements` field for each specialty based on elective needs

## Using the Query Script

### View Program Information

```bash
python query_degree.py "MBA"
```

### Interactive Mode

```bash
python query_degree.py
```

Options:
1. **Detailed information** - View all specialties and courses for a program
2. **Structure visualization** - Generate interactive tree diagram
3. **Course comparison** - Check your progress against program requirements
4. **Both** - Detailed info + visualization

### Course Comparison Feature

Track student progress and identify missing requirements:

```bash
python query_degree.py
# Choose option 3
# Enter program name
# Enter completed course subjects
```

The comparison tool will:
- Check completion status for each specialty
- Identify missing required courses
- Show optional course options
- Calculate overall program progress

## Example Queries

### SQL Examples

**Get all specialties for a program:**
```sql
SELECT s.specialty_name, s.Requirements, s.description
FROM specialties s
JOIN programs p ON s.program_id = p.id
WHERE p.program_name = 'MBA';
```

**Get required courses for a specialty:**
```sql
SELECT c.Subject, c.Course_Title, c.Credits
FROM courses c
JOIN specialty_classes sc ON c.course_code = sc.course_code
JOIN specialties s ON sc.specialty_id = s.id
WHERE s.specialty_name = 'Finance' AND sc.is_required = 1;
```

**Get optional courses for a specialty:**
```sql
SELECT c.Subject, c.Course_Title, c.Credits
FROM courses c
JOIN specialty_classes sc ON c.course_code = sc.course_code
JOIN specialties s ON sc.specialty_id = s.id
WHERE s.specialty_name = 'Finance' AND sc.is_required = 0;
```

**Check program requirements:**
```sql
SELECT 
    p.program_name,
    p.Requirements as optional_specialties_required,
    COUNT(s.id) as total_specialties_available
FROM programs p
LEFT JOIN specialties s ON p.id = s.program_id
WHERE p.program_name = 'MBA'
GROUP BY p.id;
```

## Best Practices

### 1. Organizing Core Requirements
- Always create a specialty with the same name as the program
- This specialty should contain ALL required core courses
- Mark all core courses with `is_required = 1`
- Set this specialty's `Requirements` field to 0 (no optional courses needed)

### 2. Setting Program Requirements
- Count only the optional specialties
- Don't include the core program specialty in the count
- Example: If students need core + 2 additional specialties, set Requirements = 2

### 3. Setting Specialty Requirements
- Count only optional courses needed
- All required courses are already enforced by `is_required = 1`
- Example: If specialty needs 3 required + 2 electives, set Requirements = 2

### 4. Maintaining Data Integrity
- Keep specialty names unique within each program
- Ensure course subjects match exactly when linking
- Use consistent naming conventions
- Regularly validate Requirements fields against actual course counts

## File Structure

```
WPI_bus_school/
├── bus_school.db              # SQLite database file
├── wpi_bus_school.db          # Alternative database name
├── setup_database.sql         # Database schema and sample data
├── create_database.py         # Database creation script
├── query_degree.py            # Query and visualization tool
├── wbs-courses.csv            # Course data source
└── README.md                  # This file
```

## Support and Maintenance

### Adding New Programs
1. Insert into programs table with appropriate Requirements value
2. Create core specialty with same name as program
3. Add optional specialties as needed
4. Link courses via specialty_classes table

### Adding New Courses
1. Import course data into courses table
2. Link to appropriate specialties via specialty_classes
3. Set `is_required` flag appropriately

### Updating Requirements
- Programs: Update when changing number of optional specialties needed
- Specialties: Update when changing number of optional courses needed

## Questions?

For issues or questions about the database structure, refer to the schema in `setup_database.sql` or examine the query examples in `query_degree.py`.
