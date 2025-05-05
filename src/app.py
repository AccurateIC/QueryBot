import os
import tempfile
import base64
import streamlit as st
from utils import config, connect_database, get_llm_response, convert_result_to_csv
from pdf_util import ChatPDF


class IntegratedChatApp:
    def __init__(self):
        self.init_session()
        self.setup_ui()

    def init_session(self):
        defaults = {
            "chat": [],
            "chat_histories": {},
            "active_chat": None,
            "logged_in": False,
            "active_tab": "MySQL Chat",
            "pdf_assistant": ChatPDF(),
            "pdf_messages": [],
            "pdf_processed": False,
            "pdf_chat_histories": {},
            "active_pdf_chat": None,
            "uploaded_files": [],
            "temp_file_paths": []
        }
        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value

    def setup_ui(self):
        if not st.session_state.logged_in:
            self.show_login_page()
        else:
            st.set_page_config(page_title="QueryBot", layout="centered")
            self.setup_tab_switcher()
            self.setup_sidebar()

            if st.session_state.active_tab == "MySQL Chat":
                self.setup_mysql_page()
            else:
                self.setup_pdf_page()

    def setup_tab_switcher(self):
        tabs = ["MySQL Chat", "PDF Chat"]
        selected_tab = st.radio("Select Mode:", tabs, horizontal=True, label_visibility="collapsed")

        if selected_tab != st.session_state.active_tab:
            st.session_state.active_tab = selected_tab
            st.rerun()

    def show_login_page(self):
        st.title("Login to Integrated Chat App")
        username = st.text_input("Username", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")
        login_button = st.button("Login")

        if login_button:
            if username == config["auth"]["username"] and password == config["auth"]["password"]:
                st.session_state.logged_in = True
                st.success("Login successful! Redirecting to the app...")
                st.rerun()
            else:
                st.error("Invalid username or password!")

    def setup_sidebar(self):
        with st.sidebar:
            if st.session_state.active_tab == "MySQL Chat":
                with st.expander("Connect to Database", expanded=True):
                    st.text_input("Host", key="host", value=config["database"]["host"])
                    st.text_input("Port", key="port", value=str(config["database"]["port"]))
                    st.text_input("Username", key="username", value=config["database"]["username"])
                    st.text_input("Password", key="password", type="password", value=config["database"]["password"])
                    st.text_input("Database", key="database", value=config["database"]["name"])

                    if st.button("Connect"):
                        connect_database(
                            host=st.session_state.host,
                            user=st.session_state.username,
                            password=st.session_state.password,
                            database=st.session_state.database,
                            port=st.session_state.port,
                        )

                st.markdown("---")

            st.title("Chat History")
            if st.button("New Chat"):
                if st.session_state.active_tab == "MySQL Chat":
                    new_chat_name = f"SQL Chat {len(st.session_state.chat_histories) + 1}"
                    st.session_state.chat_histories[new_chat_name] = []
                    st.session_state.active_chat = new_chat_name
                    st.session_state.chat = []
                    st.session_state.conversation_history = []
                else:
                    new_chat_name = f"PDF Chat {len(st.session_state.pdf_chat_histories) + 1}"
                    st.session_state.pdf_chat_histories[new_chat_name] = []
                    st.session_state.active_pdf_chat = new_chat_name
                    st.session_state.pdf_messages = []
                    if st.session_state.uploaded_files:
                        st.session_state.pdf_processed = True
                    else:
                        st.session_state.pdf_processed = False
                        st.session_state.pdf_assistant.clear()

            if st.session_state.active_tab == "MySQL Chat":
                for chat_title in list(st.session_state.chat_histories.keys()):
                    with st.expander(chat_title, expanded=(chat_title == st.session_state.active_chat)):
                        if st.button(f"Open {chat_title}", key=f"open_{chat_title}"):
                            st.session_state.active_chat = chat_title
                            st.session_state.chat = st.session_state.chat_histories[chat_title]
                            st.session_state.conversation_history = [
                                msg for msg in st.session_state.chat if msg["role"] in ["user", "assistant"]
                            ]
            else:
                for chat_title in list(st.session_state.pdf_chat_histories.keys()):
                    with st.expander(chat_title, expanded=(chat_title == st.session_state.active_pdf_chat)):
                        if st.button(f"Open {chat_title}", key=f"open_pdf_{chat_title}"):
                            st.session_state.active_pdf_chat = chat_title
                            st.session_state.pdf_messages = st.session_state.pdf_chat_histories[chat_title]

    def setup_mysql_page(self):
        st.title("Database")
        self.handle_mysql_chat()

    def handle_mysql_chat(self):
        question = st.chat_input('Ask anything about your database')
        
        if question:
            if "db" not in st.session_state or not st.session_state.db:
                st.error('Please connect to the database first.')
                return

            # Initialize active chat if not already
            if st.session_state.active_chat is None:
                new_chat_name = f"SQL Chat {len(st.session_state.chat_histories) + 1}"
                st.session_state.chat_histories[new_chat_name] = []
                st.session_state.active_chat = new_chat_name
                st.session_state.chat = []
                st.session_state.conversation_history = []

            # Add the user question to the conversation history
            st.session_state.conversation_history.append({"role": "user", "content": question})
            
            # Get the LLM response (assuming this is a function that queries the database and gets a response)
            response, raw_result = get_llm_response(question)
            
            # Add the assistant's response to the conversation history
            st.session_state.conversation_history.append({"role": "assistant", "content": response})
            
            # Update the main chat list
            st.session_state.chat.append({"role": "user", "content": question})
            st.session_state.chat.append({"role": "assistant", "content": response})
            
            # Save the chat to the active chat history
            if st.session_state.active_chat:
                st.session_state.chat_histories[st.session_state.active_chat] = list(st.session_state.chat)

            # Update the sidebar chat history right after the query
            if st.session_state.active_chat:
                st.session_state.chat_histories[st.session_state.active_chat] = list(st.session_state.chat)

            # Show the result and any options like downloading CSV
            st.session_state.last_result = raw_result

            # Optionally, display the results as CSV
            # Inside the handle_mysql_chat function where the download button is created
            if "last_result" in st.session_state and st.session_state.last_result:
                csv = convert_result_to_csv(st.session_state.last_result)
                st.download_button(
                    label="Download table as CSV",
                    data=csv,
                    file_name="query_results.csv",
                    mime="text/csv",
                    key=f"download_button_{len(st.session_state.chat)}"  # Make the key unique
                )


        # Display all messages in the chat
        for i, chat in enumerate(st.session_state.chat):
            st.chat_message(chat['role']).markdown(chat['content'])

            # Display the latest response in the assistant's message
            is_last_message = i == len(st.session_state.chat) - 1
            if chat['role'] == 'assistant' and is_last_message:
                if "last_result" in st.session_state and st.session_state.last_result:
                    csv = convert_result_to_csv(st.session_state.last_result)
                    st.download_button(
                        label="Download table as CSV",
                        data=csv,
                        file_name="query_results.csv",
                        mime="text/csv"
                    )

    def setup_pdf_page(self):
        st.title("PDF Documents")
        self.handle_pdf_upload()
        self.display_pdf_messages()
        self.handle_pdf_chat()

    def handle_pdf_upload(self):
        st.subheader("Upload a document")
        uploaded_files = st.file_uploader(
            "Upload PDF document",
            type=["pdf"],
            key="file_uploader",
            accept_multiple_files=True,
            label_visibility="collapsed"
        )

        if uploaded_files:
            new_files = set(file.name for file in uploaded_files)
            old_files = set(file.name for file in st.session_state.uploaded_files)

            if new_files != old_files:
                st.session_state.pdf_assistant.clear()
                st.session_state.pdf_messages = []
                st.session_state.uploaded_files = uploaded_files

                st.session_state.temp_file_paths = []

                for file in uploaded_files:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tf:
                        tf.write(file.getbuffer())
                        file_path = tf.name
                        st.session_state.temp_file_paths.append(file_path)

                    with st.spinner(f"Processing {file.name}"):
                        st.session_state.pdf_assistant.ingest(file_path)

                st.session_state.pdf_processed = True
                st.rerun()

    def display_pdf_messages(self):
        st.subheader("Chat")
        for msg, is_user in st.session_state.pdf_messages:
            st.chat_message("user" if is_user else "assistant").markdown(msg)

        if st.session_state.pdf_processed:
            
            for file_path in st.session_state.temp_file_paths:
                file_name = os.path.basename(file_path)
                if st.button(f"View PDF: {file_name}", key=f"view_pdf_{file_name}"):
                    self.show_pdf(file_path)

    def show_pdf(self, file_path):
        with open(file_path, "rb") as f:
            base64_pdf = base64.b64encode(f.read()).decode("utf-8")

    def handle_pdf_chat(self):
        question = st.chat_input('Ask anything about the PDF')
        if question and st.session_state.pdf_processed:
            st.session_state.pdf_messages.append((question, True))

            with st.spinner("Thinking..."):
                response = st.session_state.pdf_assistant.ask(question)

            st.session_state.pdf_messages.append((response, False))

            if st.session_state.active_pdf_chat:
                st.session_state.pdf_chat_histories[st.session_state.active_pdf_chat] = list(
                    st.session_state.pdf_messages
                )

            st.rerun()


if __name__ == "__main__":
    IntegratedChatApp()
