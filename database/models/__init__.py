"""
Database models package.

This package contains SQLAlchemy model definitions for the application.
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

# Import models here when created
# from .student import Student
# from .course import Course
# from .transcript import Transcript
