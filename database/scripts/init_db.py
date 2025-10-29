#!/usr/bin/env python3
"""
Database initialization script.

Creates tables and sets up initial schema.
"""
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from sqlalchemy import create_engine
from database.models import Base

def init_database(db_url: str = "sqlite:///database/data/mis520.db"):
    """
    Initialize the database with schema.

    Args:
        db_url: Database connection URL
    """
    print(f"[INFO] Initializing database: {db_url}")

    # Create engine
    engine = create_engine(db_url, echo=True)

    # Create all tables
    Base.metadata.create_all(engine)

    print("[SUCCESS] Database initialized successfully!")
    print(f"[INFO] Tables created: {list(Base.metadata.tables.keys())}")

if __name__ == "__main__":
    # Get database URL from environment or use default
    db_url = os.getenv("DATABASE_URL", "sqlite:///database/data/mis520.db")
    init_database(db_url)
