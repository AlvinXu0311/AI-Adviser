"""
Regression tests: degree audits must resolve the program the student named.

Previously "MBA", "Master of Business Administration" and (depending on set
ordering) "MSBA" all resolved to "MBA in Analytics", so plain-MBA students got
the wrong graduation requirements.
"""
import pytest

from app.services.program_db_service import get_program_db_service

CASES = [
    ("MBA", "Master of Business Administration"),
    ("mba", "Master of Business Administration"),
    ("Master of Business Administration", "Master of Business Administration"),
    ("MBA in Analytics", "MBA in Analytics : Master of Business Administration"),
    ("MSBA", "Master's in Business Analytics : Master of Science"),
    ("Business Analytics", "Master's in Business Analytics : Master of Science"),
    ("MSIT", "Master's in Information Technology"),
    ("FinTech", "Master's in Financial Technology (FinTech)"),
    ("OSCA", "Master’s in Operations & Supply Chain Analytics"),
]


@pytest.mark.parametrize("query,expected", CASES)
def test_compare_student_progress_resolves_named_program(query, expected):
    analysis = get_program_db_service().compare_student_progress(query, ["BUS 500"], [])
    assert analysis["program_name"] == expected
