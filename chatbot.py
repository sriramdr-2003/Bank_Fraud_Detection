import streamlit as st
import pyodbc
import pandas as pd
from groq import Groq

# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="Banking SQL Chatbot",
    layout="wide"
)

# =========================================================
# SESSION STATE
# =========================================================
if "messages" not in st.session_state:
    st.session_state.messages = []

# =========================================================
# SIDEBAR (LEFT PANE)
# =========================================================
with st.sidebar:
    st.markdown("## 🔐 Groq API Configuration")

    groq_api_key = st.text_input(
        "Groq API Key",
        type="password",
        placeholder="gsk_...",
        help="Paste your Groq API key here"
    )

    st.markdown("---")

    st.markdown("### 🧭 How to get your Groq API Key")

    st.markdown(
        """
**Step 1:** Open Groq Console  
👉 [Groq](https://console.groq.com/keys)

**Step 2:** Sign in with GitHub / Google  

**Step 3:** Click **Create API Key**  

**Step 4:** Copy the key and paste it above ☝️  
        """
    )

    st.info("🔒 Your API key is used only in this session and is never stored.")

    st.markdown("---")

    if st.button("🧹 Clear Chat"):
        st.session_state.messages = []
        st.rerun()

# Stop if API key missing
if not groq_api_key:
    st.warning("Please enter your Groq API key in the left panel to continue.")
    st.stop()

# =========================================================
# GROQ CLIENT
# =========================================================
client = Groq(api_key=groq_api_key)

# =========================================================
# SQL SERVER CONNECTION
# =========================================================
conn = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=localhost\\SQLEXPRESS;"
    "DATABASE=FINANCE;"
    "Trusted_Connection=yes;"
)

# =========================================================
# DATABASE SCHEMA
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
# SQL GENERATION
# =========================================================
def generate_sql(question, sql_box):
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
        max_completion_tokens=2048,
        stream=True
    )

    sql = ""
    for chunk in completion:
        sql += chunk.choices[0].delta.content or ""
        sql_box.markdown(f"```sql\n{sql}\n```")

    return sql.strip()

# =========================================================
# SQL EXECUTION (DEFENSIVE)
# =========================================================
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

# =========================================================
# RESULT EXPLANATION
# =========================================================
def explain_result(question, df, answer_box):
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
        max_completion_tokens=1024,
        stream=True
    )

    explanation = ""
    for chunk in completion:
        explanation += chunk.choices[0].delta.content or ""
        answer_box.markdown(explanation)

    return explanation

# =========================================================
# MAIN CHAT UI
# =========================================================
st.title("💬 Banking SQL Chatbot")

# Display history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Chat input
user_input = st.chat_input("Ask about customers, accounts, transactions, or orders")

if user_input:
    st.session_state.messages.append(
        {"role": "user", "content": user_input}
    )

    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        sql_box = st.empty()
        answer_box = st.empty()

        st.info("🧠 Generating SQL...")
        sql = generate_sql(user_input, sql_box)

        try:
            df = execute_sql(sql)

            with st.expander("🧾 Generated SQL"):
                st.code(sql, language="sql")

            st.dataframe(df)

            st.info("📖 Explanation")
            explanation = explain_result(user_input, df, answer_box)

            st.session_state.messages.append(
                {"role": "assistant", "content": explanation}
            )

        except Exception as e:
            error_msg = f"❌ SQL execution failed:\n\n{e}"
            st.error(error_msg)

            st.session_state.messages.append(
                {"role": "assistant", "content": error_msg}
            )
