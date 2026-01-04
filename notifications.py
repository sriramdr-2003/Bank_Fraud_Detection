import pyodbc
import time

# SQL Server connection
conn = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=Sriram_DR\SQLEXPRESS;"
    "DATABASE=FINANCE;"
    "Trusted_Connection=yes;"
)

conn.autocommit = True
cursor = conn.cursor()

def send_email(account_id, message):
    print(f"[EMAIL SENT] Account: {account_id} | Message: {message}")

while True:
    cursor.execute("""
        SELECT notification_id, account_id, message
        FROM notification_queue
        WHERE processed = 0
        ORDER BY created_at
    """)

    rows = cursor.fetchall()

    for row in rows:
        notification_id = row.notification_id
        account_id = row.account_id
        message = row.message

        send_email(account_id, message)

        cursor.execute("""
            UPDATE notification_queue
            SET processed = 1
            WHERE notification_id = ?
        """, notification_id)

    time.sleep(5)
