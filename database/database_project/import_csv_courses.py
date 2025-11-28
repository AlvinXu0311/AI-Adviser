#!/usr/bin/env python3
"""
Script to import courses from wbs-courses-updated.csv into the database.
This will replace all existing courses with the CSV data.
"""

import sqlite3
import csv
import os

def import_courses():
    db_path = 'bus_school.db'
    csv_file = 'wbs-courses-updated.csv'
    
    if not os.path.exists(csv_file):
        print(f"❌ CSV file '{csv_file}' not found")
        return
    
    if not os.path.exists(db_path):
        print(f"❌ Database '{db_path}' not found. Run create_database.py first.")
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Count existing courses
        cursor.execute("SELECT COUNT(*) FROM courses")
        old_count = cursor.fetchone()[0]
        print(f"📊 Existing courses in database: {old_count}")
        
        # Clear existing courses
        cursor.execute("DELETE FROM courses")
        print("🗑️  Cleared existing courses")
        
        # Read and import CSV
        imported = 0
        skipped = 0
        seen_courses = set()  # Track unique course codes
        
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                course_code = row.get('Course_Code', '').strip()
                
                if not course_code:
                    skipped += 1
                    continue
                
                # Skip duplicate course codes (CSV has multiple sections)
                if course_code in seen_courses:
                    skipped += 1
                    continue
                
                seen_courses.add(course_code)
                
                # Parse credits (convert to integer)
                try:
                    credits = int(row.get('Credits', 0))
                except ValueError:
                    credits = 3  # Default
                
                cursor.execute("""
                    INSERT INTO courses (
                        course_code, Course_Title, Locations, Instructional_Format,
                        Course_Description, Subject, Delivery_Mode, Academic_Level,
                        Credits, Section_Details, Instructors, Offering_Period, Academic_Units
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    course_code,
                    row.get('Course_Title', ''),
                    row.get('Locations', ''),
                    row.get('Instructional_Format', ''),
                    row.get('Course_Description', ''),
                    row.get('Subject', ''),
                    row.get('Delivery_Mode', ''),
                    row.get('Academic_Level', ''),
                    credits,
                    row.get('Section_Details', ''),
                    row.get('Instructors', ''),
                    row.get('Offering_Period', ''),
                    row.get('Academic_Units', '')
                ))
                imported += 1
        
        conn.commit()
        
        # Verify import
        cursor.execute("SELECT COUNT(*) FROM courses")
        new_count = cursor.fetchone()[0]
        
        print(f"✅ Import complete!")
        print(f"   - Imported: {imported} unique courses")
        print(f"   - Skipped: {skipped} duplicate sections")
        print(f"   - Total in database: {new_count}")
        
        # Show sample of imported courses
        print("\n📋 Sample imported courses:")
        cursor.execute("SELECT course_code, Course_Title, Subject, Academic_Level FROM courses LIMIT 10")
        for row in cursor.fetchall():
            print(f"   {row[0]}: {row[1][:50]}... ({row[2]}, {row[3]})")
        
    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    import_courses()
