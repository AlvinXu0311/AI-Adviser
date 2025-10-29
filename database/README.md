# Database

This directory contains database-related files and configurations for the MIS520 project.

## Directory Structure

```
database/
├── README.md                # This file
├── models/                  # Database model definitions
│   ├── __init__.py         # Models package
│   ├── student.py          # Student model
│   ├── course.py           # Course model
│   └── transcript.py       # Transcript model
├── migrations/              # Database migration scripts
│   ├── 001_initial.sql     # Initial schema
│   └── 002_add_indexes.sql # Add indexes
├── backups/                 # Database backups (gitignored)
│   └── .gitkeep            # Keep directory in git
├── data/                    # Data files (gitignored)
│   ├── .gitkeep            # Keep directory in git
│   └── sample_data.sql     # Sample data for development
└── scripts/                 # Utility scripts
    ├── init_db.py          # Initialize database
    ├── backup_db.sh        # Backup script
    └── restore_db.sh       # Restore script
```

## Database Technologies

### Current Setup
- **SQLite** - Development and testing
- **In-memory storage** - Temporary transcript caching

### Future Options
- **PostgreSQL** - Production deployment
- **MySQL** - Alternative production option
- **MongoDB** - For document storage (transcripts, PDFs)

## Models

### Student
- student_id (PK)
- name
- email
- program
- enrollment_date
- status

### Course
- course_id (PK)
- code
- name
- credits
- description
- program_id

### Transcript
- transcript_id (PK)
- student_id (FK)
- upload_date
- file_path
- parsed_data (JSON)
- gpa
- total_credits

## Usage

### Initialize Database

```bash
cd /home/owner/Documents/MIS520
python database/scripts/init_db.py
```

### Run Migrations

```bash
python database/scripts/migrate.py
```

### Backup Database

```bash
bash database/scripts/backup_db.sh
```

## Configuration

Database connection settings are stored in:
- `backend/.env` - Connection strings and credentials
- `backend/app/config/database.py` - SQLAlchemy configuration

## Related Files

- [backend/app/schemas/](../backend/app/schemas/) - Pydantic schemas
- [backend/app/services/context_manager.py](../backend/app/services/context_manager.py) - Current caching system

## Migration Path

Current state: In-memory caching with SQLAlchemy setup
Future state: Persistent database with proper models and migrations

## Security

- Database credentials stored in `.env` (gitignored)
- Backup files are gitignored
- Use parameterized queries to prevent SQL injection
- Implement proper access control and authentication
