#!/usr/bin/env python3
"""
Import courses from wbs-courses-updated.csv into the bus_school.db database.
This script updates the courses table while preserving programs, specialties, 
and specialty_classes relationships.
"""

import csv
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "database_project", "bus_school.db")
CSV_PATH = os.path.join(os.path.dirname(__file__), "database_project", "wbs-courses-updated.csv")


def import_courses():
    """Import courses from CSV file into database"""
    
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at {DB_PATH}")
        return False
    
    if not os.path.exists(CSV_PATH):
        print(f"❌ CSV file not found at {CSV_PATH}")
        return False
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Count existing courses before import
        cursor.execute("SELECT COUNT(*) FROM courses")
        old_count = cursor.fetchone()[0]
        print(f"📊 Existing courses in database: {old_count}")
        
        # Read CSV and import courses
        imported = 0
        skipped = 0
        updated = 0
        
        with open(CSV_PATH, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            
            for row in reader:
                course_code = row.get('Course_Code', '').strip()
                
                if not course_code:
                    skipped += 1
                    continue
                
                # Parse credits (handle empty or non-numeric values)
                credits_str = row.get('Credits', '').strip()
                try:
                    credits = int(float(credits_str)) if credits_str else None
                except ValueError:
                    credits = None
                
                # Check if course already exists
                cursor.execute("SELECT course_code FROM courses WHERE course_code = ?", (course_code,))
                exists = cursor.fetchone()
                
                if exists:
                    # Update existing course
                    cursor.execute("""
                        UPDATE courses SET
                            Course_Title = ?,
                            Locations = ?,
                            Instructional_Format = ?,
                            Course_Description = ?,
                            Subject = ?,
                            Delivery_Mode = ?,
                            Academic_Level = ?,
                            Credits = ?,
                            Section_Details = ?,
                            Instructors = ?,
                            Offering_Period = ?,
                            Academic_Units = ?
                        WHERE course_code = ?
                    """, (
                        row.get('Course_Title', '').strip(),
                        row.get('Locations', '').strip(),
                        row.get('Instructional_Format', '').strip(),
                        row.get('Course_Description', '').strip(),
                        row.get('Subject', '').strip(),
                        row.get('Delivery_Mode', '').strip(),
                        row.get('Academic_Level', '').strip(),
                        credits,
                        row.get('Section_Details', '').strip(),
                        row.get('Instructors', '').strip(),
                        row.get('Offering_Period', '').strip(),
                        row.get('Academic_Units', '').strip(),
                        course_code
                    ))
                    updated += 1
                else:
                    # Insert new course
                    cursor.execute("""
                        INSERT INTO courses (
                            course_code, Course_Title, Locations, Instructional_Format,
                            Course_Description, Subject, Delivery_Mode, Academic_Level,
                            Credits, Section_Details, Instructors, Offering_Period, Academic_Units
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        course_code,
                        row.get('Course_Title', '').strip(),
                        row.get('Locations', '').strip(),
                        row.get('Instructional_Format', '').strip(),
                        row.get('Course_Description', '').strip(),
                        row.get('Subject', '').strip(),
                        row.get('Delivery_Mode', '').strip(),
                        row.get('Academic_Level', '').strip(),
                        credits,
                        row.get('Section_Details', '').strip(),
                        row.get('Instructors', '').strip(),
                        row.get('Offering_Period', '').strip(),
                        row.get('Academic_Units', '').strip()
                    ))
                    imported += 1
        
        conn.commit()
        
        # Count courses after import
        cursor.execute("SELECT COUNT(*) FROM courses")
        new_count = cursor.fetchone()[0]
        
        # Show subject breakdown
        cursor.execute("""
            SELECT Subject, COUNT(*) as count 
            FROM courses 
            GROUP BY Subject 
            ORDER BY count DESC
        """)
        subjects = cursor.fetchall()
        
        print(f"\n✅ Import completed successfully!")
        print(f"   - New courses inserted: {imported}")
        print(f"   - Existing courses updated: {updated}")
        print(f"   - Skipped (no course code): {skipped}")
        print(f"   - Total courses in database: {new_count}")
        print(f"\n📚 Courses by Subject:")
        for subject, count in subjects:
            print(f"   - {subject or 'Unknown'}: {count}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error during import: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def verify_data():
    """Verify database integrity after import"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("\n🔍 Verifying data integrity...")
    
    # Check programs
    cursor.execute("SELECT COUNT(*) FROM programs")
    programs = cursor.fetchone()[0]
    
    # Check specialties
    cursor.execute("SELECT COUNT(*) FROM specialties")
    specialties = cursor.fetchone()[0]
    
    # Check specialty_classes
    cursor.execute("SELECT COUNT(*) FROM specialty_classes")
    specialty_classes = cursor.fetchone()[0]
    
    # Check for orphaned specialty_classes (courses that don't exist)
    cursor.execute("""
        SELECT sc.course_code 
        FROM specialty_classes sc 
        LEFT JOIN courses c ON sc.course_code = c.course_code 
        WHERE c.course_code IS NULL
    """)
    orphaned = cursor.fetchall()
    
    print(f"   - Programs: {programs}")
    print(f"   - Specialties: {specialties}")
    print(f"   - Specialty-Course mappings: {specialty_classes}")
    
    if orphaned:
        print(f"   ⚠️  Orphaned course references: {[o[0] for o in orphaned]}")
    else:
        print(f"   ✅ No orphaned references")
    
    # Sample some courses
    cursor.execute("""
        SELECT course_code, Course_Title, Credits, Subject 
        FROM courses 
        LIMIT 5
    """)
    samples = cursor.fetchall()
    print(f"\n📋 Sample courses:")
    for code, title, credits, subject in samples:
        print(f"   - {code}: {title} ({credits} cr) [{subject}]")
    
    conn.close()


if __name__ == "__main__":
    print("🚀 Starting course import from CSV...")
    print(f"   Database: {DB_PATH}")
    print(f"   CSV File: {CSV_PATH}")
    print()
    
    success = import_courses()
    if success:
        verify_data()
