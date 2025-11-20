import sqlite3
import sys
import os

# Add the parent directory to the system path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from query_degree import (
    connect_database, 
    query_degree_info, 
    display_degree_info,
    compare_courses_for_degree,
    display_course_comparison
)

def test_database_structure():
    """Test if the database has the expected structure"""
    print("🔍 Testing Database Structure...")
    print("=" * 50)
    
    conn = connect_database()
    if not conn:
        print("❌ Failed to connect to database")
        return False
    
    cursor = conn.cursor()
    
    # Check if required tables exist
    tables = ['programs', 'specialties', 'courses', 'specialty_courses']
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    existing_tables = [table[0] for table in cursor.fetchall()]
    
    print("Checking tables:")
    all_tables_exist = True
    for table in tables:
        if table in existing_tables:
            print(f"  ✅ {table} - exists")
        else:
            print(f"  ❌ {table} - missing")
            all_tables_exist = False
    
    if not all_tables_exist:
        print("\n⚠️  Some required tables are missing")
        conn.close()
        return False
    
    # Check table structures
    print("\nTable Structures:")
    
    # Programs table
    cursor.execute("PRAGMA table_info(programs)")
    programs_columns = [col[1] for col in cursor.fetchall()]
    print(f"  programs: {', '.join(programs_columns)}")
    
    # Specialties table
    cursor.execute("PRAGMA table_info(specialties)")
    specialties_columns = [col[1] for col in cursor.fetchall()]
    print(f"  specialties: {', '.join(specialties_columns)}")
    
    # Courses table
    cursor.execute("PRAGMA table_info(courses)")
    courses_columns = [col[1] for col in cursor.fetchall()]
    print(f"  courses: {', '.join(courses_columns)}")
    
    # Specialty_courses table
    cursor.execute("PRAGMA table_info(specialty_courses)")
    specialty_courses_columns = [col[1] for col in cursor.fetchall()]
    print(f"  specialty_courses: {', '.join(specialty_courses_columns)}")
    
    # Check record counts
    print("\nRecord Counts:")
    cursor.execute("SELECT COUNT(*) FROM programs")
    program_count = cursor.fetchone()[0]
    print(f"  Programs: {program_count}")
    
    cursor.execute("SELECT COUNT(*) FROM specialties")
    specialty_count = cursor.fetchone()[0]
    print(f"  Specialties: {specialty_count}")
    
    cursor.execute("SELECT COUNT(*) FROM courses")
    course_count = cursor.fetchone()[0]
    print(f"  Courses: {course_count}")
    
    cursor.execute("SELECT COUNT(*) FROM specialty_courses")
    specialty_courses_count = cursor.fetchone()[0]
    print(f"  Specialty-Course relationships: {specialty_courses_count}")
    
    conn.close()
    print("\n✅ Database structure test complete")
    return True

def test_query_specific_program():
    """Test querying a specific program"""
    print("\n🔍 Testing Query for Specific Program...")
    print("=" * 50)
    
    # Get a sample program
    conn = connect_database()
    cursor = conn.cursor()
    cursor.execute("SELECT program_name FROM programs LIMIT 1")
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        print("❌ No programs found in database")
        return False
    
    test_program = result[0]
    print(f"Testing with program: {test_program}")
    print()
    
    results = query_degree_info(test_program)
    
    if results:
        print("✅ Query successful")
        display_degree_info(results, test_program)
        return True
    else:
        print("❌ Query failed")
        return False

def test_relationships():
    """Test that relationships between tables are working correctly"""
    print("\n🔍 Testing Table Relationships...")
    print("=" * 50)
    
    conn = connect_database()
    cursor = conn.cursor()
    
    # Test program-specialty relationship
    query = """
    SELECT p.program_name, COUNT(DISTINCT s.specialty_id) as specialty_count
    FROM programs p
    LEFT JOIN specialties s ON p.program_id = s.program_id
    GROUP BY p.program_id, p.program_name
    """
    
    cursor.execute(query)
    results = cursor.fetchall()
    
    print("Program -> Specialty relationships:")
    for row in results:
        print(f"  {row[0]}: {row[1]} specialties")
    
    # Test specialty-course relationship
    query = """
    SELECT s.specialty_name, COUNT(DISTINCT c.course_id) as course_count
    FROM specialties s
    LEFT JOIN specialty_courses sc ON s.specialty_id = sc.specialty_id
    LEFT JOIN courses c ON sc.course_id = c.course_id
    GROUP BY s.specialty_id, s.specialty_name
    LIMIT 10
    """
    
    cursor.execute(query)
    results = cursor.fetchall()
    
    print("\nSpecialty -> Course relationships (sample):")
    for row in results:
        print(f"  {row[0]}: {row[1]} courses")
    
    # Test required vs optional courses
    query = """
    SELECT 
        CASE WHEN sc.is_required = 1 THEN 'Required' ELSE 'Optional' END as course_type,
        COUNT(*) as count
    FROM specialty_courses sc
    GROUP BY sc.is_required
    """
    
    cursor.execute(query)
    results = cursor.fetchall()
    
    print("\nCourse Type Distribution:")
    for row in results:
        print(f"  {row[0]}: {row[1]} courses")
    
    conn.close()
    print("\n✅ Relationship test complete")
    return True

def test_course_comparison():
    """Test the course comparison functionality"""
    print("\n🔍 Testing Course Comparison Functionality...")
    print("=" * 50)
    
    # Get a sample program and some of its courses
    conn = connect_database()
    cursor = conn.cursor()
    
    # Get first program
    cursor.execute("SELECT program_name FROM programs LIMIT 1")
    program_result = cursor.fetchone()
    
    if not program_result:
        print("❌ No programs found")
        conn.close()
        return False
    
    test_program = program_result[0]
    
    # Get some courses from this program
    query = """
    SELECT DISTINCT c.subject
    FROM programs p
    JOIN specialties s ON p.program_id = s.program_id
    JOIN specialty_courses sc ON s.specialty_id = sc.specialty_id
    JOIN courses c ON sc.course_id = c.course_id
    WHERE p.program_name = ?
    LIMIT 3
    """
    
    cursor.execute(query, (test_program,))
    course_results = cursor.fetchall()
    
    if not course_results:
        print("❌ No courses found for this program")
        conn.close()
        return False
    
    test_courses = [row[0] for row in course_results]
    
    conn.close()
    
    print(f"Testing with program: {test_program}")
    print(f"Testing with courses: {', '.join(test_courses)}")
    print()
    
    # Run comparison
    analysis = compare_courses_for_degree(test_program, test_courses)
    
    if analysis and 'error' not in analysis:
        print("✅ Course comparison successful")
        display_course_comparison(analysis)
        return True
    else:
        print("❌ Course comparison failed")
        if analysis:
            print(f"Error: {analysis.get('error', 'Unknown error')}")
        return False

def run_all_tests():
    """Run all test functions"""
    print("🧪 RUNNING ALL TESTS")
    print("=" * 60)
    
    tests = [
        ("Database Structure", test_database_structure),
        ("Query Specific Program", test_query_specific_program),
        ("Table Relationships", test_relationships),
        ("Course Comparison", test_course_comparison)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n❌ {test_name} raised an exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"  {status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed!")
    else:
        print("⚠️  Some tests failed")

if __name__ == "__main__":
    run_all_tests()
