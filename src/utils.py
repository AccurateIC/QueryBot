
# utils.py

import mysql.connector
import streamlit as st
import re
import json
import yaml
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple

from langchain_community.chat_models import ChatOllama
from langchain.schema import LLMResult
from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, AIMessage

from schema_fetch import get_database_metadata


def load_config(path: str = "/home/chirag/Documents/QueryBot/config/config.yaml") -> Dict:
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


def initialize_llm() -> ChatOllama:
    return ChatOllama(
        model=config["llm"]["model"],
        base_url=config["llm"]["base_url"],
        callbacks=[LLMCallbackHandler(Path(config["llm"]["log_path"]))]
    )


def connect_database(host: str, user: str, password: str, database: str, port: int) -> None:
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


def run_query(query: str) -> Tuple[Optional[List[Dict]], Optional[str]]:
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


def get_llm_response(question: str, maintain_context: bool = True) -> str:
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
        return f"```sql\n{sql_query}\n```\n\n❌ Error: {error}"

    return f"```sql\n{sql_query}\n```\n\n{format_query_result(query_result)}"
