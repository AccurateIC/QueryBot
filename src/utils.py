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
import time
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
        callbacks=[LLMCallbackHandler(Path(config["llm"]["log_path"]))],
        temperature=0.3  # More deterministic output for SQL
    )

def connect_database(host: str, user: str, password: str, database: str, port: int) -> None:
    try:
        connection = mysql.connector.connect(
            host=host,
            user=user,
            password=password,
            database=database,
            port=int(port),
            connect_timeout=5  # 5 seconds connection timeout
        )
        cursor = connection.cursor(dictionary=True)
        st.session_state.db = (connection, cursor)
        st.session_state.conversation_history = []
        st.session_state.schema_cache = None  # Initialize schema cache
        st.success("✅ Database connected successfully!")
    except mysql.connector.Error as e:
        st.error(f"❌ Failed to connect: {e}")
        raise

def disconnect_database() -> None:
    if "db" in st.session_state and st.session_state.db:
        connection, cursor = st.session_state.db
        cursor.close()
        connection.close()
        del st.session_state.db
        st.session_state.db_connected = False
        st.success("Disconnected from database")

def validate_query(query: str) -> Tuple[bool, str]:
    """Basic SQL query validation"""
    query = query.strip().upper()
    if not query:
        return False, "Empty query"
    
    # Check for forbidden statements
    forbidden = ["DROP", "TRUNCATE", "GRANT", "REVOKE", "SHUTDOWN"]
    for keyword in forbidden:
        if keyword in query:
            return False, f"Query contains forbidden keyword: {keyword}"
    
    # Check if it starts with SELECT (for this demo, we'll only allow SELECT)
    if not query.startswith("SELECT"):
        return False, "Only SELECT queries are allowed in this demo"
    
    return True, ""

def run_query(query: str) -> Tuple[Optional[List[Dict]], Optional[str], float]:
    """Run query and return results, error message, and execution time"""
    start_time = time.time()
    try:
        # Basic query validation
        is_valid, validation_msg = validate_query(query)
        if not is_valid:
            return None, f"Invalid query: {validation_msg}", 0
        
        if "db" in st.session_state and st.session_state.db:
            connection, cursor = st.session_state.db
            cursor.execute(query)
            result = cursor.fetchall()
            execution_time = time.time() - start_time
            return result, None, execution_time
        return None, "⚠️ Please connect to the database first.", 0
    except mysql.connector.Error as e:
        execution_time = time.time() - start_time
        return None, f"❌ Error executing query: {e}", execution_time

def format_query_result(result: List[Dict]) -> str:
    if not result:
        return "ℹ️ No results found."
    
    # Limit the number of rows displayed in the chat
    display_limit = 10
    truncated = len(result) > display_limit
    display_results = result[:display_limit]
    
    table_headers = display_results[0].keys()
    table_rows = [list(row.values()) for row in display_results]
    
    formatted_result = f"**Query Results ({len(result)} rows)**\n\n"
    formatted_result += "| " + " | ".join(table_headers) + " |\n"
    formatted_result += "| " + " | ".join(["---"] * len(table_headers)) + " |\n"
    
    for row in table_rows:
        formatted_result += "| " + " | ".join(str(cell)[:100] for cell in row) + " |\n"
    
    if truncated:
        formatted_result += f"\nShowing first {display_limit} of {len(result)} rows. Download for full results."
    
    return formatted_result

def extract_sql_query(text: str) -> str:
    """Improved SQL query extraction with more patterns"""
    # Remove <think> blocks if present
    think_end = text.find("</think>")
    if think_end != -1:
        text = text[think_end + len("</think>"):]
    
    # Pattern 1: ```sql ... ```
    match = re.search(r"```sql\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    # Pattern 2: SQL query: SELECT ...;
    match = re.search(r"SQL query:\s*(SELECT .*?;)", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    # Pattern 3: Just the query without any markers
    match = re.search(r"(SELECT .*?;)", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    return text.strip()

def get_cached_schema() -> str:
    """Get cached schema or fetch fresh if not available"""
    if "schema_cache" not in st.session_state or st.session_state.schema_cache is None:
        ddl, _ = get_database_metadata()
        st.session_state.schema_cache = ddl
    return st.session_state.schema_cache

def get_llm_response(question: str, maintain_context: bool = True) -> Tuple[str, Optional[List[Dict]], float]:
    try:
        if "conversation_history" not in st.session_state:
            st.session_state.conversation_history = []

        # Get schema from cache or fresh fetch
        schema_info = get_cached_schema()
        
        # Limit history to last 4 messages for context
        recent_history = st.session_state.conversation_history[-4:] if maintain_context else []
        
        context_messages = []
        for msg in recent_history:
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

        Respond with just the SQL query between ```sql markers:
        ```sql
        SELECT * FROM table;
        ```
        """

        prompt = ChatPromptTemplate.from_template(template)
        chain = prompt | initialize_llm()

        formatted_prompt = {
            "schema_info": schema_info,
            "history": "\n".join([f"{msg['role']}: {msg['content']}" for msg in recent_history]),
            "question": question
        }

        response = chain.invoke(formatted_prompt)
        sql_query = extract_sql_query(response.content.strip())

        query_result, error, execution_time = run_query(sql_query)

        if error:
            return f"```sql\n{sql_query}\n```\n\n❌ Error: {error}", None, execution_time

        return f"```sql\n{sql_query}\n```\n\n{format_query_result(query_result)}", query_result, execution_time

    except Exception as e:
        error_msg = f"Error generating response: {str(e)}"
        st.error(error_msg)
        return error_msg, None, 0

def convert_result_to_csv(result: List[Dict]) -> Optional[bytes]:
    if not result:
        return None
    try:
        df = pd.DataFrame(result)
        output = io.StringIO()
        df.to_csv(output, index=False)
        return output.getvalue().encode('utf-8')
    except Exception as e:
        st.error(f"Error converting results to CSV: {str(e)}")
        return None