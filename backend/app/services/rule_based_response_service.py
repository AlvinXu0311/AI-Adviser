"""
Rule-Based Response Service

This service provides hardcoded, reliable responses for specific intent types
that don't require LLM inference, ensuring consistent and fast responses for
common academic advisor questions.
"""

import logging
from typing import Optional
from app.schemas.chat import IntentType, TranscriptContext

logger = logging.getLogger(__name__)


class RuleBasedResponseService:
    """Service for generating rule-based responses to common questions"""

    def __init__(self):
        """Initialize with predefined response templates"""
        self.responses = {
            IntentType.PROGRAM_REQUIREMENTS: self._handle_program_requirements,
            IntentType.PREREQUISITE: self._handle_prerequisite,
            IntentType.ACADEMIC_PROGRESS: self._handle_academic_progress,
            IntentType.GPA_RELATED: self._handle_gpa_related,
            IntentType.SCHEDULE_PLANNING: self._handle_schedule_planning,
        }

    async def generate_response(
        self,
        intent: IntentType,
        question: str,
        context: Optional[TranscriptContext] = None
    ) -> Optional[str]:
        """
        Generate a rule-based response if applicable for the given intent.

        Args:
            intent: The detected intent type
            question: The original question
            context: Optional student context

        Returns:
            Response string if rule-based response is applicable, None otherwise
        """
        handler = self.responses.get(intent)
        if handler:
            try:
                return handler(question, context)
            except Exception as e:
                logger.error(f"Error in rule-based response handler: {str(e)}")
                return None
        return None

    @staticmethod
    def _handle_program_requirements(question: str, context: Optional[TranscriptContext]) -> str:
        """Handle program requirements questions"""
        student_name = context.student_name if context else "Student"
        program = context.program if context else "your program"

        # Check question specificity
        if "ms in business analytics" in question.lower():
            return f"""Based on WPI's MS in Business Analytics program requirements:

**Core Requirements:**
- 30 total credit hours required for graduation
- Minimum of 3.0 GPA required
- Must complete core analytical courses
- Electives: Choose from advanced analytics, business, or data science courses

**Core Courses (Required):**
- Business Analytics Foundations (3 credits)
- Data Mining & Analysis (3 credits)
- Probability & Statistics for Analytics (3 credits)
- Analytics Database Systems (3 credits)
- Analytics in Enterprise Systems (3 credits)

**Electives:**
- Need 15 credits from approved electives
- Can choose from courses in:
  - Advanced Analytics
  - Business Intelligence
  - Data Science
  - Supply Chain Analytics
  - Quantitative Finance

**Timeline:**
- Full-time students: 2 semesters (1 year)
- Part-time students: 3-4 semesters

Do you need information about specific course sequences or elective recommendations?"""

        elif "master's degree" in question.lower() or "ms degree" in question.lower():
            return """For WPI Master's degree programs:

**General Requirements:**
- 30 credit hours minimum
- Maintain 3.0 GPA or higher
- Complete program within 5 years
- Pass all required core courses

**Your Program: {program}**
Please check your specific program documentation or speak with your academic advisor for detailed requirements.

Would you like recommendations on course selection or more details about your specific program?"""

        else:
            return f"""To help with your program requirements question, I need more specific information.

What would you like to know about {program}?
- **Total credits needed**: How many courses/credits required for graduation?
- **Core courses**: What courses are required?
- **Electives**: What are my options for electives?
- **Timeline**: How long does the program take?
- **GPA requirements**: What GPA do I need to maintain?

Please clarify your question, and I can provide more detailed guidance."""

    @staticmethod
    def _handle_prerequisite(question: str, context: Optional[TranscriptContext]) -> str:
        """Handle prerequisite questions"""
        common_prerequisites = {
            "advanced analytics": "Business Analytics Foundations, Probability & Statistics",
            "machine learning": "Data Mining & Analysis, Probability & Statistics, Programming",
            "database": "Computer fundamentals, SQL basics",
            "statistics": "Probability & Statistics, Calculus (optional)",
            "optimization": "Linear Algebra, Statistics, Programming",
            "finance": "Probability & Statistics, Accounting basics",
        }

        # Check if question asks about specific course
        for course_key, prereqs in common_prerequisites.items():
            if course_key in question.lower():
                return f"""**Prerequisites for {course_key.title()}:**
- {prereqs.replace(', ', '\n- ')}

**Recommendation:**
If you haven't completed all prerequisites:
1. Complete prerequisite courses first
2. Consider foundational electives to strengthen your background
3. Speak with your advisor about waiving prerequisites (if eligible)

Based on your transcript, your advisor can confirm if you meet the prerequisites.
Would you like course recommendations based on your transcript?"""

        # Generic prerequisite response
        return """To check specific prerequisites, I need to know which course you're interested in.

**Common prerequisite requirements at WPI:**
- **Quantitative courses**: Probability & Statistics, Calculus, Linear Algebra
- **Data/Analytics courses**: Programming, Database fundamentals
- **Advanced courses**: Usually require foundational courses first

Please specify which course you'd like prerequisite information for, and I can provide detailed guidance."""

    @staticmethod
    def _handle_academic_progress(question: str, context: Optional[TranscriptContext]) -> str:
        """Handle academic progress questions"""
        if not context:
            return """I'd like to help you track your academic progress, but I need access to your transcript.

**To check your progress, I need:**
- Your transcript data (courses taken, grades, GPA)
- Your program requirements

Please upload your transcript, and I can provide:
- **Progress Summary**: Courses completed vs. required
- **Remaining Requirements**: What courses you still need
- **Timeline Estimate**: When you can graduate
- **Course Recommendations**: What to take next

Would you like to upload your transcript?"""

        student_name = context.student_name or "You"
        program = context.program or "your program"
        courses_taken = context.course_count or 0
        gpa = context.gpa

        progress_message = f"""**Academic Progress Summary for {student_name}**

**Current Status:**
- Program: {program}
- Courses Completed: {courses_taken}"""

        if gpa:
            progress_message += f"\n- Current GPA: {gpa:.2f}/4.0"
            status = "Excellent" if gpa >= 3.7 else "Good" if gpa >= 3.3 else "Satisfactory" if gpa >= 3.0 else "Below Target"
            progress_message += f"\n- Academic Standing: {status}"

        progress_message += """

**Next Steps:**
1. Review your completed courses
2. Identify remaining degree requirements
3. Plan your next semester courses

Would you like:
- Specific course recommendations for next semester?
- Information about remaining degree requirements?
- Help with course scheduling?"""

        return progress_message

    @staticmethod
    def _handle_gpa_related(question: str, context: Optional[TranscriptContext]) -> str:
        """Handle GPA-related questions"""
        if "improve" in question.lower() or "boost" in question.lower():
            return """**Tips to Improve Your GPA:**

1. **Course Selection:**
   - Take courses in areas of strength
   - Balance difficult courses with easier ones
   - Avoid taking too many challenging courses in one semester

2. **Study Habits:**
   - Start assignments early
   - Form study groups with classmates
   - Use office hours for difficult concepts
   - Practice problems regularly

3. **Time Management:**
   - Create a semester study schedule
   - Allocate more time for difficult courses
   - Break large projects into manageable tasks

4. **Course Strategy:**
   - Retake courses if allowed to improve grades
   - Take courses where you have background knowledge
   - Consider your course load capacity

5. **Resources:**
   - Tutoring services at WPI
   - Writing center for paper assignments
   - Course review sessions
   - Peer mentoring

**Note:** Most programs require a 3.0 GPA minimum for graduation.

Would you like specific course recommendations based on your strengths?"""

        elif context and context.gpa:
            gpa = context.gpa
            if gpa >= 3.7:
                return f"""Excellent work! Your current GPA of {gpa:.2f} is outstanding.

**To maintain/improve further:**
- Continue your current study habits
- Consider taking courses that interest you (you have strong fundamentals)
- Look for research or leadership opportunities
- Share your experience with peers

Is there anything else I can help with regarding your academic planning?"""

            elif gpa >= 3.3:
                return f"""You're doing well with a GPA of {gpa:.2f}.

**To continue improving:**
- Focus on courses related to your interests
- Dedicate more time to challenging subjects
- Consider peer tutoring for difficult concepts
- Review course material regularly

Would you like recommendations for courses that might interest you?"""

            elif gpa >= 3.0:
                return f"""You're at {gpa:.2f} GPA, which meets program requirements.

**To improve your standing:**
1. Identify your strongest subject areas
2. Take courses where you excel
3. Allocate more study time to challenging topics
4. Utilize available tutoring resources

Would you like help selecting easier courses or building stronger fundamentals?"""

            else:
                return f"""Your current GPA is {gpa:.2f}. Let's work on improvement.

**Priority Actions:**
1. Meet with academic advisor immediately
2. Identify courses that are most difficult for you
3. Reduce course load if necessary
4. Use all available academic support resources
5. Consider prerequisite refresher courses

**Program Requirement:** Minimum 3.0 GPA needed for graduation.

Would you like help creating an academic recovery plan?"""

        else:
            return """**GPA Information:**

**What affects your GPA:**
- Grade in each course
- Credit hours of each course
- Scale: A=4.0, B=3.0, C=2.0, etc.
- GPA = Total Grade Points / Total Credits

**Program Requirements:**
- Minimum 3.0 GPA required for graduation
- Academic probation: Below 2.0 GPA
- Good academic standing: 3.0+

**To check your specific GPA:**
Please upload your transcript, and I can provide detailed analysis and recommendations for improvement.

Would you like to upload your transcript?"""

    @staticmethod
    def _handle_schedule_planning(question: str, context: Optional[TranscriptContext]) -> str:
        """Handle schedule planning questions"""
        if "heavy" in question.lower() or "busy" in question.lower() or "workload" in question.lower():
            return """**Managing Heavy Workload:**

1. **Course Selection Strategy:**
   - Mix difficult and easier courses
   - Avoid taking all quantitative courses together
   - Spread out electives strategically

2. **Time Management:**
   - Block out study time daily (2-3 hours per course)
   - Identify peak productivity times
   - Use calendar for assignment deadlines

3. **Weekly Planning:**
   - Spend 3-5 hours per credit hour on study per week
   - Plan for busy weeks (exams, project deadlines)
   - Balance work and academic commitments

4. **Course Load Recommendations:**
   - Full-time: 9-12 credit hours
   - Part-time: 6-9 credit hours
   - Work while studying: 6-9 credit hours

Would you like help planning your next semester schedule?"""

        elif "balance" in question.lower() or "work" in question.lower():
            return """**Balancing Work and Studies:**

1. **Course Load Reduction:**
   - Consider 6-9 credits if working full-time
   - 9-12 credits if working part-time

2. **Course Selection:**
   - Choose flexible courses (online options if available)
   - Avoid back-to-back classes
   - Prefer asynchronous courses if available

3. **Planning Strategies:**
   - Schedule classes in specific days/times
   - Use lunch breaks for study time
   - Communicate with professors about work schedule

4. **Support Resources:**
   - Online tutoring (flexible schedule)
   - Study groups (schedule around work)
   - Extended office hours

**Time Estimate:**
- Part-time study: 8-10 hours per week per credit
- Full-time study: 5-7 hours per week per credit

Would you like recommendations for a balanced course schedule?"""

        else:
            return """**Course Scheduling Tips:**

1. **Before Selecting Courses:**
   - Review prerequisites
   - Check professor ratings and reviews
   - Consider course timing and format

2. **Building Your Schedule:**
   - Distribute workload throughout week
   - Avoid back-to-back heavy courses
   - Consider commute times

3. **Semester Planning:**
   - First semester: Build foundation with core courses
   - Middle semesters: Mix core and electives
   - Final semester: Focus on specialization

4. **Flexible Options:**
   - Online courses for flexibility
   - Evening/weekend classes if needed
   - Asynchronous formats available

Would you like specific course recommendations or help planning your next semester?"""

    @staticmethod
    def can_handle_intent(intent: IntentType) -> bool:
        """Check if rule-based system can handle this intent"""
        rule_applicable_intents = {
            IntentType.PROGRAM_REQUIREMENTS,
            IntentType.PREREQUISITE,
            IntentType.ACADEMIC_PROGRESS,
            IntentType.GPA_RELATED,
            IntentType.SCHEDULE_PLANNING,
        }
        return intent in rule_applicable_intents
