import streamlit as st
from utils import connect_database, get_llm_response, convert_result_to_csv, config
import os

class MySQLChatApp:
    def __init__(self):
        st.set_page_config(page_title="Chat with MySQL DB", layout="centered")
        if "logged_in" not in st.session_state:
            st.session_state.logged_in = False
        if not st.session_state.logged_in:
            self.login()
        else:
            self.setup_ui()

    def login(self):
        st.title("🔐 Login")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.button("Login"):
            if (
                username == config["auth"]["username"]
                and password == config["auth"]["password"]
            ):
                st.session_state.logged_in = True
                st.rerun()
            else:
                st.error("❌ Invalid credentials")

    def setup_ui(self):
        st.sidebar.title("🗂️ Chat History")
        self.show_history_sidebar()

        st.title("🧠 Chat with MySQL")
        with st.expander("📡 Connect to Database", expanded=True):
            host = st.text_input("Host", value="localhost")
            user = st.text_input("User", value="root")
            password = st.text_input("Password", type="password")
            database = st.text_input("Database Name")
            port = st.text_input("Port", value="3306")

            if st.button("Connect"):
                connect_database(host, user, password, database, port)

        if "db" in st.session_state:
            st.markdown("### 💬 Ask your database anything")
            question = st.text_area("Enter your question:", height=100)
            if st.button("Send"):
                if question.strip():
                    response, result = get_llm_response(question)
                    st.markdown(response, unsafe_allow_html=True)
                    if result:
                        csv = convert_result_to_csv(result)
                        if csv:
                            st.download_button("⬇️ Download CSV", data=csv, file_name="query_result.csv", mime="text/csv")

    def show_history_sidebar(self):
        if "conversation_history" in st.session_state:
            for i, msg in enumerate(reversed(st.session_state.conversation_history)):
                role = "🧑" if msg["role"] == "user" else "🤖"
                st.sidebar.markdown(f"{role} {msg['content'][:100]}")


if __name__ == "__main__":
    MySQLChatApp()
