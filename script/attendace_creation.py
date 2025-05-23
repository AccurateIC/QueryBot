import sqlite3
from faker import Faker
import random
from datetime import datetime, timedelta

# Setup
fake = Faker()
Faker.seed(0)
random.seed(0)
conn = sqlite3.connect("hrms.db")
cursor = conn.cursor()

# Create Tables
cursor.executescript("""
DROP TABLE IF EXISTS employees;
DROP TABLE IF EXISTS departments;
DROP TABLE IF EXISTS roles;
DROP TABLE IF EXISTS salaries;
DROP TABLE IF EXISTS attendance;

CREATE TABLE departments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT UNIQUE NOT NULL
);

CREATE TABLE employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT,
    last_name TEXT,
    email TEXT UNIQUE,
    department_id INTEGER,
    role_id INTEGER,
    hire_date TEXT,
    FOREIGN KEY(department_id) REFERENCES departments(id),
    FOREIGN KEY(role_id) REFERENCES roles(id)
);

CREATE TABLE salaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER,
    salary INTEGER,
    effective_from TEXT,
    FOREIGN KEY(employee_id) REFERENCES employees(id)
);

CREATE TABLE attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER,
    date TEXT,
    status TEXT,
    FOREIGN KEY(employee_id) REFERENCES employees(id)
);
""")

# Static Departments and Roles
departments = ["Engineering", "Sales", "Marketing", "HR", "Finance", "Support", "Operations", "IT"]
roles = ["Engineer", "Manager", "HR Specialist", "Sales Rep", "Accountant", "IT Admin", "Data Analyst", "Executive"]

cursor.executemany("INSERT INTO departments (name) VALUES (?)", [(d,) for d in departments])
cursor.executemany("INSERT INTO roles (title) VALUES (?)", [(r,) for r in roles])
conn.commit()

# Generate Employees
unique_names = set()
employee_data = []

while len(employee_data) < 500:
    first, last = fake.first_name(), fake.last_name()
    name_key = f"{first} {last}"
    if name_key in unique_names:
        continue
    unique_names.add(name_key)
    email = f"{first.lower()}.{last.lower()}@example.com"
    dept_id = random.randint(1, len(departments))
    role_id = random.randint(1, len(roles))
    hire_date = fake.date_between(start_date="-3y", end_date="today").isoformat()
    employee_data.append((first, last, email, dept_id, role_id, hire_date))

cursor.executemany("""
    INSERT INTO employees (first_name, last_name, email, department_id, role_id, hire_date)
    VALUES (?, ?, ?, ?, ?, ?)
""", employee_data)
conn.commit()

# Salaries
salary_data = []
for emp_id in range(1, 501):
    salary = random.randint(30000, 120000)
    effective_from = fake.date_between(start_date="-2y", end_date="today").isoformat()
    salary_data.append((emp_id, salary, effective_from))

cursor.executemany("""
    INSERT INTO salaries (employee_id, salary, effective_from)
    VALUES (?, ?, ?)
""", salary_data)
conn.commit()

# Attendance
start_date = datetime.strptime("2025-01-01", "%Y-%m-%d")
end_date = datetime.now()
days = (end_date - start_date).days + 1
status_choices = ["Present", "Absent", "Remote", "Leave"]

attendance_records = []
for emp_id in range(1, 501):
    for i in range(days):
        current_date = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
        status = random.choices(status_choices, weights=[85, 5, 5, 5], k=1)[0]
        attendance_records.append((emp_id, current_date, status))

# Chunk insert to avoid memory issues
chunk_size = 10000
for i in range(0, len(attendance_records), chunk_size):
    cursor.executemany("""
        INSERT INTO attendance (employee_id, date, status)
        VALUES (?, ?, ?)
    """, attendance_records[i:i + chunk_size])
    conn.commit()

print("✅ HRMS database 'hrms.db' generated successfully with 500 employees and full attendance records.")
