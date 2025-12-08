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
        
        # Query to get program information with all related specialties, sub-specialties, and courses
        # Use LEFT JOIN for courses to include courses not yet in the courses table
        query = """
        SELECT 
            p.program_name,
            p.program_notes,
            p.program_requirements,
            s.specialty_name,
            s.specialty_type,
            s.specialty_notes,
            ss.sub_specialty_name,
            ss.sub_specialty_requirements,
            sc.course_code,
            c.Course_Title,
            c.Subject,
            c.Course_Description,
            c.Instructors,
            c.Credits,
            sc.sub_specialty_courses
        FROM programs p
        LEFT JOIN specialties s ON p.id = s.program_id
        LEFT JOIN sub_specialties ss ON s.id = ss.specialty_id
        LEFT JOIN specialty_classes sc ON ss.id = sc.sub_specialty_id
        LEFT JOIN courses c ON sc.course_code = c.course_code
        WHERE p.program_name LIKE ?
        ORDER BY s.specialty_type DESC, s.specialty_name, ss.sub_specialty_name, sc.course_code
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
    print(f"Program Notes: {program_info[1] if program_info[1] else 'N/A'}")
    print(f"Program Requirements: {program_info[2] if program_info[2] else 'N/A'} OPTIONAL specialties required")
    print("  (Must complete ALL Required specialties + this many Optional specialties)")
    print()
    
    # Group results by specialty and sub-specialty
    specialties = {}
    required_count = 0
    optional_count = 0
    
    for row in results:
        if row[3]:  # If specialty exists
            specialty_name = row[3]
            specialty_type = row[4]
            
            if specialty_name not in specialties:
                specialties[specialty_name] = {
                    'type': specialty_type,
                    'notes': row[5],
                    'sub_specialties': {}
                }
                if specialty_type == 'Required':
                    required_count += 1
                elif specialty_type == 'Optional':
                    optional_count += 1
            
            if row[6]:  # If sub-specialty exists
                sub_specialty_name = row[6]
                if sub_specialty_name not in specialties[specialty_name]['sub_specialties']:
                    specialties[specialty_name]['sub_specialties'][sub_specialty_name] = {
                        'requirements': row[7],
                        'courses': []
                    }
                
                if row[8]:  # If course_code exists in specialty_classes
                    course_info = {
                        'code': row[8],
                        'title': row[9] if row[9] else f"Course information not available",
                        'subject': row[10] if row[10] else row[8],  # Use course_code as subject if not available
                        'description': row[11],
                        'instructors': row[12],
                        'credits': row[13],
                        'sub_specialty_courses': row[14],
                        'incomplete_info': row[9] is None  # Flag for missing course details
                    }
                    specialties[specialty_name]['sub_specialties'][sub_specialty_name]['courses'].append(course_info)
    
    # Display specialty counts
    print(f"📊 SPECIALTY OVERVIEW:")
    print(f"   Required Specialties: {required_count} (must complete ALL)")
    print(f"   Optional Specialties: {optional_count} (must complete {program_info[2] if program_info[2] else 0})")
    print(f"   Total to Complete: {required_count + int(program_info[2] if program_info[2] else 0)} specialties")
    print()
    print("=" * 80)
    print()
    
    # Display Required specialties first, then Optional
    for specialty_type in ['Required', 'Optional']:
        for specialty_name, specialty_data in specialties.items():
            if specialty_data['type'] != specialty_type:
                continue
                
            type_emoji = '🔴' if specialty_type == 'Required' else '🟢'
            print(f"{type_emoji} SPECIALTY: {specialty_name} ({specialty_type})")
            print(f"   Notes: {specialty_data['notes'] if specialty_data['notes'] else 'N/A'}")
            print(f"   To complete this specialty: Satisfy ALL sub-specialties below")
            print()
            
            for sub_specialty_name, sub_specialty_data in specialty_data['sub_specialties'].items():
                courses_required = int(sub_specialty_data['requirements']) if sub_specialty_data['requirements'] else 0
                courses_available = len(sub_specialty_data['courses'])
                
                # Determine if students have choice
                if courses_required == courses_available and courses_required > 0:
                    requirement_text = f"ALL {courses_available} courses REQUIRED (no choice)"
                elif courses_required < courses_available:
                    requirement_text = f"Choose {courses_required} of {courses_available} courses"
                elif courses_required == 0:
                    requirement_text = "Requirements not specified"
                else:
                    requirement_text = f"{courses_required} courses required"
                
                print(f"   └─ SUB-SPECIALTY: {sub_specialty_name}")
                print(f"      📋 Requirement: {requirement_text}")
                print(f"      COURSES:")
                
                if sub_specialty_data['courses']:
                    for course in sub_specialty_data['courses']:
                        print(f"      • {course['code']} - {course['title']}")
                        print(f"        Subject: {course['subject']} | Credits: {course['credits']}")
                        print(f"        Instructors: {course['instructors'] if course['instructors'] else 'N/A'}")
                        if course['sub_specialty_courses']:
                            print(f"        Notes: {course['sub_specialty_courses']}")
                        print()
                else:
                    print("        ⚠️  No courses assigned to this sub-specialty")
                    print()
        
        if specialty_type == 'Required' and optional_count > 0:
            print("=" * 80)
            print()

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
    """Visualize the relationship between courses, sub-specialties, and specialties for a specific program using Plotly"""
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
            s.specialty_type,
            ss.sub_specialty_name,
            ss.sub_specialty_requirements,
            c.course_code,
            c.Course_Title,
            c.Subject
        FROM programs p
        LEFT JOIN specialties s ON p.id = s.program_id
        LEFT JOIN sub_specialties ss ON s.id = ss.specialty_id
        LEFT JOIN specialty_classes sc ON ss.id = sc.sub_specialty_id
        LEFT JOIN courses c ON sc.course_code = c.course_code
        WHERE p.program_name LIKE ?
        ORDER BY s.specialty_name, ss.sub_specialty_name, c.course_code
        """
        
        cursor.execute(query, (f"%{program_name}%",))
        results = cursor.fetchall()
        
        if not results:
            print(f"No program found matching '{program_name}'")
            conn.close()
            return
        
        # Get program name
        program_title = results[0][0]
        
        # Group by specialty and sub-specialty
        specialties = {}
        for row in results:
            if row[1]:  # If specialty exists
                specialty_name = row[1]
                specialty_type = row[2]
                
                if specialty_name not in specialties:
                    specialties[specialty_name] = {
                        'type': specialty_type,
                        'sub_specialties': {}
                    }
                
                if row[3]:  # If sub-specialty exists
                    sub_specialty_name = row[3]
                    sub_specialty_req = row[4]
                    
                    if sub_specialty_name not in specialties[specialty_name]['sub_specialties']:
                        specialties[specialty_name]['sub_specialties'][sub_specialty_name] = {
                            'requirements': sub_specialty_req,
                            'courses': []
                        }
                    
                    if row[5]:  # If course exists
                        course_info = {
                            'code': row[5],
                            'title': row[6],
                            'subject': row[7]
                        }
                        specialties[specialty_name]['sub_specialties'][sub_specialty_name]['courses'].append(course_info)
        
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
        node_texts.append(program_title[:30])
        hover_texts.append(f"<b>{program_title}</b><br>Specialties: {len(specialties)}")
        
        # Calculate positions
        num_specialties = len(specialties)
        specialty_y_spacing = 3.0
        sub_specialty_y_spacing = 1.5
        course_y_spacing = 0.5
        
        y_offset = -(num_specialties - 1) * specialty_y_spacing / 2
        
        for spec_idx, (specialty_name, specialty_data) in enumerate(specialties.items()):
            # Specialty node
            spec_y = y_offset + spec_idx * specialty_y_spacing
            spec_id = f"spec_{spec_idx}"
            
            nodes.append({'id': spec_id, 'x': 2.5, 'y': spec_y, 'level': 1})
            node_colors.append('#2ca02c')  # Green
            node_sizes.append(30)
            node_texts.append(specialty_name[:25] + "..." if len(specialty_name) > 25 else specialty_name)
            
            num_sub_specs = len(specialty_data['sub_specialties'])
            hover_texts.append(
                f"<b>{specialty_name}</b><br>"
                f"Type: {specialty_data['type']}<br>"
                f"Sub-specialties: {num_sub_specs}"
            )
            
            # Edge from program to specialty
            edges.append({'from': program_title, 'to': spec_id})
            
            # Sub-specialty nodes
            sub_spec_y_offset = spec_y - (num_sub_specs - 1) * sub_specialty_y_spacing / 2
            
            for sub_idx, (sub_specialty_name, sub_specialty_data) in enumerate(specialty_data['sub_specialties'].items()):
                sub_spec_y = sub_spec_y_offset + sub_idx * sub_specialty_y_spacing
                sub_spec_id = f"sub_{spec_idx}_{sub_idx}"
                
                nodes.append({'id': sub_spec_id, 'x': 5, 'y': sub_spec_y, 'level': 2})
                node_colors.append('#9467bd')  # Purple
                node_sizes.append(25)
                node_texts.append(sub_specialty_name[:20] + "..." if len(sub_specialty_name) > 20 else sub_specialty_name)
                
                num_courses = len(sub_specialty_data['courses'])
                hover_texts.append(
                    f"<b>{sub_specialty_name}</b><br>"
                    f"Requirements: {sub_specialty_data['requirements']}<br>"
                    f"Courses: {num_courses}"
                )
                
                # Edge from specialty to sub-specialty
                edges.append({'from': spec_id, 'to': sub_spec_id})
                
                # Course nodes
                course_y_offset = sub_spec_y - (num_courses - 1) * course_y_spacing / 2
                
                for course_idx, course in enumerate(sub_specialty_data['courses']):
                    course_y = course_y_offset + course_idx * course_y_spacing
                    course_id = f"course_{spec_idx}_{sub_idx}_{course_idx}"
                    
                    nodes.append({'id': course_id, 'x': 7.5, 'y': course_y, 'level': 3})
                    node_colors.append('#ff7f0e')  # Orange
                    node_sizes.append(18)
                    node_texts.append(course['subject'])
                    hover_texts.append(
                        f"<b>{course['code']}</b><br>"
                        f"{course['title']}"
                    )
                    
                    # Edge from sub-specialty to course
                    edges.append({'from': sub_spec_id, 'to': course_id})
        
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
            textfont=dict(size=9, color='white'),
            hovertemplate='%{customdata}<extra></extra>',
            customdata=hover_texts
        )
        
        # Create figure
        fig = go.Figure(data=[edge_trace, node_trace])
        
        fig.update_layout(
            title=dict(
                text=f"<b>{program_title} - Program Structure</b><br><sub>🔵 Program | 🟢 Specialty | 🟣 Sub-Specialty | 🟠 Course</sub>",
                x=0.5,
                xanchor='center',
                font=dict(size=18)
            ),
            showlegend=False,
            hovermode='closest',
            width=1600,
            height=1200,
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
        print(f"   📊 {len(specialties)} specialties with {len([n for n in nodes if n['level'] == 3])} total courses")
        print(f"   🔵 Blue = Program | 🟢 Green = Specialty")
        print(f"   🟣 Purple = Sub-Specialty | 🟠 Orange = Course")
        
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
    
    Logic:
    - Program completion = All Required specialties + N Optional specialties (N = program_requirements)
    - Specialty completion = All sub-specialties satisfied
    - Sub-specialty completion = Complete required number of courses from available courses
    
    Args:
        program_name (str): Name of the program to check against
        completed_courses (list): List of course codes that the student has completed
    
    Returns:
        dict: Analysis results including missing courses, satisfied sub-specialties, etc.
    """
    conn = connect_database()
    if not conn:
        return None
    
    try:
        cursor = conn.cursor()
        
        # Get all courses for the program grouped by specialty and sub-specialty
        query = """
        SELECT 
            p.program_name,
            p.program_requirements,
            s.specialty_name,
            s.specialty_type,
            ss.sub_specialty_name,
            ss.sub_specialty_requirements,
            c.course_code,
            c.Course_Title,
            c.Subject
        FROM programs p
        LEFT JOIN specialties s ON p.id = s.program_id
        LEFT JOIN sub_specialties ss ON s.id = ss.specialty_id
        LEFT JOIN specialty_classes sc ON ss.id = sc.sub_specialty_id
        LEFT JOIN courses c ON sc.course_code = c.course_code
        WHERE p.program_name LIKE ? AND c.course_code IS NOT NULL
        ORDER BY s.specialty_type DESC, s.specialty_name, ss.sub_specialty_name, c.course_code
        """
        
        cursor.execute(query, (f"%{program_name}%",))
        results = cursor.fetchall()
        
        if not results:
            conn.close()
            return {"error": f"No program found matching '{program_name}'"}
        
        # Convert completed courses to uppercase for comparison
        completed_courses_upper = [course.upper().strip() for course in completed_courses]
        
        # Organize program requirements
        program_info = {
            'name': results[0][0],
            'requirements': results[0][1],  # Number of optional specialties needed
            'specialties': {}
        }
        
        # Group courses by specialty and sub-specialty
        for row in results:
            specialty_name = row[2]
            specialty_type = row[3]
            sub_specialty_name = row[4]
            sub_specialty_req = row[5]
            course_code = row[6]
            course_title = row[7]
            course_subject = row[8]
            
            if specialty_name not in program_info['specialties']:
                program_info['specialties'][specialty_name] = {
                    'type': specialty_type,
                    'sub_specialties': {}
                }
            
            if sub_specialty_name not in program_info['specialties'][specialty_name]['sub_specialties']:
                program_info['specialties'][specialty_name]['sub_specialties'][sub_specialty_name] = {
                    'requirements': sub_specialty_req,
                    'all_courses': [],
                    'completed_courses': [],
                    'missing_courses': []
                }
            
            sub_spec = program_info['specialties'][specialty_name]['sub_specialties'][sub_specialty_name]
            course_info = {
                'code': course_code,
                'title': course_title,
                'subject': course_subject
            }
            
            sub_spec['all_courses'].append(course_info)
            
            if course_code.upper() in completed_courses_upper or course_subject.upper() in completed_courses_upper:
                sub_spec['completed_courses'].append(course_info)
            else:
                sub_spec['missing_courses'].append(course_info)
        
        # Analyze completion status
        analysis = {
            'program_name': program_info['name'],
            'program_requirements': program_info['requirements'],
            'completed_courses': completed_courses,
            'specialty_analysis': {},
            'overall_status': 'incomplete',
            'satisfied_required_specialties': 0,
            'total_required_specialties': 0,
            'satisfied_optional_specialties': 0,
            'total_optional_specialties': 0,
            'optional_specialties_needed': int(program_info['requirements']) if program_info['requirements'] else 0
        }
        
        # Analyze each specialty
        for specialty_name, specialty_data in program_info['specialties'].items():
            sub_spec_analysis = {}
            total_satisfied_sub_specs = 0
            total_sub_specs = len(specialty_data['sub_specialties'])
            
            # Check each sub-specialty
            for sub_spec_name, sub_spec_data in specialty_data['sub_specialties'].items():
                required = int(sub_spec_data['requirements']) if sub_spec_data['requirements'] else len(sub_spec_data['all_courses'])
                completed = len(sub_spec_data['completed_courses'])
                total_available = len(sub_spec_data['all_courses'])
                
                # Determine if sub-specialty is satisfied
                sub_spec_satisfied = completed >= required
                
                # Determine choice type
                if required == total_available and required > 0:
                    choice_type = "All courses required"
                elif required < total_available:
                    choice_type = f"Choice: {required} of {total_available}"
                else:
                    choice_type = "Requirements unclear"
                
                sub_spec_analysis[sub_spec_name] = {
                    'requirements': required,
                    'total_courses': total_available,
                    'completed_count': completed,
                    'completed_courses': sub_spec_data['completed_courses'],
                    'missing_courses': sub_spec_data['missing_courses'],
                    'satisfied': sub_spec_satisfied,
                    'choice_type': choice_type,
                    'status': '✅ Satisfied' if sub_spec_satisfied else '❌ Incomplete'
                }
                
                if sub_spec_satisfied:
                    total_satisfied_sub_specs += 1
            
            # Specialty is satisfied only if ALL sub-specialties are satisfied
            specialty_satisfied = (total_satisfied_sub_specs == total_sub_specs) and total_sub_specs > 0
            
            analysis['specialty_analysis'][specialty_name] = {
                'type': specialty_data['type'],
                'sub_specialties': sub_spec_analysis,
                'total_sub_specialties': total_sub_specs,
                'satisfied_sub_specialties': total_satisfied_sub_specs,
                'satisfied': specialty_satisfied,
                'status': '✅ Complete' if specialty_satisfied else '❌ Incomplete'
            }
            
            # Track required vs optional specialty completion
            if specialty_data['type'] == 'Required':
                analysis['total_required_specialties'] += 1
                if specialty_satisfied:
                    analysis['satisfied_required_specialties'] += 1
            elif specialty_data['type'] == 'Optional':
                analysis['total_optional_specialties'] += 1
                if specialty_satisfied:
                    analysis['satisfied_optional_specialties'] += 1
        
        # Determine overall program completion
        # Must complete ALL required + N optional specialties
        all_required_complete = (analysis['satisfied_required_specialties'] == analysis['total_required_specialties'])
        enough_optional_complete = (analysis['satisfied_optional_specialties'] >= analysis['optional_specialties_needed'])
        
        if all_required_complete and enough_optional_complete:
            analysis['overall_status'] = '✅ COMPLETE - Program requirements satisfied!'
        elif analysis['satisfied_required_specialties'] > 0 or analysis['satisfied_optional_specialties'] > 0:
            analysis['overall_status'] = '⚠️  IN PROGRESS - Some requirements satisfied'
        else:
            analysis['overall_status'] = '❌ NOT STARTED - No specialties completed'
        
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
    
    print("\n")
    print("🎯 PROGRAM COMPLETION ANALYSIS")
    print("=" * 80)
    print(f"Program: {analysis['program_name']}")
    print(f"Completed Courses Submitted: {', '.join(analysis['completed_courses'])}")
    print()
    
    # Overall status with clear logic
    print("📋 GRADUATION REQUIREMENTS:")
    print(f"   Required Specialties: {analysis['satisfied_required_specialties']}/{analysis['total_required_specialties']} complete")
    print(f"   Optional Specialties: {analysis['satisfied_optional_specialties']}/{analysis['total_optional_specialties']} complete")
    print(f"   Optional Needed: {analysis['optional_specialties_needed']}")
    print()
    
    # Check if graduation requirements are met
    all_required_done = analysis['satisfied_required_specialties'] == analysis['total_required_specialties']
    enough_optional_done = analysis['satisfied_optional_specialties'] >= analysis['optional_specialties_needed']
    
    print(f"Overall Status: {analysis['overall_status']}")
    print()
    
    if all_required_done and enough_optional_done:
        print("🎉 CONGRATULATIONS! You have met all graduation requirements!")
        print(f"   ✅ All {analysis['total_required_specialties']} Required specialties complete")
        print(f"   ✅ {analysis['satisfied_optional_specialties']} of {analysis['optional_specialties_needed']} Optional specialties complete")
    else:
        print("📝 REMAINING REQUIREMENTS:")
        if not all_required_done:
            remaining_required = analysis['total_required_specialties'] - analysis['satisfied_required_specialties']
            print(f"   ⚠️  Need {remaining_required} more Required specialties")
        if not enough_optional_done:
            remaining_optional = analysis['optional_specialties_needed'] - analysis['satisfied_optional_specialties']
            print(f"   ⚠️  Need {remaining_optional} more Optional specialties")
    
    print()
    print("=" * 80)
    print()
    
    # Specialty breakdown - Required first
    for specialty_type in ['Required', 'Optional']:
        type_emoji = '🔴' if specialty_type == 'Required' else '🟢'
        
        # Filter specialties by type
        specialties_of_type = {name: data for name, data in analysis['specialty_analysis'].items() 
                               if data['type'] == specialty_type}
        
        if not specialties_of_type:
            continue
            
        print(f"{type_emoji} {specialty_type.upper()} SPECIALTIES:")
        print("-" * 80)
        
        for specialty_name, specialty_analysis in specialties_of_type.items():
            print(f"\n{specialty_analysis['status']} {specialty_name}")
            print(f"   Sub-Specialties: {specialty_analysis['satisfied_sub_specialties']}/{specialty_analysis['total_sub_specialties']} complete")
            print(f"   Note: ALL sub-specialties must be satisfied to complete this specialty")
            print()
            
            for sub_spec_name, sub_spec_data in specialty_analysis['sub_specialties'].items():
                print(f"   {sub_spec_data['status']} SUB-SPECIALTY: {sub_spec_name}")
                print(f"      Requirement: {sub_spec_data['choice_type']}")
                print(f"      Completed: {sub_spec_data['completed_count']}/{sub_spec_data['requirements']} courses")
                
                if sub_spec_data['completed_courses']:
                    print(f"      ✓ Completed Courses:")
                    for course in sub_spec_data['completed_courses']:
                        print(f"         • {course['code']} - {course['title']}")
                
                if not sub_spec_data['satisfied'] and sub_spec_data['missing_courses']:
                    remaining = sub_spec_data['requirements'] - sub_spec_data['completed_count']
                    if remaining > 0:
                        print(f"      📝 Need {remaining} more course(s) from:")
                        for course in sub_spec_data['missing_courses']:
                            print(f"         • {course['code']} - {course['title']}")
                
                print()
        
        print("=" * 80)
        print()
    
    # Summary
    print("📌 SUMMARY")
    print("=" * 80)
    
    if all_required_done and enough_optional_done:
        print("🎉 You are ready to graduate! All requirements satisfied.")
    else:
        print("To graduate, you must:")
        print(f"1. Complete ALL {analysis['total_required_specialties']} Required specialties")
        print(f"2. Complete {analysis['optional_specialties_needed']} Optional specialties")
        print()
        print("Remember:")
        print("• To complete a specialty, ALL its sub-specialties must be satisfied")
        print("• Each sub-specialty requires a specific number of courses")
        print("• Some sub-specialties require ALL courses, others allow choice")

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
        print("Enter your completed course codes (one per line, press Enter twice when done):")
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