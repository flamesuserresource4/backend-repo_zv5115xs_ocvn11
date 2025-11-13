from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

# Each class name determines collection: class User -> "user"

class Student(BaseModel):
    name: str
    email: str
    password: str
    role: str = "student"  # can be admin/instructor later
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Course(BaseModel):
    title: str
    code: str
    description: Optional[str] = None
    instructor: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Enrollment(BaseModel):
    student_id: str
    course_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Attendance(BaseModel):
    student_id: str
    course_id: str
    date: datetime = Field(default_factory=datetime.utcnow)
    status: str = Field(regex="^(present|absent)$")

class Grade(BaseModel):
    student_id: str
    course_id: str
    grade: float
    label: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Session(BaseModel):
    student_id: str
    token: str
    expires_at: datetime
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Announcement(BaseModel):
    course_id: str
    title: str
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
