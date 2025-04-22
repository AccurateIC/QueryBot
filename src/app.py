# app.py

import streamlit as st
from utils import config
from utils import connect_database, get_llm_response, convert_result_to_csv

class MySQLChatApp:
    def __init__(self):
        self.init_session()
        self.setup_ui()

    def init_session(self):
        if "chat" not in st.session_state:
            st.session_state.chat = []

    def setup_ui(self):
        st.set_page_config(page_title="Chat with MySQL DB", layout="centered")
        st.title("Chat with Your MySQL Database")
        self.setup_sidebar()
        self.handle_chat()

    def setup_sidebar(self):
        

        with st.sidebar:
            st.title('🔗 Connect to Database')
            st.text_input(label="Host", key="host", value=config["database"]["host"])
            st.text_input(label="Port", key="port", value=str(config["database"]["port"]))
            st.text_input(label="Username", key="username", value=config["database"]["username"])
            st.text_input(label="Password", key="password", type="password", value=config["database"]["password"])
            st.text_input(label="Database", key="database", value=config["database"]["name"])
            connect_btn = st.button("Connect")

            if connect_btn:
                connect_database(
                    host=st.session_state.host,
                    user=st.session_state.username,
                    password=st.session_state.password,
                    database=st.session_state.database,
                    port=st.session_state.port,
                )

    def handle_chat(self):
        question = st.chat_input('💬 Ask anything about your database')
        if question:
            if "db" not in st.session_state or not st.session_state.db:
                st.error('Please connect to the database first.')
                return

            st.session_state.conversation_history.append({"role": "user", "content": question})
            response, raw_result = get_llm_response(question)
            st.session_state.conversation_history.append({"role": "assistant", "content": response})
            st.session_state.chat.append({"role": "user", "content": question})
            st.session_state.chat.append({"role": "assistant", "content": response})
            st.session_state.last_result = raw_result  # Save only the data table

        for i, chat in enumerate(st.session_state.chat):
            st.chat_message(chat['role']).markdown(chat['content'])

            # If it's the last assistant message and has a result, show download
            is_last_message = i == len(st.session_state.chat) - 1
            if chat['role'] == 'assistant' and is_last_message:
                if "last_result" in st.session_state and st.session_state.last_result:
                    csv = convert_result_to_csv(st.session_state.last_result)
                    st.download_button(
                        label="⬇️ Download table as CSV",
                        data=csv,
                        file_name="query_results.csv",
                        mime="text/csv"
                    )


if __name__ == "__main__":
    MySQLChatApp()

