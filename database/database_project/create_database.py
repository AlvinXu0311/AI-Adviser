#!/usr/bin/env python3
"""
Script to create and populate the WPI Bus School database
"""

import sqlite3
import os

def create_database():
    # Database file path
    db_path = 'bus_school.db'
    sql_file = 'setup_database.sql'
    
    try:
        # Connect to database (creates if doesn't exist)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Read and execute SQL file
        with open(sql_file, 'r') as file:
            sql_script = file.read()
            cursor.executescript(sql_script)
        
        # Commit changes
        conn.commit()
        print(f"✅ Database '{db_path}' created successfully!")
        
        # Verify tables were created
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print(f"📋 Created tables: {[table[0] for table in tables]}")
        
        # Show sample data count
        cursor.execute("SELECT COUNT(*) FROM courses")
        course_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM programs")
        program_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM specialties")
        specialty_count = cursor.fetchone()[0]
        
        print(f"📊 Initial data inserted:")
        print(f"   - Programs: {program_count}")
        print(f"   - Specialties: {specialty_count}")
        print(f"   - Courses: {course_count}")
        print()
        print("📝 Next steps:")
        print("   1. Import course data")
        print("   2. Create core specialty for each program (same name as program)")
        print("   3. Link courses to specialties via specialty_classes table")
        print("   4. Set is_required flag appropriately for each course")
        
    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
    except FileNotFoundError:
        print(f"❌ SQL file '{sql_file}' not found")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    create_database()