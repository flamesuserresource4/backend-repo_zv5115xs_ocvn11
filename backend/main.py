from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import os
import secrets

from pymongo import MongoClient
from bson import ObjectId

from schemas import Student, Course, Enrollment, Attendance, Grade, Session, Announcement

app = FastAPI(title="Student Management System")

# CORS
frontend_origin = os.getenv("FRONTEND_URL", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "smsdb")
client = MongoClient(DATABASE_URL)
db = client[DATABASE_NAME]

# Helpers

def to_dict(doc):
    if not doc:
        return doc
    doc["_id"] = str(doc["_id"])  # type: ignore
    return doc

async def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    sess = db.session.find_one({"token": token, "expires_at": {"$gt": datetime.utcnow()}})
    if not sess:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = db.student.find_one({"_id": ObjectId(sess["student_id"])})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return to_dict(user)

# Schemas for requests
class RegisterBody(BaseModel):
    name: str
    email: str
    password: str

class LoginBody(BaseModel):
    email: str
    password: str

class EnrollBody(BaseModel):
    course_id: str

class AttendanceBody(BaseModel):
    course_id: str
    status: str

class GradeBody(BaseModel):
    course_id: str
    grade: float
    label: Optional[str] = None

class AnnouncementBody(BaseModel):
    course_id: str
    title: str
    content: str

# Auth endpoints
@app.post("/auth/register")
def register(body: RegisterBody):
    existing = db.student.find_one({"email": body.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    student = Student(name=body.name, email=body.email, password=body.password).dict()
    res = db.student.insert_one(student)
    student["_id"] = str(res.inserted_id)
    token = secrets.token_hex(24)
    session = Session(student_id=student["_id"], token=token, expires_at=datetime.utcnow() + timedelta(days=7)).dict()
    db.session.insert_one(session)
    return {"token": token, "user": {"_id": student["_id"], "name": student["name"], "email": student["email"], "role": student.get("role", "student")}}

@app.post("/auth/login")
def login(body: LoginBody):
    user = db.student.find_one({"email": body.email, "password": body.password})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = secrets.token_hex(24)
    session = Session(student_id=str(user["_id"]), token=token, expires_at=datetime.utcnow() + timedelta(days=7)).dict()
    db.session.insert_one(session)
    return {"token": token, "user": {"_id": str(user["_id"]), "name": user["name"], "email": user["email"], "role": user.get("role", "student")}}

# Courses
@app.post("/courses")
def create_course(course: Course, user=Depends(get_current_user)):
    # For now allow any logged-in user to create; can restrict to admin later
    data = course.dict()
    res = db.course.insert_one(data)
    data["_id"] = str(res.inserted_id)
    return data

@app.get("/courses")
def list_courses():
    return [to_dict(c) for c in db.course.find().sort("created_at", -1)]

# Enrollment
@app.post("/enroll")
def enroll(body: EnrollBody, user=Depends(get_current_user)):
    course = db.course.find_one({"_id": ObjectId(body.course_id)})
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    exists = db.enrollment.find_one({"student_id": user["_id"], "course_id": body.course_id})
    if exists:
        return to_dict(exists)
    enr = Enrollment(student_id=user["_id"], course_id=body.course_id).dict()
    res = db.enrollment.insert_one(enr)
    enr["_id"] = str(res.inserted_id)
    return enr

@app.get("/my/courses")
def my_courses(user=Depends(get_current_user)):
    course_ids = [e["course_id"] for e in db.enrollment.find({"student_id": user["_id"]})]
    items = []
    for cid in course_ids:
        c = db.course.find_one({"_id": ObjectId(cid)})
        if c:
            items.append(to_dict(c))
    return items

# Attendance
@app.post("/attendance/mark")
def mark_attendance(body: AttendanceBody, user=Depends(get_current_user)):
    course = db.course.find_one({"_id": ObjectId(body.course_id)})
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    att = Attendance(student_id=user["_id"], course_id=body.course_id, status=body.status).dict()
    res = db.attendance.insert_one(att)
    att["_id"] = str(res.inserted_id)
    return att

@app.get("/attendance/{course_id}")
def list_attendance(course_id: str, user=Depends(get_current_user)):
    recs = db.attendance.find({"student_id": user["_id"], "course_id": course_id}).sort("date", -1)
    return [to_dict(r) for r in recs]

# Grades
@app.post("/grades")
def add_grade(body: GradeBody, user=Depends(get_current_user)):
    # For demo allow student to add; later restrict to instructor
    course = db.course.find_one({"_id": ObjectId(body.course_id)})
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    g = Grade(student_id=user["_id"], course_id=body.course_id, grade=body.grade, label=body.label).dict()
    res = db.grade.insert_one(g)
    g["_id"] = str(res.inserted_id)
    return g

@app.get("/grades/{course_id}")
def list_grades(course_id: str, user=Depends(get_current_user)):
    items = db.grade.find({"student_id": user["_id"], "course_id": course_id}).sort("created_at", -1)
    return [to_dict(i) for i in items]

# Announcements
@app.post("/announcements")
def add_announcement(body: AnnouncementBody, user=Depends(get_current_user)):
    course = db.course.find_one({"_id": ObjectId(body.course_id)})
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    a = Announcement(course_id=body.course_id, title=body.title, content=body.content).dict()
    res = db.announcement.insert_one(a)
    a["_id"] = str(res.inserted_id)
    return a

@app.get("/announcements/{course_id}")
def list_announcements(course_id: str, user=Depends(get_current_user)):
    items = db.announcement.find({"course_id": course_id}).sort("created_at", -1)
    return [to_dict(i) for i in items]

# Dashboard
@app.get("/dashboard")
def dashboard(user=Depends(get_current_user)):
    enrollments = list(db.enrollment.find({"student_id": user["_id"]}))
    progress = []
    for e in enrollments:
        cid = e["course_id"]
        course = db.course.find_one({"_id": ObjectId(cid)})
        if not course:
            continue
        at_count = db.attendance.count_documents({"student_id": user["_id"], "course_id": cid})
        grades = list(db.grade.find({"student_id": user["_id"], "course_id": cid}))
        avg = sum([g.get("grade", 0) for g in grades]) / len(grades) if grades else 0
        progress.append({
            "course": to_dict(course),
            "attendance_records": at_count,
            "avg_grade": avg,
        })
    return {"progress": progress}

# Demo seed
@app.post("/seed")
def seed():
    if db.course.count_documents({}) > 0:
        return {"message": "Already seeded"}
    demo_courses = [
        Course(title="Intro to Programming", code="CS101", description="Learn Python basics", instructor="Dr. Ada").dict(),
        Course(title="Data Structures", code="CS201", description="Arrays, Trees, Graphs", instructor="Dr. Knuth").dict(),
        Course(title="Databases", code="CS301", description="SQL/NoSQL fundamentals", instructor="Dr. Codd").dict(),
    ]
    db.course.insert_many(demo_courses)
    return {"message": "Seeded", "count": len(demo_courses)}

@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}
