# app.py

import streamlit as st
from utils import config
from utils import connect_database, get_llm_response

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

            st.session_state.chat.append({"role": "user", "content": question})
            response = get_llm_response(question)
            st.session_state.chat.append({"role": "assistant", "content": response})

        for chat in st.session_state.chat:
            st.chat_message(chat['role']).markdown(chat['content'])


if __name__ == "__main__":
    MySQLChatApp()
