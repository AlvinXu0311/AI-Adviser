import sqlite3
import sys
import plotly.graph_objects as go
import webbrowser
import os

def connect_database(db_path="bus_school.db"):
    """Connect to the SQLite database"""
    try:
        conn = sqlite3.connect(db_path)
        return conn
    except sqlite3.Error as e:
        print(f"Error connecting to database: {e}")
        return None

def query_degree_info(program_name):
    """Query database for a specific program and return all related information"""
    conn = connect_database()
    if not conn:
        return None
    
    try:
        cursor = conn.cursor()
        
        # Query to get program information with all related specialties and courses
        query = """
        SELECT 
            p.program_name,
            p.description as program_description,
            p.program_level,
            s.specialty_name,
            s.description as specialty_description,
            c.course_title,
            c.subject,
            c.course_description,
            c.instructors,
            c.credits,
            sc.is_required
        FROM programs p
        LEFT JOIN specialties s ON p.program_id = s.program_id
        LEFT JOIN specialty_courses sc ON s.specialty_id = sc.specialty_id
        LEFT JOIN courses c ON sc.course_id = c.course_id
        WHERE p.program_name LIKE ?
        ORDER BY s.specialty_name, sc.is_required DESC, c.course_title
        """
        
        cursor.execute(query, (f"%{program_name}%",))
        results = cursor.fetchall()
        
        conn.close()
        return results
        
    except sqlite3.Error as e:
        print(f"Error querying database: {e}")
        if conn:
            conn.close()
        return None

def display_degree_info(results, program_name):
    """Display the program information in a formatted way"""
    if not results:
        print(f"No program found matching '{program_name}'")
        return
    
    # Get program information from first result
    program_info = results[0]
    print("=" * 80)
    print(f"PROGRAM: {program_info[0]}")
    print("=" * 80)
    print(f"Description: {program_info[1]}")
    print(f"Level: {program_info[2]}")
    print()
    
    # Group results by specialty
    specialties = {}
    for row in results:
        if row[3]:  # If specialty exists
            specialty_name = row[3]
            if specialty_name not in specialties:
                specialties[specialty_name] = {
                    'description': row[4],
                    'courses': []
                }
            
            if row[5]:  # If course exists
                course_info = {
                    'title': row[5],
                    'subject': row[6],
                    'description': row[7],
                    'instructors': row[8],
                    'credits': row[9],
                    'is_required': row[10]
                }
                specialties[specialty_name]['courses'].append(course_info)
    
    # Display specialties and courses
    for specialty_name, specialty_data in specialties.items():
        print(f"📋 SPECIALTY: {specialty_name}")
        print(f"   Description: {specialty_data['description']}")
        print("   COURSES:")
        
        if specialty_data['courses']:
            for course in specialty_data['courses']:
                req_type = 'Required' if course['is_required'] else 'Optional'
                print(f"   • {course['subject']} - {course['title']} ({req_type})")
                print(f"     Instructors: {course['instructors']}")
                print(f"     Credits: {course['credits']}")
                print(f"     Description: {course['description']}")
                print()
        else:
            print("     No courses assigned to this specialty")
            print()
        print("-" * 60)

def list_all_degrees():
    """List all available programs in the database"""
    conn = connect_database()
    if not conn:
        return
    
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT program_name FROM programs ORDER BY program_name")
        programs = cursor.fetchall()
        
        print("Available programs:")
        for program in programs:
            print(f"  - {program[0]}")
        print()
        conn.close()
        
    except sqlite3.Error as e:
        print(f"Error fetching programs: {e}")
        if conn:
            conn.close()

def visualize_degree_structure(program_name):
    """Visualize the relationship between courses and specialties for a specific program using Plotly"""
    conn = connect_database()
    if not conn:
        return
    
    try:
        cursor = conn.cursor()
        
        # Query to get program structure
        query = """
        SELECT 
            p.program_name,
            s.specialty_name,
            c.course_title,
            c.subject,
            sc.is_required
        FROM programs p
        LEFT JOIN specialties s ON p.program_id = s.program_id
        LEFT JOIN specialty_courses sc ON s.specialty_id = sc.specialty_id
        LEFT JOIN courses c ON sc.course_id = c.course_id
        WHERE p.program_name LIKE ?
        ORDER BY s.specialty_name, sc.is_required DESC, c.course_title
        """
        
        cursor.execute(query, (f"%{program_name}%",))
        results = cursor.fetchall()
        
        if not results:
            print(f"No program found matching '{program_name}'")
            conn.close()
            return
        
        # Get program name
        program_title = results[0][0]
        
        # Group by specialty
        specialties = {}
        for row in results:
            if row[1]:  # If specialty exists
                specialty_name = row[1]
                if specialty_name not in specialties:
                    specialties[specialty_name] = {'required': [], 'optional': []}
                
                if row[2]:  # If course exists
                    course_info = {
                        'subject': row[3],
                        'title': row[2],
                        'is_required': row[4]
                    }
                    if course_info['is_required']:
                        specialties[specialty_name]['required'].append(course_info)
                    else:
                        specialties[specialty_name]['optional'].append(course_info)
        
        # Build node positions and edges for tree layout
        nodes = []
        edges = []
        node_colors = []
        node_sizes = []
        node_texts = []
        hover_texts = []
        
        # Root node (program)
        nodes.append({'id': program_title, 'x': 0, 'y': 0, 'level': 0})
        node_colors.append('#1f77b4')  # Blue
        node_sizes.append(40)
        node_texts.append(program_title)
        hover_texts.append(f"<b>{program_title}</b><br>Specialties: {len(specialties)}")
        
        # Calculate positions
        num_specialties = len(specialties)
        specialty_y_spacing = 2.0
        course_y_spacing = 0.8
        
        y_offset = -(num_specialties - 1) * specialty_y_spacing / 2
        
        for spec_idx, (specialty_name, courses_data) in enumerate(specialties.items()):
            # Specialty node
            spec_y = y_offset + spec_idx * specialty_y_spacing
            spec_id = f"spec_{spec_idx}"
            
            nodes.append({'id': spec_id, 'x': 3, 'y': spec_y, 'level': 1})
            node_colors.append('#2ca02c')  # Green
            node_sizes.append(30)
            node_texts.append(specialty_name[:20] + "..." if len(specialty_name) > 20 else specialty_name)
            
            total_courses = len(courses_data['required']) + len(courses_data['optional'])
            hover_texts.append(
                f"<b>{specialty_name}</b><br>"
                f"Required: {len(courses_data['required'])}<br>"
                f"Optional: {len(courses_data['optional'])}"
            )
            
            # Edge from program to specialty
            edges.append({'from': program_title, 'to': spec_id})
            
            # Course nodes
            all_courses = [('Required', c) for c in courses_data['required']] + \
                         [('Optional', c) for c in courses_data['optional']]
            
            num_courses = len(all_courses)
            course_y_offset = spec_y - (num_courses - 1) * course_y_spacing / 2
            
            for course_idx, (course_type, course) in enumerate(all_courses):
                course_y = course_y_offset + course_idx * course_y_spacing
                course_id = f"course_{spec_idx}_{course_idx}"
                
                nodes.append({'id': course_id, 'x': 6, 'y': course_y, 'level': 2})
                
                if course_type == 'Required':
                    node_colors.append('#ff7f0e')  # Orange
                    node_sizes.append(20)
                else:
                    node_colors.append('#ffbb78')  # Light orange
                    node_sizes.append(18)
                
                node_texts.append(course['subject'])
                hover_texts.append(
                    f"<b>{course['subject']}</b><br>"
                    f"{course['title']}<br>"
                    f"<b>{course_type.upper()}</b>"
                )
                
                # Edge from specialty to course
                edges.append({'from': spec_id, 'to': course_id})
        
        # Extract coordinates for plotting
        node_x = [n['x'] for n in nodes]
        node_y = [n['y'] for n in nodes]
        
        # Create edge traces
        edge_x = []
        edge_y = []
        
        for edge in edges:
            from_node = next(n for n in nodes if n['id'] == edge['from'])
            to_node = next(n for n in nodes if n['id'] == edge['to'])
            
            edge_x.extend([from_node['x'], to_node['x'], None])
            edge_y.extend([from_node['y'], to_node['y'], None])
        
        # Create edge trace
        edge_trace = go.Scatter(
            x=edge_x,
            y=edge_y,
            mode='lines',
            line=dict(width=1, color='#888'),
            hoverinfo='none'
        )
        
        # Create node trace
        node_trace = go.Scatter(
            x=node_x,
            y=node_y,
            mode='markers+text',
            marker=dict(
                size=node_sizes,
                color=node_colors,
                line=dict(width=2, color='white')
            ),
            text=node_texts,
            textposition='middle center',
            textfont=dict(size=10, color='white'),
            hovertemplate='%{customdata}<extra></extra>',
            customdata=hover_texts
        )
        
        # Create figure
        fig = go.Figure(data=[edge_trace, node_trace])
        
        fig.update_layout(
            title=dict(
                text=f"<b>{program_title} - Program Structure</b><br><sub>🔵 Program | 🟢 Specialty | 🟠 Required Course | 🟡 Optional Course</sub>",
                x=0.5,
                xanchor='center',
                font=dict(size=20)
            ),
            showlegend=False,
            hovermode='closest',
            width=1400,
            height=1000,
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            plot_bgcolor='white',
            margin=dict(t=100, l=20, r=20, b=20)
        )
        
        # Save and open
        output_file = "degree_structure.html"
        fig.write_html(output_file)
        
        file_path = os.path.abspath(output_file)
        webbrowser.open(f"file://{file_path}")
        print(f"✅ Interactive tree visualization opened in your default web browser.")
        print(f"   📊 {len(specialties)} specialties with {len([n for n in nodes if n['level'] == 2])} total courses")
        print(f"   🔵 Blue = Program | 🟢 Green = Specialty")
        print(f"   🟠 Orange = Required Course | 🟡 Light Orange = Optional Course")
        
        conn.close()
        
    except sqlite3.Error as e:
        print(f"Error creating visualization: {e}")
        if conn:
            conn.close()
    except Exception as e:
        print(f"Error generating visualization: {e}")
        if conn:
            conn.close()

def compare_courses_for_degree(program_name, completed_courses):
    """
    Compare completed courses against program requirements and identify missing courses
    
    Args:
        program_name (str): Name of the program to check against
        completed_courses (list): List of course subjects that the student has completed
    
    Returns:
        dict: Analysis results including missing courses, satisfied specialties, etc.
    """
    conn = connect_database()
    if not conn:
        return None
    
    try:
        cursor = conn.cursor()
        
        # Get all required courses for the program
        query = """
        SELECT 
            p.program_name,
            s.specialty_name,
            c.subject,
            c.course_title,
            sc.is_required,
            s.specialty_id
        FROM programs p
        LEFT JOIN specialties s ON p.program_id = s.program_id
        LEFT JOIN specialty_courses sc ON s.specialty_id = sc.specialty_id
        LEFT JOIN courses c ON sc.course_id = c.course_id
        WHERE p.program_name LIKE ? AND c.subject IS NOT NULL
        ORDER BY s.specialty_name, sc.is_required DESC, c.subject
        """
        
        cursor.execute(query, (f"%{program_name}%",))
        results = cursor.fetchall()
        
        if not results:
            conn.close()
            return {"error": f"No program found matching '{program_name}'"}
        
        # Convert completed courses to uppercase for comparison
        completed_courses_upper = [course.upper() for course in completed_courses]
        
        # Organize program requirements
        program_info = {
            'name': results[0][0],
            'specialties': {}
        }
        
        # Group courses by specialty
        for row in results:
            specialty_name = row[1]
            course_subject = row[2]
            course_title = row[3]
            is_required = row[4]
            specialty_id = row[5]
            
            if specialty_name not in program_info['specialties']:
                program_info['specialties'][specialty_name] = {
                    'id': specialty_id,
                    'required_courses': [],
                    'optional_courses': [],
                    'completed_required': [],
                    'completed_optional': [],
                    'missing_required': [],
                    'missing_optional': []
                }
            
            specialty = program_info['specialties'][specialty_name]
            course_info = {'subject': course_subject, 'title': course_title}
            
            if is_required:
                specialty['required_courses'].append(course_info)
                if course_subject.upper() in completed_courses_upper:
                    specialty['completed_required'].append(course_info)
                else:
                    specialty['missing_required'].append(course_info)
            else:
                specialty['optional_courses'].append(course_info)
                if course_subject.upper() in completed_courses_upper:
                    specialty['completed_optional'].append(course_info)
                else:
                    specialty['missing_optional'].append(course_info)
        
        # Analyze completion status
        analysis = {
            'program_name': program_info['name'],
            'completed_courses': completed_courses,
            'specialty_analysis': {},
            'overall_status': 'incomplete',
            'satisfied_specialties': 0,
            'total_specialties': len(program_info['specialties'])
        }
        
        satisfied_specialties = 0
        
        for specialty_name, specialty_data in program_info['specialties'].items():
            # Check if specialty is satisfied (all required courses completed)
            required_satisfied = len(specialty_data['missing_required']) == 0
            
            specialty_analysis = {
                'required_satisfied': required_satisfied,
                'total_required': len(specialty_data['required_courses']),
                'completed_required': len(specialty_data['completed_required']),
                'missing_required': specialty_data['missing_required'],
                'total_optional': len(specialty_data['optional_courses']),
                'completed_optional': len(specialty_data['completed_optional']),
                'missing_optional': specialty_data['missing_optional'],
                'status': 'satisfied' if required_satisfied else 'incomplete'
            }
            
            analysis['specialty_analysis'][specialty_name] = specialty_analysis
            
            if required_satisfied:
                satisfied_specialties += 1
        
        analysis['satisfied_specialties'] = satisfied_specialties
        
        # Check overall program completion
        if satisfied_specialties >= analysis['total_specialties']:
            analysis['overall_status'] = 'complete'
        elif satisfied_specialties > 0:
            analysis['overall_status'] = 'partial_completion'
        
        conn.close()
        return analysis
        
    except sqlite3.Error as e:
        print(f"Error comparing courses: {e}")
        if conn:
            conn.close()
        return {"error": f"Database error: {e}"}

def display_course_comparison(analysis):
    """Display the course comparison results in a formatted way"""
    if 'error' in analysis:
        print(f"Error: {analysis['error']}")
        return
    
    print("🎯 PROGRAM COMPLETION ANALYSIS")
    print("=" * 70)
    print(f"Program: {analysis['program_name']}")
    print(f"Completed Courses: {', '.join(analysis['completed_courses'])}")
    print()
    
    # Overall status
    status_emoji = {
        'complete': '✅',
        'partial_completion': '⚠️',
        'incomplete': '❌'
    }
    
    emoji = status_emoji.get(analysis['overall_status'], '❓')
    print(f"Overall Status: {emoji} {analysis['overall_status'].replace('_', ' ').title()}")
    print(f"Satisfied Specialties: {analysis['satisfied_specialties']}/{analysis['total_specialties']}")
    print()
    
    # Specialty breakdown
    print("📋 SPECIALTY BREAKDOWN")
    print("=" * 50)
    
    for specialty_name, specialty_analysis in analysis['specialty_analysis'].items():
        status_emoji = '✅' if specialty_analysis['status'] == 'satisfied' else '❌'
        print(f"{status_emoji} {specialty_name}")
        
        # Required courses status
        req_completed = specialty_analysis['completed_required']
        req_total = specialty_analysis['total_required']
        print(f"   Required Courses: {req_completed}/{req_total} completed")
        
        if specialty_analysis['missing_required']:
            print("   📝 Missing Required Courses:")
            for course in specialty_analysis['missing_required']:
                print(f"      • {course['subject']} - {course['title']}")
        
        # Optional courses status
        opt_completed = specialty_analysis['completed_optional']
        opt_total = specialty_analysis['total_optional']
        if opt_total > 0:
            print(f"   Optional Courses: {opt_completed}/{opt_total} completed")
            
            if specialty_analysis['missing_optional']:
                print("   📚 Available Optional Courses:")
                for course in specialty_analysis['missing_optional']:
                    print(f"      • {course['subject']} - {course['title']}")
        
        print()
    
    # Summary of what's needed
    print("📌 SUMMARY")
    print("=" * 30)
    
    if analysis['overall_status'] == 'complete':
        print("🎉 Congratulations! All program requirements are satisfied.")
    elif analysis['overall_status'] == 'partial_completion':
        print("✨ Some specialties completed. Continue working on remaining ones.")
    else:
        print("📝 To complete specialties, you need:")
        for specialty_name, specialty_analysis in analysis['specialty_analysis'].items():
            if specialty_analysis['status'] != 'satisfied' and specialty_analysis['missing_required']:
                print(f"   {specialty_name}:")
                for course in specialty_analysis['missing_required']:
                    print(f"      - {course['subject']} ({course['title']})")

def interactive_course_comparison():
    """Interactive function to compare student courses against program requirements"""
    print("🎯 COURSE COMPARISON TOOL")
    print("=" * 40)
    
    # Get program name
    list_all_degrees()
    program_name = input("Enter program name to check against: ").strip()
    
    if not program_name:
        print("Please provide a program name.")
        return
    
    # Get completed courses
    print("\nEnter your completed course subjects (one per line, press Enter twice when done):")
    completed_courses = []
    while True:
        course = input().strip()
        if not course:
            break
        completed_courses.append(course)
    
    if not completed_courses:
        print("No courses entered.")
        return
    
    # Perform comparison
    print(f"\nAnalyzing {len(completed_courses)} completed courses against '{program_name}'...")
    print()
    
    analysis = compare_courses_for_degree(program_name, completed_courses)
    display_course_comparison(analysis)

def main():
    """Main function to handle command line interaction"""
    if len(sys.argv) > 1:
        program_name = " ".join(sys.argv[1:])
    else:
        print("WPI Bus School - Program Information Query")
        print("=" * 50)
        list_all_degrees()
        program_name = input("Enter program name (or part of it): ").strip()
    
    if not program_name:
        print("Please provide a program name.")
        return
    
    # Ask user what type of output they want
    print("\nChoose display option:")
    print("1. Detailed information")
    print("2. Structure visualization")
    print("3. Course comparison (check your progress)")
    print("4. Both detailed info and visualization")
    
    choice = input("Enter choice (1-4, default is 1): ").strip()
    
    if choice == "2":
        visualize_degree_structure(program_name)
    elif choice == "3":
        # Use the program name already provided
        print(f"\nChecking course completion for: {program_name}")
        print("Enter your completed course subjects (one per line, press Enter twice when done):")
        completed_courses = []
        while True:
            course = input().strip()
            if not course:
                break
            completed_courses.append(course)
        
        if completed_courses:
            analysis = compare_courses_for_degree(program_name, completed_courses)
            display_course_comparison(analysis)
        else:
            print("No courses entered.")
    elif choice == "4":
        results = query_degree_info(program_name)
        display_degree_info(results, program_name)
        print("\n" + "="*60 + "\n")
        visualize_degree_structure(program_name)
    else:  # Default to detailed view
        results = query_degree_info(program_name)
        display_degree_info(results, program_name)

if __name__ == "__main__":
    main()