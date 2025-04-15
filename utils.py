# utils.py

import mysql.connector
import streamlit as st
import re
import json
import yaml
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Any, Dict, List

from langchain_community.chat_models import ChatOllama
from langchain.schema import LLMResult
from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.prompts import ChatPromptTemplate
from schema_fetch import get_database_metadata


# Load config from YAML
def load_config(path="config.yaml"):
    with open(path, "r") as file:
        return yaml.safe_load(file)

config = load_config()


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


def initialize_llm():
    return ChatOllama(
        model=config["llm"]["model"],
        base_url=config["llm"]["base_url"],
        callbacks=[LLMCallbackHandler(Path(config["llm"]["log_path"]))]
    )


def connect_database(host, user, password, database, port):
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
        st.success("✅ Database connected successfully!")
    except mysql.connector.Error as e:
        st.error(f"❌ Failed to connect: {e}")


def run_query(query):
    try:
        if "db" in st.session_state and st.session_state.db:
            connection, cursor = st.session_state.db
            cursor.execute(query)
            result = cursor.fetchall()
            return format_query_result(result)
        return "⚠️ Please connect to the database first."
    except mysql.connector.Error as e:
        return f"❌ Error executing query: {e}"


def format_query_result(result):
    if not result:
        return "ℹ️ No results found."
    table_headers = result[0].keys()
    table_rows = [list(row.values()) for row in result]

    formatted_result = f"**Query Results:**\n\n| " + " | ".join(table_headers) + " |\n| " + " | ".join(["---"] * len(table_headers)) + " |\n"
    for row in table_rows:
        formatted_result += "| " + " | ".join(str(cell) for cell in row) + " |\n"
    return formatted_result


def extract_sql_query(text):
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


def get_llm_response(question):
    ddl, _ = get_database_metadata()
    schema_info = f"{ddl}"
    template = f"""You are an expert MySQL assistant. 
Only generate the raw SQL query based on the user's question, using the given schema. 
Do NOT explain or reason. 
Do NOT include any markdown, backticks, or natural language. 
Only output a single valid SQL query that can be run directly.
Do NOT include think

Table Schemas:
{schema_info}

Natural Language Question:
{{question}}

Your response:
"""
    prompt = ChatPromptTemplate.from_template(template)
    chain = prompt | initialize_llm()

    response = chain.invoke({"question": question})
    sql_query = extract_sql_query(response.content.strip())
    query_result = run_query(sql_query)

    return f"```sql\n{sql_query}\n```\n\n{query_result}"
