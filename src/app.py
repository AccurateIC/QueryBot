import streamlit as st
import tempfile
from utils import (
    config,
    connect_database,
    disconnect_database,
    get_llm_response,
    convert_result_to_csv,
    process_pdf,
    is_pdf_question
)
from datetime import datetime


class MySQLChatApp:
    def __init__(self):
        self.init_session()
        self.setup_ui()

    def init_session(self):
        # Initialize session state if not already initialized
        session_defaults = {
            "chat": [],
            "chat_histories": {},
            "active_chat": None,
            "logged_in": False,
            "db_connected": False,
            "uploaded_pdfs": [],
            "conversation_history": []
        }
        
        for key, value in session_defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value

    def setup_ui(self):
        # Show login page if not logged in
        if not st.session_state.logged_in:
            self.show_login_page()
        else:
            # Main page with database, PDF and chat functionality
            self.setup_main_page()

    def show_login_page(self):
        st.title("Login to MySQL Chat App")

        # Login form
        with st.form("login_form"):
            username = st.text_input("Username", key="login_username")
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Login")

            if submitted:
                if username == config["auth"]["username"] and password == config["auth"]["password"]:
                    st.session_state.logged_in = True
                    st.session_state.login_time = datetime.now()
                    st.success("Login successful! Redirecting to the app...")
                    st.rerun()
                else:
                    st.error("Invalid username or password!")

    def setup_main_page(self):
        st.set_page_config(page_title="Chat with MySQL DB & PDFs", layout="centered")
        st.title("Chat with Your MySQL Database or PDF Documents")
        self.setup_sidebar()
        self.handle_file_upload()
        self.handle_chat()

    def setup_sidebar(self):
        with st.sidebar:
            # Database connection section
            with st.expander("📡 Connect to Database", expanded=True):
                st.title('🔗 Connect to Database')
                host = st.text_input(label="Host", key="host", value=config["database"]["host"])
                port = st.text_input(label="Port", key="port", value=str(config["database"]["port"]))
                username = st.text_input(label="Username", key="db_username", value=config["database"]["username"])
                password = st.text_input(label="Password", key="db_password", type="password", value="")
                database = st.text_input(label="Database", key="database", value=config["database"]["name"])
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Connect", use_container_width=True):
                        try:
                            connect_database(
                                host=host,
                                user=username,
                                password=password,
                                database=database,
                                port=int(port),
                            )
                            st.session_state.db_connected = True
                            st.session_state.db_password = ""  # Clear password after connection
                            st.rerun()
                        except Exception as e:
                            st.error(f"Connection failed: {str(e)}")
                
                with col2:
                    if st.session_state.db_connected:
                        if st.button("Disconnect", use_container_width=True):
                            disconnect_database()
                            st.session_state.db_connected = False
                            st.rerun()

            st.markdown("---")

            # PDF documents section
            with st.expander("📄 PDF Documents", expanded=False):
                st.title("Uploaded PDFs")
                if st.session_state.uploaded_pdfs:
                    for pdf in st.session_state.uploaded_pdfs:
                        st.write(f"• {pdf['name']}")
                    if st.button("Clear All PDFs", key="clear_pdfs"):
                        st.session_state.uploaded_pdfs = []
                        st.rerun()
                else:
                    st.info("No PDFs uploaded yet")

            st.markdown("---")

            # Chat History section
            st.title("🗂️ Chat History")

            # New Chat button to start a fresh conversation
            if st.button("➕ New Chat"):
                new_chat_name = f"Chat {len(st.session_state.chat_histories) + 1} - {datetime.now().strftime('%H:%M')}"
                st.session_state.chat_histories[new_chat_name] = []
                st.session_state.active_chat = new_chat_name
                st.session_state.chat = []
                st.session_state.conversation_history = []

            # Display existing chat histories
            for chat_title in list(st.session_state.chat_histories.keys()):
                with st.expander(chat_title, expanded=(chat_title == st.session_state.active_chat)):
                    if st.button(f"🟢 Open {chat_title}", key=f"open_{chat_title}"):
                        st.session_state.active_chat = chat_title
                        st.session_state.chat = st.session_state.chat_histories[chat_title]
                        st.session_state.conversation_history = [
                            msg for msg in st.session_state.chat if msg["role"] in ["user", "assistant"]
                        ]

    def handle_file_upload(self):
        with st.expander("📄 Upload PDF Documents", expanded=False):
            uploaded_files = st.file_uploader(
                "Upload PDF files", 
                type=["pdf"],
                accept_multiple_files=True,
                key="pdf_uploader"
            )
            
            if uploaded_files:
                if "uploaded_pdfs" not in st.session_state:
                    st.session_state.uploaded_pdfs = []
                
                for uploaded_file in uploaded_files:
                    # Save to temporary file
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                        tmp.write(uploaded_file.getbuffer())
                        file_info = {
                            "name": uploaded_file.name,
                            "path": tmp.name
                        }
                        if file_info not in st.session_state.uploaded_pdfs:
                            st.session_state.uploaded_pdfs.append(file_info)
                            st.success(f"Processed PDF: {uploaded_file.name}")

    def handle_chat(self):
        question = st.chat_input('💬 Ask anything about your database or PDF documents')
        if question:
            # Initialize chat history if this is the first question
            if not st.session_state.active_chat:
                new_chat_name = f"Chat {len(st.session_state.chat_histories) + 1} - {datetime.now().strftime('%H:%M')}"
                st.session_state.chat_histories[new_chat_name] = []
                st.session_state.active_chat = new_chat_name
                st.session_state.chat = []
                st.session_state.conversation_history = []

            # First determine if this is a PDF question
            is_pdf_query = is_pdf_question(question, st.session_state.get("uploaded_pdfs", []))
            
            if is_pdf_query:
                self.handle_pdf_question(question)
            else:
                self.handle_db_question(question)

            # Display the chat messages after processing
            self.display_chat_messages()

    def handle_db_question(self, question):
        if "db" not in st.session_state or not st.session_state.db:
            st.error('Please connect to the database first.')
            return

        # Add question to all relevant histories
        st.session_state.conversation_history.append({"role": "user", "content": question})
        st.session_state.chat.append({"role": "user", "content": question})
        
        with st.spinner("Generating response..."):
            try:
                response, raw_result, execution_time = get_llm_response(question)
                
                # Add metadata to the response
                enhanced_response = f"{response}\n\n⏱️ Query executed in {execution_time:.2f}s"
                if raw_result:
                    enhanced_response += f" | 📊 {len(raw_result)} rows returned"
                
                st.session_state.conversation_history.append({
                    "role": "assistant", 
                    "content": enhanced_response
                })
                st.session_state.chat.append({
                    "role": "assistant", 
                    "content": enhanced_response
                })
                # Update the chat history for the active chat
                st.session_state.chat_histories[st.session_state.active_chat] = st.session_state.chat
                st.session_state.last_result = raw_result
            except Exception as e:
                st.error(f"Error processing your request: {str(e)}")

    def handle_pdf_question(self, question):
        if "uploaded_pdfs" not in st.session_state or not st.session_state.uploaded_pdfs:
            st.error('Please upload PDF documents first.')
            return

        # Add question to chat
        st.session_state.conversation_history.append({"role": "user", "content": question})
        st.session_state.chat.append({"role": "user", "content": question})
        
        with st.spinner("Searching PDF documents..."):
            try:
                # Process PDF and get answer
                answer = process_pdf(question, [pdf["path"] for pdf in st.session_state.uploaded_pdfs])
                
                # Add assistant response to chat
                assistant_response = f"From PDF documents:\n\n{answer}"
                st.session_state.conversation_history.append({
                    "role": "assistant", 
                    "content": assistant_response
                })
                st.session_state.chat.append({
                    "role": "assistant", 
                    "content": assistant_response
                })
                
                # Update chat history if active chat exists
                if st.session_state.active_chat:
                    st.session_state.chat_histories[st.session_state.active_chat] = st.session_state.chat
                    
            except Exception as e:
                st.error(f"Error processing PDF question: {str(e)}")

    def display_chat_messages(self):
        # Display chat messages
        for i, chat in enumerate(st.session_state.chat):
            st.chat_message(chat['role']).markdown(chat['content'])

            # If it's the last assistant message and has a result, show download
            is_last_message = i == len(st.session_state.chat) - 1
            if chat['role'] == 'assistant' and is_last_message:
                if "last_result" in st.session_state and st.session_state.last_result:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    csv = convert_result_to_csv(st.session_state.last_result)
                    st.download_button(
                        label="⬇️ Download as CSV",
                        data=csv,
                        file_name=f"query_results_{timestamp}.csv",
                        mime="text/csv",
                        key=f"download_{timestamp}"
                    )


if __name__ == "__main__":
    MySQLChatApp()