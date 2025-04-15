import mysql.connector
import random
from datetime import datetime, timedelta

# Database credentials
host = "127.0.0.1"
user = "root"
password = "hello@123"
database = "hrms"
port = 3306

# Connect to the database
conn = mysql.connector.connect(
    host=host,
    user=user,
    password=password,
    database=database,
    port=port
)
cursor = conn.cursor()

# Fetch all employee IDs
cursor.execute("SELECT employee_id FROM employees")
employees = [row[0] for row in cursor.fetchall()]

# Attendance date range
start_date = datetime(2025, 1, 1)
end_date = datetime(2025, 4, 1)

# Populate attendance data
for emp_id in employees:
    current_date = start_date
    monthly_offs = {}  # {(year, month): count}

    while current_date < end_date:
        year_month = (current_date.year, current_date.month)
        if year_month not in monthly_offs:
            monthly_offs[year_month] = 0

        # Default status is 'Present'
        status = 'Present'

        # Allow max 2 days off per month (Absent or On Leave)
        if monthly_offs[year_month] < 2:
            rand = random.random()
            if rand < 0.05:  # 5% chance of Absent
                status = 'Absent'
                monthly_offs[year_month] += 1
            elif rand < 0.10:  # 5% chance of On Leave
                status = 'On Leave'
                monthly_offs[year_month] += 1

        # Insert into attendance table
        cursor.execute(
            "INSERT INTO attendance (employee_id, date, status) VALUES (%s, %s, %s)",
            (emp_id, current_date.date(), status)
        )

        current_date += timedelta(days=1)

# Commit changes and close connection
conn.commit()
cursor.close()
conn.close()

print("✅ Attendance table populated successfully from 2025-01-01 to 2025-04-01.")
