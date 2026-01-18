import streamlit as st
import pyodbc
import pandas as pd
import smtplib
import os
from email.mime.text import MIMEText
from dotenv import load_dotenv
from groq import Groq

# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="Bank Fraud Monitoring + AI Copilot",
    page_icon="🚨",
    layout="wide"
)

# =========================================================
# SESSION STATE
# =========================================================
if "view_mode" not in st.session_state:
    st.session_state.view_mode = "DASHBOARD"  # or CHATBOT

if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []

# =========================================================
# LOAD ENV (EMAIL)
# =========================================================
load_dotenv()

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

# =========================================================
# EMAIL FUNCTION
# =========================================================
def send_email(subject, body):
    msg = MIMEText(body, "html")
    msg["From"] = SMTP_USER
    msg["To"] = SMTP_USER
    msg["Subject"] = subject

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)

# =========================================================
# SQL SERVER CONNECTION
# =========================================================
conn = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=localhost\\SQLEXPRESS;"
    "DATABASE=FINANCE;"
    "Trusted_Connection=yes;"
)

def load_df(query):
    return pd.read_sql(query, conn)

# =========================================================
# DATABASE SCHEMA (CHATBOT)
# =========================================================
schema_info = """
TABLE accounts (
  account_id UNIQUEIDENTIFIER,
  customer_id UNIQUEIDENTIFIER,
  account_status VARCHAR,
  risk_score INT,
  daily_txn_limit DECIMAL,
  created_at DATETIME
)

TABLE customers (
  customer_id UNIQUEIDENTIFIER,
  full_name VARCHAR,
  email VARCHAR,
  created_at DATETIME
)

TABLE orders (
  order_id INT,
  customer_name VARCHAR,
  order_amount DECIMAL,
  order_date DATETIME
)

TABLE transactions (
  txn_id UNIQUEIDENTIFIER,
  account_id UNIQUEIDENTIFIER,
  amount DECIMAL,
  txn_type VARCHAR,
  merchant_country VARCHAR,
  device_id VARCHAR,
  txn_timestamp DATETIME
)
"""

# =========================================================
# CHATBOT FUNCTIONS
# =========================================================
def generate_sql(client, question, sql_box):
    prompt = f"""
You are a senior SQL Server expert.

Database schema:
{schema_info}

User question:
{question}

Rules:
- Use ONLY columns defined in the schema
- SQL Server SELECT queries ONLY
- NEVER use LIMIT
- Use TOP 100 if needed
- Do NOT use backticks or ```sql
- Always CAST aggregates to FLOAT
- Always alias computed columns
- Infer failures using amount < 0 if needed
Return ONLY SQL.
"""

    completion = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        stream=True
    )

    sql = ""
    for chunk in completion:
        sql += chunk.choices[0].delta.content or ""
        sql_box.markdown(f"```sql\n{sql}\n```")

    return sql.strip()

def execute_sql(sql):
    cursor = conn.cursor()
    cursor.execute(sql)
    rows = cursor.fetchall()
    if not rows:
        return pd.DataFrame()

    columns = [col[0] for col in cursor.description]
    if len(rows[0]) != len(columns):
        columns = columns[:len(rows[0])]

    return pd.DataFrame.from_records(rows, columns=columns)

def explain_result(client, question, df, answer_box):
    prompt = f"""
User question:
{question}

SQL result:
{df.to_dict(orient="records")}

Explain the answer in simple banking terms.
"""

    completion = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        stream=True
    )

    explanation = ""
    for chunk in completion:
        explanation += chunk.choices[0].delta.content or ""
        answer_box.markdown(explanation)

    return explanation

# =========================================================
# TOP ACTION BAR
# =========================================================
c1, c2 = st.columns([6, 1])

with c1:
    if st.session_state.view_mode == "DASHBOARD":
        st.title("🚨 Bank Fraud Monitoring Dashboard")
    else:
        st.title("🤖 AI SQL Copilot")

with c2:
    if st.session_state.view_mode == "DASHBOARD":
        if st.button("🤖 Open AI Copilot"):
            st.session_state.view_mode = "CHATBOT"
            st.rerun()
    else:
        if st.button("⬅ Back to Dashboard"):
            st.session_state.view_mode = "DASHBOARD"
            st.rerun()

st.divider()

# =========================================================
# DASHBOARD VIEW
# =========================================================
if st.session_state.view_mode == "DASHBOARD":

    kpi_df = load_df("""
        SELECT
            COUNT(*) AS total_accounts,
            SUM(CASE WHEN account_status = 'FROZEN' THEN 1 ELSE 0 END) AS frozen_accounts,
            SUM(CASE WHEN risk_score >= 60 THEN 1 ELSE 0 END) AS high_risk_accounts
        FROM accounts
    """)

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Accounts", int(kpi_df.total_accounts[0]))
    c2.metric("Frozen Accounts", int(kpi_df.frozen_accounts[0]))
    c3.metric("High Risk Accounts (≥60)", int(kpi_df.high_risk_accounts[0]))

    st.subheader("🏦 Accounts Overview")

    accounts_df = load_df("""
        SELECT
            c.full_name AS customer_name,
            a.account_id,
            a.account_status,
            a.risk_score,
            a.daily_txn_limit
        FROM customers c
        JOIN accounts a ON c.customer_id = a.customer_id
        ORDER BY a.risk_score DESC
    """)
    st.dataframe(accounts_df, use_container_width=True)

    tab1, tab2 = st.tabs(["🚩 Fraud Alerts", "🔔 Notifications"])

    with tab1:
        st.dataframe(load_df("SELECT * FROM fraud_alerts ORDER BY created_at DESC"))

    with tab2:
        st.dataframe(load_df("SELECT * FROM notification_queue ORDER BY created_at DESC"))

    # -------------------------------------------------
    # TRANSACTION SIMULATOR
    # -------------------------------------------------
    st.subheader("🧪 Transaction Simulator")

    active_accounts = accounts_df[accounts_df.account_status == "ACTIVE"]

    with st.form("txn_form"):
        customer = st.selectbox(
            "Select Customer",
            active_accounts["customer_name"].tolist()
        )

        account_id = active_accounts[
            active_accounts.customer_name == customer
        ]["account_id"].values[0]

        amount = st.number_input("Amount", min_value=1, step=100)
        txn_type = st.selectbox("Transaction Type", ["POS", "ATM", "TRANSFER"])

        submit = st.form_submit_button("Submit Transaction")

        if submit:
            try:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO transactions (
                        txn_id,
                        account_id,
                        amount,
                        txn_type,
                        merchant_country,
                        device_id,
                        txn_timestamp
                    )
                    VALUES (
                        NEWID(),
                        ?,
                        ?,
                        ?,
                        'IN',
                        'streamlit_ui',
                        GETDATE()
                    )
                """, (account_id, amount, txn_type))
                conn.commit()
                st.success(f"Transaction submitted for {customer}")
            except Exception as e:
                st.error("Transaction failed")
                st.code(str(e))
# =========================================================
# CHATBOT VIEW (FULL SCREEN)
# =========================================================
else:
    st.markdown("### 🔐 Groq API Key")
    groq_api_key = st.text_input(
        "Enter your Groq API Key",
        type="password",
        placeholder="gsk_..."
    )

    st.markdown("Get API key 👉 [Groq](https://console.groq.com/keys)")

    if not groq_api_key:
        st.info("Enter API key to start chatting")
        st.stop()

    client = Groq(api_key=groq_api_key)

    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_input = st.chat_input("Ask about fraud, risk, transactions, customers...")

    if user_input:
        # 1️⃣ SHOW USER MESSAGE IMMEDIATELY
        with st.chat_message("user"):
            st.markdown(user_input)

        st.session_state.chat_messages.append(
            {"role": "user", "content": user_input}
        )

        # 2️⃣ ASSISTANT RESPONSE
        with st.chat_message("assistant"):
            sql_box = st.empty()
            answer_box = st.empty()

            try:
                sql = generate_sql(client, user_input, sql_box)
                df = execute_sql(sql)

                with st.expander("🧾 Generated SQL"):
                    st.code(sql, language="sql")

                st.dataframe(df, use_container_width=True)

                explanation = explain_result(client, user_input, df, answer_box)

                st.session_state.chat_messages.append(
                    {"role": "assistant", "content": explanation}
                )

            except Exception as e:
                error_msg = f"❌ SQL execution failed:\n\n{e}"
                st.error(error_msg)

                st.session_state.chat_messages.append(
                    {"role": "assistant", "content": error_msg}
                )
                
