"""
Database Schemas for Student Management System

Each Pydantic model represents a collection in MongoDB.
Collection name is lowercase of class name by default.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class Student(BaseModel):
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")
    password_hash: str = Field(..., description="Hashed password")
    role: str = Field("student", description="user role: student|admin")
    is_active: bool = Field(True)


class Course(BaseModel):
    code: str = Field(..., description="Course code e.g., CS101")
    title: str = Field(..., description="Course title")
    description: Optional[str] = Field(None)
    instructor: Optional[str] = Field(None)
    capacity: Optional[int] = Field(100, ge=1)


class Enrollment(BaseModel):
    student_id: str = Field(..., description="Student _id as string")
    course_id: str = Field(..., description="Course _id as string")
    status: str = Field("enrolled", description="enrolled|completed|dropped")
    enrolled_at: datetime = Field(default_factory=datetime.utcnow)


class Attendance(BaseModel):
    student_id: str
    course_id: str
    date: datetime = Field(default_factory=datetime.utcnow)
    status: str = Field("present", description="present|absent")


class Grade(BaseModel):
    student_id: str
    course_id: str
    grade: float = Field(..., ge=0, le=100)
    label: Optional[str] = Field(None, description="e.g., Midterm, Final, Assignment 1")
    graded_at: datetime = Field(default_factory=datetime.utcnow)


class Session(BaseModel):
    user_id: str
    token: str
    expires_at: datetime
