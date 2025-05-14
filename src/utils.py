import mysql.connector
import streamlit as st
import re
import json
import yaml
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
import io
import requests
from langchain_community.chat_models import ChatOllama
from langchain.schema import LLMResult
from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, AIMessage
from sql_metadata import Parser

from schema_fetch import get_database_metadata

# === CONFIG LOAD ===
def load_config(path: str = "/home/chirag/Documents/QueryBot/config/config.yaml") -> Dict:
    with open(path, "r") as file:
        return yaml.safe_load(file)

config = load_config()

# === EVENT LOGGING ===
@dataclass
class Event:
    event: str
    timestamp: str
    text: str

def _current_time() -> str:
    return datetime.now(timezone.utc).isoformat()

class LLMCallbackHandler(BaseCallbackHandler):
    def __init__(self, log_path: Path):
        self.log_path = log_path

    def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any) -> Any:
        assert len(prompts) == 1
        event = Event(event="llm_start", timestamp=_current_time(), text=prompts[0])
        with self.log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(asdict(event)) + "\n")

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> Any:
        generation = response.generations[-1][-1].message.content
        event = Event(event="llm_end", timestamp=_current_time(), text=generation)
        with self.log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(asdict(event)) + "\n")

# === LLM INITIALIZATION ===
def initialize_llm() -> ChatOllama:
    return ChatOllama(
        model=config["llm"]["model"],
        base_url=config["llm"]["base_url"],
        callbacks=[LLMCallbackHandler(Path(config["llm"]["log_path"]))]
    )

# === DATABASE CONNECTION ===
def connect_database(host: str, user: str, password: str, database: str, port: int) -> None:
    try:
        connection = mysql.connector.connect(
            host=host,
            user=user,
            password=password,
            database=database,
            port=int(port)
        )
        cursor = connection.cursor(dictionary=True)
        st.session_state.db = (connection, cursor)
        st.session_state.conversation_history = []
        st.success("✅ Database connected successfully!")
    except mysql.connector.Error as e:
        st.error(f"❌ Failed to connect: {e}")

# === ROLE-BASED ACCESS CHECK ===
def check_role_permissions(query: str) -> Tuple[bool, Optional[str]]:
    role = st.session_state.get("role", "employee")
    restricted = config.get("roles", {}).get(role, {}).get("restricted_columns", [])

    parser = Parser(query)
    queried_columns = parser.columns_dict.get("select", [])

    for column in queried_columns:
        if column in restricted:
            return False, f"Access to column '{column}' is restricted for your role ({role})."
    return True, None

# === RUN SQL ===
def run_query(query: str) -> Tuple[Optional[List[Dict]], Optional[str]]:
    is_allowed, error = check_role_permissions(query)
    if not is_allowed:
        return None, f"⛔️ {error}"

    try:
        if "db" in st.session_state and st.session_state.db:
            connection, cursor = st.session_state.db
            cursor.execute(query)
            result = cursor.fetchall()
            return result, None
        return None, "⚠️ Please connect to the database first."
    except mysql.connector.Error as e:
        return None, f"❌ Error executing query: {e}"

def format_query_result(result: List[Dict]) -> str:
    if not result:
        return "ℹ️ No results found."
    table_headers = result[0].keys()
    table_rows = [list(row.values()) for row in result]
    formatted_result = f"**Query Results:**\n\n| " + " | ".join(table_headers) + " |\n| " + " | ".join(["---"] * len(table_headers)) + " |\n"
    for row in table_rows:
        formatted_result += "| " + " | ".join(str(cell) for cell in row) + " |\n"
    return formatted_result

def extract_sql_query(text: str) -> str:
    think_end = text.find("</think>")
    if think_end != -1:
        text = text[think_end + len("</think>"):]
    match = re.search(r"```sql\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    match = re.search(r"SQL query:\s*(SELECT .*?;)", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text.strip()

# === MAIN SQL LLM FUNCTION ===
def get_llm_response(question: str, maintain_context: bool = True) -> Tuple[str, Optional[List[Dict]]]:
    if "conversation_history" not in st.session_state:
        st.session_state.conversation_history = []

    ddl, _ = get_database_metadata()
    schema_info = f"{ddl}"

    context_messages = []
    if maintain_context and st.session_state.conversation_history:
        for msg in st.session_state.conversation_history[-5:]:
            if msg["role"] == "user":
                context_messages.append(HumanMessage(content=msg["content"]))
            else:
                context_messages.append(AIMessage(content=msg["content"]))

    template = """You are an expert MySQL assistant. 
    Generate SQL queries based on the user's questions and the database schema.
    Maintain context from previous questions when appropriate.
    Only generate the raw SQL query unless the user asks for an explanation.
    The query should be valid and executable against the provided schema.

    Database Schema:
    {schema_info}

    Conversation History:
    {history}

    Current Question: {question}

    Your response (SQL query only, no explanation unless asked):
    """

    prompt = ChatPromptTemplate.from_template(template)
    chain = prompt | initialize_llm()

    formatted_prompt = {
        "schema_info": schema_info,
        "history": "\n".join([f"{msg['role']}: {msg['content']}" for msg in st.session_state.conversation_history[-4:]]),
        "question": question
    }

    response = chain.invoke(formatted_prompt)
    sql_query = extract_sql_query(response.content.strip())

    query_result, error = run_query(sql_query)

    st.session_state.conversation_history.append({"role": "user", "content": question})
    st.session_state.conversation_history.append({
        "role": "assistant",
        "content": f"SQL Query: {sql_query}\n\nResult: {query_result if query_result else error}"
    })

    if error:
        return f"```sql\n{sql_query}\n```\n\n❌ Error: {error}", None

    return f"```sql\n{sql_query}\n```\n\n{format_query_result(query_result)}", query_result

# === CSV UTILITY ===
def convert_result_to_csv(result: List[Dict]) -> Optional[bytes]:
    if not result:
        return None
    df = pd.DataFrame(result)
    output = io.StringIO()
    df.to_csv(output, index=False)
    return output.getvalue().encode('utf-8')

# === LLM QUERY TYPE CLASSIFIER ===
def classify_query_type(question: str) -> str:
    print("Classifying question:", question)

    prompt = (
        "Classify the following user question as either 'MySQL' or 'RAG'.\n"
        "Use 'MySQL' for database-related (structured data) questions, and 'RAG' for questions about documents or unstructured data.\n"
        "Only respond with one word: 'MySQL' or 'RAG'.\n\n"
        "Examples:\n"
        "Q: How many employees are in the database?\nA: MySQL\n"
        "Q: Summarize the uploaded PDF.\nA: RAG\n"
        "Q: What is the total revenue in 2023?\nA: MySQL\n"
        "Q: What is this document about?\nA: RAG\n\n"
        "Q: give their complete details?\nA: MySQL\n\n"
        f"Q: {question}\nA:"
    )

    payload = {
        "model": config["llm"]["model"],
        "prompt": prompt,
        "stream": False
    }

    try:
        response = requests.post(config["llm"]["base_url"] + "/api/generate", json=payload)
        result = response.json()["response"].strip().lower()
        print("Classification result:", result)
        return "MySQL" if "mysql" in result else "rag"
    except Exception as e:
        st.warning(f"Failed to classify query type: {e}")
        return "rag"
