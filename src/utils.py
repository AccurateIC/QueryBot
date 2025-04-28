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
import tempfile
from PyPDF2 import PdfReader

# LangChain imports
from langchain_community.chat_models import ChatOllama
from langchain.schema import LLMResult
from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, AIMessage
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain.chains import RetrievalQA
from langchain.docstore.document import Document

from schema_fetch import get_database_metadata

def load_config(path: str = "./config/config.yaml") -> Dict:
    """Load configuration from YAML file"""
    with open(path, "r") as file:
        return yaml.safe_load(file)

config = load_config()

@dataclass
class Event:
    event: str
    timestamp: str
    text: str

def _current_time() -> str:
    """Get current UTC time in ISO format"""
    return datetime.now(timezone.utc).isoformat()

class LLMCallbackHandler(BaseCallbackHandler):
    """Callback handler for LLM events"""
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
    """Initialize the LLM with configuration"""
    return ChatOllama(
        model=config["llm"]["model"],
        base_url=config["llm"]["base_url"],
        callbacks=[LLMCallbackHandler(Path(config["llm"]["log_path"]))],
        temperature=0.3
    )

def connect_database(host: str, user: str, password: str, database: str, port: int) -> None:
    """Connect to MySQL database"""
    try:
        connection = mysql.connector.connect(
            host=host,
            user=user,
            password=password,
            database=database,
            port=int(port),
            connect_timeout=5
        )
        cursor = connection.cursor(dictionary=True)
        st.session_state.db = (connection, cursor)
        st.session_state.conversation_history = []
        st.session_state.schema_cache = None
        st.success("✅ Database connected successfully!")
    except mysql.connector.Error as e:
        st.error(f"❌ Failed to connect: {e}")
        raise

def disconnect_database() -> None:
    """Disconnect from MySQL database"""
    if "db" in st.session_state and st.session_state.db:
        connection, cursor = st.session_state.db
        cursor.close()
        connection.close()
        del st.session_state.db
        st.session_state.db_connected = False
        st.success("Disconnected from database")

def validate_query(query: str) -> Tuple[bool, str]:
    """Validate SQL query for safety"""
    query = query.strip().upper()
    if not query:
        return False, "Empty query"
    
    forbidden = ["DROP", "TRUNCATE", "GRANT", "REVOKE", "SHUTDOWN"]
    for keyword in forbidden:
        if keyword in query:
            return False, f"Query contains forbidden keyword: {keyword}"
    
    if not query.startswith("SELECT"):
        return False, "Only SELECT queries are allowed in this demo"
    
    return True, ""

def run_query(query: str) -> Tuple[Optional[List[Dict]], Optional[str], float]:
    """Execute SQL query and return results"""
    start_time = time.time()
    try:
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
    """Format SQL query results for display"""
    if not result:
        return "ℹ️ No results found."
    
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
    """Extract SQL query from LLM response"""
    think_end = text.find("</think>")
    if think_end != -1:
        text = text[think_end + len("</think>"):]
    
    match = re.search(r"```sql\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    match = re.search(r"SQL query:\s*(SELECT .*?;)", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    match = re.search(r"(SELECT .*?;)", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    return text.strip()

def get_cached_schema() -> str:
    """Get cached database schema"""
    if "schema_cache" not in st.session_state or st.session_state.schema_cache is None:
        ddl, _ = get_database_metadata()
        st.session_state.schema_cache = ddl
    return st.session_state.schema_cache

def is_pdf_question(question: str, uploaded_pdfs: list) -> bool:
    """Determine if question should be answered from PDFs"""
    if not uploaded_pdfs:
        return False
    
    pdf_keywords = ["document", "pdf", "file", "text", "content", "article", "section", "page"]
    question_lower = question.lower()
    
    return any(keyword in question_lower for keyword in pdf_keywords)

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from PDF with robust error handling"""
    try:
        reader = PdfReader(pdf_path)
        text = ""
        for i, page in enumerate(reader.pages):
            try:
                page_text = page.extract_text()
                if page_text:
                    text += f"--- PAGE {i+1} ---\n{page_text}\n"
            except Exception as e:
                st.warning(f"Could not read page {i+1} in {pdf_path}: {str(e)}")
        return text
    except Exception as e:
        st.error(f"Failed to process PDF {pdf_path}: {str(e)}")
        return ""

def initialize_chroma_store(pdf_paths: List[str]) -> Chroma:
    """Initialize Chroma vector store with PDF documents"""
    # Extract text from all PDFs
    all_texts = []
    for path in pdf_paths:
        text = extract_text_from_pdf(path)
        if text:
            all_texts.append(text)
    
    if not all_texts:
        raise ValueError("Could not extract any text from the provided PDFs")

    # Split text into chunks with metadata
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len
    )
    
    documents = []
    for text in all_texts:
        docs = text_splitter.create_documents([text])
        documents.extend(docs)
    
    # Add source information
    for i, doc in enumerate(documents):
        doc.metadata = {
            "source": pdf_paths[i % len(pdf_paths)],
            "page": (i // len(pdf_paths)) + 1
        }

    # Create embeddings
    embeddings = OllamaEmbeddings(
        model=config["llm"]["model"],
        base_url=config["llm"]["base_url"]
    )

    # Create and persist Chroma store
    return Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        persist_directory=config["chroma"]["persist_directory"],
        collection_name=config["chroma"]["collection_name"]
    )

def process_pdf(question: str, pdf_paths: list[str]) -> str:
    """Process PDF question using ChromaDB vector store"""
    if not pdf_paths:
        return "No PDF documents available to search."

    try:
        # Initialize Chroma store if not exists
        if "chroma_store" not in st.session_state:
            with st.spinner("Indexing PDF documents..."):
                st.session_state.chroma_store = initialize_chroma_store(pdf_paths)

        # Create retrieval QA chain
        qa_chain = RetrievalQA.from_chain_type(
            llm=initialize_llm(),
            chain_type="stuff",
            retriever=st.session_state.chroma_store.as_retriever(
                search_kwargs={"k": 3}  # Return top 3 relevant chunks
            ),
            return_source_documents=True
        )
        
        # Get answer with sources
        result = qa_chain({"query": question})
        
        # Format response
        if not result['result']:
            return "No relevant information found in the documents."
            
        response = f"{result['result']}\n\n---\n**Sources:**\n"
        unique_sources = set()
        for doc in result['source_documents']:
            source = doc.metadata.get('source', 'Unknown document')
            if source not in unique_sources:
                response += f"- {Path(source).name} (Page {doc.metadata.get('page', 'N/A')})\n"
                unique_sources.add(source)
        
        return response
        
    except Exception as e:
        st.error(f"Error processing your question: {str(e)}")
        return "Could not generate an answer from the documents."

def get_llm_response(question: str, maintain_context: bool = True) -> Tuple[str, Optional[List[Dict]], float]:
    """Get LLM response for database questions"""
    try:
        if "conversation_history" not in st.session_state:
            st.session_state.conversation_history = []

        schema_info = get_cached_schema()
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
    """Convert query results to CSV format"""
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
    

import os
import tempfile
from typing import List

import streamlit as st
from PyPDF2 import PdfReader
from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OllamaEmbeddings
from langchain.prompts import PromptTemplate
from langchain_community.chat_models import ChatOllama

# ---------- Configuration (must be provided from outside or imported) ----------
# Expected config dict structure:
# config = {
#     "llm": {
#         "model": "your-model-name",
#         "base_url": "http://localhost:11434"
#     },
#     "chroma": {
#         "persist_directory": "path/to/store",
#         "collection_name": "your-collection-name"
#     },
#     "auth": {
#         "username": "your-username",
#         "password": "your-password"
#     }
# }

# ---------- PDF Processing and Chroma Embedding Functions ----------

def initialize_chroma_store(pdf_paths: List[str]) -> Chroma:
    """Initialize Chroma vector store with extracted documents from PDFs."""
    documents = []

    for path in pdf_paths:
        try:
            reader = PdfReader(path)
            for page_num, page in enumerate(reader.pages):
                try:
                    page_text = page.extract_text()
                    if page_text:
                        documents.append(
                            Document(
                                page_content=page_text,
                                metadata={
                                    "source": str(path),
                                    "page": page_num + 1
                                }
                            )
                        )
                except Exception as e:
                    st.warning(f"Could not read page {page_num + 1} in {path}: {str(e)}")
        except Exception as e:
            st.error(f"Failed to process PDF {path}: {str(e)}")

    if not documents:
        raise ValueError("No text extracted from the provided PDFs.")

    # Split documents into manageable chunks
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len
    )
    split_documents = text_splitter.split_documents(documents)

    # Initialize embeddings
    embeddings = OllamaEmbeddings(
        model=config["llm"]["model"],
        base_url=config["llm"]["base_url"]
    )

    # Create Chroma vector store
    vectordb = Chroma.from_documents(
        documents=split_documents,
        embedding=embeddings,
        persist_directory=config["chroma"]["persist_directory"],
        collection_name=config["chroma"]["collection_name"]
    )

    vectordb.persist()
    return vectordb


def process_pdf(uploaded_files) -> Chroma:
    """Handle uploaded PDFs and initialize vector store."""
    if not uploaded_files:
        st.error("Please upload at least one PDF file.")
        return None

    pdf_paths = []

    for uploaded_file in uploaded_files:
        # Save uploaded file to a temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            tmp_file.write(uploaded_file.read())
            pdf_paths.append(tmp_file.name)

    with st.spinner("Processing PDFs and creating vector store..."):
        vectordb = initialize_chroma_store(pdf_paths)

    # Clean up temp files
    for path in pdf_paths:
        try:
            os.remove(path)
        except Exception as e:
            st.warning(f"Could not delete temporary file {path}: {str(e)}")

    st.success("PDFs processed and vector store created successfully!")
    return vectordb

# ---------- LLM and Retrieval Helper Functions ----------

def load_vectorstore() -> Chroma:
    """Load existing Chroma vectorstore."""
    embeddings = OllamaEmbeddings(
        model=config["llm"]["model"],
        base_url=config["llm"]["base_url"]
    )
    vectordb = Chroma(
        persist_directory=config["chroma"]["persist_directory"],
        embedding_function=embeddings,
        collection_name=config["chroma"]["collection_name"]
    )
    return vectordb

def get_llm():
    """Initialize LLM client."""
    return ChatOllama(
        model=config["llm"]["model"],
        base_url=config["llm"]["base_url"]
    )

def get_prompt() -> PromptTemplate:
    """Create a basic QA prompt template."""
    prompt = PromptTemplate(
        input_variables=["context", "question"],
        template="""You are a helpful assistant. 
Given the following context from a document, answer the question precisely.

Context: {context}

Question: {question}

Answer:"""
    )
    return prompt

# ---------- Authentication Helper ----------

def check_password():
    """Authenticate user with username and password."""
    def password_entered():
        if (st.session_state["username"] == config["auth"]["username"] and
            st.session_state["password"] == config["auth"]["password"]):
            st.session_state["authenticated"] = True
            del st.session_state["username"]
            del st.session_state["password"]
        else:
            st.session_state["authenticated"] = False
            st.error("Invalid username or password.")

    if "authenticated" not in st.session_state:
        st.text_input("Username", key="username")
        st.text_input("Password", type="password", key="password")
        st.button("Login", on_click=password_entered)

    if not st.session_state.get("authenticated", False):
        st.stop()
