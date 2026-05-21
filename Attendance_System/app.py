from flask import Flask, render_template, request, redirect, url_for
import sqlite3
from datetime import date, datetime, timedelta

app = Flask(__name__)
DATABASE = "database.db"

# ---------------- DATABASE CONNECTION ----------------
def get_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# ---------------- DATABASE INIT ----------------
def init_db():
    with get_connection() as conn:
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course TEXT NOT NULL,
                year TEXT NOT NULL,
                batch TEXT NOT NULL,
                roll INTEGER NOT NULL,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                contact TEXT NOT NULL
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS teachers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                subject TEXT NOT NULL
            )
        """)


        cur.execute("""
            CREATE TABLE IF NOT EXISTS student_attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER,
                status TEXT NOT NULL,
                attendance_date TEXT NOT NULL,
                lecture_type TEXT,
                lecture_number INTEGER,
                UNIQUE(student_id, attendance_date, lecture_type, lecture_number),
                FOREIGN KEY(student_id) REFERENCES students(id)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS teacher_attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id INTEGER,
                status TEXT NOT NULL,
                attendance_date TEXT NOT NULL,
                UNIQUE(teacher_id, attendance_date),
                FOREIGN KEY(teacher_id) REFERENCES teachers(id)
            )
        """)

init_db()


# Base courses are defined only here; templates use this list only.
BASE_COURSES = ["BCom", "BAF", "BSc IT", "CS"]

def get_all_courses():
    """Returns base courses + any extra courses added via 'Other'."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT course FROM students")
        db_courses = [row['course'] for row in cur.fetchall()]
    all_courses = list(BASE_COURSES)
    for c in db_courses:
        if c not in all_courses:
            all_courses.append(c)
    return all_courses


# ---------------- DASHBOARD ----------------
@app.route('/')
def dashboard():
    conn = get_connection()
    cur = conn.cursor()

    today = date.today().isoformat()

    # Students
    cur.execute("SELECT COUNT(*) FROM students")
    total_students = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(DISTINCT student_id) FROM student_attendance
        WHERE attendance_date=? AND status='Present'
    """, (today,))
    students_present = cur.fetchone()[0]

    
    student_percent = round((students_present / total_students) * 100, 2) if total_students else 0

    # Teachers
    cur.execute("SELECT COUNT(*) FROM teachers")
    total_teachers = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(*) FROM teacher_attendance
        WHERE attendance_date=? AND status='Present'
    """, (today,))
    teachers_present = cur.fetchone()[0]

    teacher_percent = round((teachers_present / total_teachers) * 100, 2) if total_teachers else 0

    conn.close()

    return render_template(
        'dashboard.html',
        total_students=total_students,
        total_teachers=total_teachers,
        student_percent=student_percent,
        teacher_percent=teacher_percent
    )


# ---------------- ADD STUDENT ----------------
@app.route('/add-student', methods=['GET', 'POST'])
def add_student():
    message = ""
    courses = get_all_courses() 

    if request.method == 'POST':
        course = request.form.get('course')
        other_course = request.form.get('other_course', '').strip()
        year = request.form.get('year')
        batch = request.form.get('batch')
        roll = request.form.get('roll')
        name = request.form.get('name')
        email = request.form.get('email')
        contact = request.form.get('contact')

        if course == "Other":
            course = other_course

        if not contact.isdigit() or len(contact) != 10:
            message = "Contact number must be exactly 10 digits"
        else:
            with get_connection() as conn:
                conn.execute("""
                    INSERT INTO students
                    (course, year, batch, roll, name, email, contact)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (course.strip(), year.strip(), batch.strip(),
                      int(roll), name.strip(), email.strip(), contact))
                conn.commit()

            message = "Student added successfully"
            courses = get_all_courses()  

    return render_template("add_student.html", message=message, courses=courses)


# ---------------- ADD TEACHER ----------------
@app.route('/add-teacher', methods=['GET', 'POST'])
def add_teacher():
    message = ""

    if request.method == 'POST':
        name = request.form.get('name')
        subject = request.form.get('subject')

        if not name or not subject:
            message = "All fields are required"
        else:
            with get_connection() as conn:
                conn.execute("""
                    INSERT INTO teachers (name, subject)
                    VALUES (?, ?)
                """, (name, subject))
            message = "Teacher added successfully"

    return render_template("add_teacher.html", message=message)


# ---------------- MARK STUDENT ATTENDANCE ----------------
@app.route('/mark_student_attendance', methods=['GET', 'POST'])
def mark_student_attendance():
    students = []
    courses = get_all_courses()  
    message = ""

    sel_course = sel_year = sel_batch = sel_date = ""
    sel_lecture_type = "Lecture"
    sel_lecture_number = ""

    if request.method == 'POST':
        action = request.form.get('action')
        sel_course = request.form.get('course', '')
        sel_year = request.form.get('year', '')
        sel_batch = request.form.get('batch', '')
        sel_date = request.form.get('date', '')
        sel_lecture_type = request.form.get('lecture_type', 'Lecture')
        sel_lecture_number = request.form.get('lecture_number', '')

        if action == 'fetch':
            with get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT * FROM students
                    WHERE TRIM(course)=? AND TRIM(year)=? AND TRIM(batch)=?
                    ORDER BY roll ASC
                """, (sel_course, sel_year, sel_batch))
                students = cur.fetchall()

            return render_template("mark_student_attendance.html",
                                   students=students, courses=courses,
                                   sel_course=sel_course, sel_year=sel_year,
                                   sel_batch=sel_batch, sel_date=sel_date,
                                   sel_lecture_type=sel_lecture_type,
                                   sel_lecture_number=sel_lecture_number,
                                   message=message)

        elif action == 'save':
            
            with get_connection() as conn:
                cur = conn.cursor()

                for key in request.form:
                    if key.startswith('status_'):
                        sample_id = key.split('_')[1]
                        break
                else:
                    sample_id = None

                already_marked = False
                if sample_id and sel_lecture_number:
                    cur.execute("""
                        SELECT COUNT(*) FROM student_attendance
                        WHERE student_id=? AND attendance_date=?
                        AND lecture_type=? AND lecture_number=?
                    """, (sample_id, sel_date, sel_lecture_type, int(sel_lecture_number)))
                    already_marked = cur.fetchone()[0] > 0

                if already_marked:
                   
                    cur.execute("""
                        SELECT * FROM students
                        WHERE TRIM(course)=? AND TRIM(year)=? AND TRIM(batch)=?
                        ORDER BY roll ASC
                    """, (sel_course, sel_year, sel_batch))
                    students = cur.fetchall()
                    message = "⚠️ Attendance for this class, date and lecture is already marked!"
                    return render_template("mark_student_attendance.html",
                                           students=students, courses=courses,
                                           sel_course=sel_course, sel_year=sel_year,
                                           sel_batch=sel_batch, sel_date=sel_date,
                                           sel_lecture_type=sel_lecture_type,
                                           sel_lecture_number=sel_lecture_number,
                                           message=message)

                # Save attendance
                for key in request.form:
                    if key.startswith('status_'):
                        student_id = key.split('_')[1]
                        status = request.form.get(key)
                        cur.execute("""
                            INSERT OR REPLACE INTO student_attendance
                            (student_id, status, attendance_date, lecture_type, lecture_number)
                            VALUES (?, ?, ?, ?, ?)
                        """, (student_id, status, sel_date,
                              sel_lecture_type,
                              int(sel_lecture_number) if sel_lecture_number else None))
                conn.commit()

            return redirect(url_for('dashboard'))

    return render_template("mark_student_attendance.html",
                           students=students, courses=courses,
                           sel_course=sel_course, sel_year=sel_year,
                           sel_batch=sel_batch, sel_date=sel_date,
                           sel_lecture_type=sel_lecture_type,
                           sel_lecture_number=sel_lecture_number,
                           message=message)


# ---------------- MARK TEACHER ATTENDANCE ----------------
@app.route('/mark_teacher_attendance', methods=['GET', 'POST'])
def mark_teacher_attendance():
    conn = get_connection()
    cur = conn.cursor()
    message = ""

    if request.method == 'POST':
        attendance_date = request.form.get('attendance_date', '').strip()

        
        if not attendance_date:
            cur.execute("SELECT * FROM teachers")
            teachers = cur.fetchall()
            conn.close()
            return render_template('mark_teacher_attendance.html',
                                   teachers=teachers,
                                   message="⚠️ Please select a date before saving.")

        
        cur.execute("""
            SELECT COUNT(*) FROM teacher_attendance WHERE attendance_date=?
        """, (attendance_date,))
        already_marked = cur.fetchone()[0] > 0

        cur.execute("SELECT * FROM teachers")
        teachers = cur.fetchall()

        if already_marked:
            conn.close()
            return render_template('mark_teacher_attendance.html',
                                   teachers=teachers,
                                   message=f"⚠️ Teacher attendance for {attendance_date} is already marked!")

        for teacher in teachers:
            status = request.form.get(f"status_{teacher['id']}", "Absent")
            cur.execute("""
                INSERT OR REPLACE INTO teacher_attendance
                (teacher_id, status, attendance_date)
                VALUES (?, ?, ?)
            """, (teacher['id'], status, attendance_date))

        conn.commit()
        conn.close()
        return redirect(url_for('dashboard'))

    cur.execute("SELECT * FROM teachers")
    teachers = cur.fetchall()
    conn.close()

    return render_template('mark_teacher_attendance.html',
                           teachers=teachers, message=message)


# ---------------- REPORTS ----------------
@app.route('/reports', methods=['GET', 'POST'])
def reports():
    conn = get_connection()
    cur = conn.cursor()

    courses = get_all_courses() 

    report_data = []
    sel_course = sel_year = sel_batch = ""

    if request.method == 'POST':
        sel_course = request.form.get('course')
        sel_year = request.form.get('year')
        sel_batch = request.form.get('batch')

        cur.execute("""
            SELECT * FROM students
            WHERE course=? AND year=? AND batch=?
            ORDER BY roll
        """, (sel_course, sel_year, sel_batch))
        students = cur.fetchall()

        today = datetime.today().date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)

        for student in students:
            sid = student['id']

            cur.execute("SELECT COUNT(*) FROM student_attendance WHERE student_id=?", (sid,))
            total = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM student_attendance WHERE student_id=? AND status='Present'", (sid,))
            present = cur.fetchone()[0]

            cur.execute("""
                SELECT COUNT(*) FROM student_attendance
                WHERE student_id=? AND status='Present' AND attendance_date >= ?
            """, (sid, week_ago))
            weekly_present = cur.fetchone()[0]

            cur.execute("""
                SELECT COUNT(*) FROM student_attendance
                WHERE student_id=? AND attendance_date >= ?
            """, (sid, week_ago))
            weekly_total = cur.fetchone()[0]

            cur.execute("""
                SELECT COUNT(*) FROM student_attendance
                WHERE student_id=? AND status='Present' AND attendance_date >= ?
            """, (sid, month_ago))
            monthly_present = cur.fetchone()[0]

            cur.execute("""
                SELECT COUNT(*) FROM student_attendance
                WHERE student_id=? AND attendance_date >= ?
            """, (sid, month_ago))
            monthly_total = cur.fetchone()[0]

            
            overall_percent  = round((present        / total)         * 100, 2) if total         else 0
            weekly_percent   = round((weekly_present / weekly_total)  * 100, 2) if weekly_total  else 0
            monthly_percent  = round((monthly_present/ monthly_total) * 100, 2) if monthly_total else 0

            report_data.append({
                'roll':    student['roll'],
                'name':    student['name'],
                'total':   total,
                'present': present,
                'overall': overall_percent,
                'weekly':  weekly_percent,
                'monthly': monthly_percent
            })

    conn.close()

    return render_template(
        'reports.html',
        report_data=report_data,
        courses=courses,
        sel_course=sel_course,
        sel_year=sel_year,
        sel_batch=sel_batch
    )


# ---------------- RUN APP ----------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
