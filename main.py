import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from bson import ObjectId
import hashlib
import secrets

from database import db, create_document, get_documents

app = FastAPI(title="Student Management System API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Utility functions

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def to_object_id(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id format")


# Auth models
class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class SessionInfo(BaseModel):
    token: str
    user: dict


# Auth helpers
async def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = authorization.replace("Bearer ", "").strip()
    session = db["session"].find_one({"token": token})
    if not session:
        raise HTTPException(status_code=401, detail="Invalid token")
    if session.get("expires_at") and session["expires_at"] < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Token expired")
    user = db["student"].find_one({"_id": session["user_id"]})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return {"_id": str(user["_id"]), "name": user["name"], "email": user["email"], "role": user.get("role", "student")}


@app.get("/")
def read_root():
    return {"message": "Student Management System API"}


@app.get("/test")
def test_database():
    resp = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            resp["database"] = "✅ Available"
            resp["database_name"] = getattr(db, "name", "✅ Connected")
            try:
                resp["collections"] = db.list_collection_names()[:10]
                resp["database"] = "✅ Connected & Working"
                resp["connection_status"] = "Connected"
            except Exception as e:
                resp["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            resp["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        resp["database"] = f"❌ Error: {str(e)[:50]}"
    resp["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    resp["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    return resp


# Auth routes
@app.post("/auth/register", response_model=SessionInfo)
def register(payload: RegisterRequest):
    if db["student"].find_one({"email": payload.email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    student = {
        "name": payload.name,
        "email": payload.email,
        "password_hash": hash_password(payload.password),
        "role": "student",
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    res = db["student"].insert_one(student)
    user_id = res.inserted_id

    token = secrets.token_urlsafe(32)
    session = {
        "user_id": user_id,
        "token": token,
        "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
        "created_at": datetime.now(timezone.utc),
    }
    db["session"].insert_one(session)

    return {"token": token, "user": {"_id": str(user_id), "name": student["name"], "email": student["email"], "role": "student"}}


@app.post("/auth/login", response_model=SessionInfo)
def login(payload: LoginRequest):
    user = db["student"].find_one({"email": payload.email})
    if not user or user.get("password_hash") != hash_password(payload.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = secrets.token_urlsafe(32)
    session = {
        "user_id": user["_id"],
        "token": token,
        "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
        "created_at": datetime.now(timezone.utc),
    }
    db["session"].insert_one(session)
    return {"token": token, "user": {"_id": str(user["_id"]), "name": user["name"], "email": user["email"], "role": user.get("role", "student")}}


# Courses
class CourseCreate(BaseModel):
    code: str
    title: str
    description: Optional[str] = None
    instructor: Optional[str] = None
    capacity: Optional[int] = 100


@app.post("/courses")
def create_course(payload: CourseCreate, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only admin can create courses")
    if db["course"].find_one({"code": payload.code}):
        raise HTTPException(status_code=400, detail="Course code exists")
    course = payload.model_dump()
    course.update({"created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)})
    res = db["course"].insert_one(course)
    course["_id"] = str(res.inserted_id)
    return course


@app.get("/courses")
def list_courses():
    items = list(db["course"].find())
    for it in items:
        it["_id"] = str(it["_id"])
    return items


# Enrollment
class EnrollmentRequest(BaseModel):
    course_id: str


@app.post("/enroll")
def enroll_course(payload: EnrollmentRequest, user=Depends(get_current_user)):
    course = db["course"].find_one({"_id": to_object_id(payload.course_id)})
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    exists = db["enrollment"].find_one({"student_id": user["_id"], "course_id": payload.course_id})
    if exists:
        raise HTTPException(status_code=400, detail="Already enrolled")
    enrollment = {
        "student_id": user["_id"],
        "course_id": payload.course_id,
        "status": "enrolled",
        "enrolled_at": datetime.now(timezone.utc),
    }
    db["enrollment"].insert_one(enrollment)
    return {"message": "Enrolled successfully"}


@app.get("/my/courses")
def my_courses(user=Depends(get_current_user)):
    enrolls = list(db["enrollment"].find({"student_id": user["_id"]}))
    course_ids = [to_object_id(e["course_id"]) for e in enrolls]
    courses = list(db["course"].find({"_id": {"$in": course_ids}})) if course_ids else []
    for c in courses:
        c["_id"] = str(c["_id"]) 
    return courses


# Attendance
class AttendanceMarkRequest(BaseModel):
    course_id: str
    status: str = Field("present")


@app.post("/attendance/mark")
def mark_attendance(payload: AttendanceMarkRequest, user=Depends(get_current_user)):
    enrollment = db["enrollment"].find_one({"student_id": user["_id"], "course_id": payload.course_id})
    if not enrollment:
        raise HTTPException(status_code=400, detail="Not enrolled in the course")
    record = {
        "student_id": user["_id"],
        "course_id": payload.course_id,
        "date": datetime.now(timezone.utc),
        "status": payload.status,
    }
    db["attendance"].insert_one(record)
    return {"message": "Attendance marked"}


@app.get("/attendance/{course_id}")
def get_attendance(course_id: str, user=Depends(get_current_user)):
    items = list(db["attendance"].find({"student_id": user["_id"], "course_id": course_id}))
    for it in items:
        it["_id"] = str(it["_id"])
    return items


# Grades
class GradeCreate(BaseModel):
    course_id: str
    grade: float
    label: Optional[str] = None


@app.post("/grades")
def add_grade(payload: GradeCreate, user=Depends(get_current_user)):
    # For demo, allow students to add their own grades. In real app, restrict to instructor/admin.
    enrollment = db["enrollment"].find_one({"student_id": user["_id"], "course_id": payload.course_id})
    if not enrollment:
        raise HTTPException(status_code=400, detail="Not enrolled in the course")
    item = {
        "student_id": user["_id"],
        "course_id": payload.course_id,
        "grade": payload.grade,
        "label": payload.label,
        "graded_at": datetime.now(timezone.utc),
    }
    db["grade"].insert_one(item)
    return {"message": "Grade added"}


@app.get("/grades/{course_id}")
def get_grades(course_id: str, user=Depends(get_current_user)):
    items = list(db["grade"].find({"student_id": user["_id"], "course_id": course_id}))
    for it in items:
        it["_id"] = str(it["_id"])
    return items


# Extra features: announcements and progress
class AnnouncementCreate(BaseModel):
    course_id: str
    title: str
    content: str


@app.post("/announcements")
def create_announcement(payload: AnnouncementCreate, user=Depends(get_current_user)):
    # Allow admin/instructor only in real app. Here allow all enrolled students for demo.
    course = db["course"].find_one({"_id": to_object_id(payload.course_id)})
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    item = {
        "course_id": payload.course_id,
        "title": payload.title,
        "content": payload.content,
        "created_by": user["_id"],
        "created_at": datetime.now(timezone.utc),
    }
    db["announcement"].insert_one(item)
    return {"message": "Announcement posted"}


@app.get("/announcements/{course_id}")
def list_announcements(course_id: str, user=Depends(get_current_user)):
    items = list(db["announcement"].find({"course_id": course_id}).sort("created_at", -1))
    for it in items:
        it["_id"] = str(it["_id"])
    return items


@app.get("/dashboard")
def dashboard(user=Depends(get_current_user)):
    enrolls = list(db["enrollment"].find({"student_id": user["_id"]}))
    course_ids = [to_object_id(e["course_id"]) for e in enrolls]
    courses = list(db["course"].find({"_id": {"$in": course_ids}})) if course_ids else []
    for c in courses:
        c["_id"] = str(c["_id"]) 

    # Calculate simple progress stats
    progress = []
    for c in courses:
        att_count = db["attendance"].count_documents({"student_id": user["_id"], "course_id": c["_id"]})
        grade_docs = list(db["grade"].find({"student_id": user["_id"], "course_id": c["_id"]}))
        avg_grade = sum([g.get("grade", 0) for g in grade_docs]) / max(len(grade_docs), 1)
        progress.append({
            "course": c,
            "attendance_records": att_count,
            "avg_grade": avg_grade,
        })

    return {"user": user, "courses": courses, "progress": progress}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
