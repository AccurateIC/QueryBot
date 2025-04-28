import streamlit as st
from utils import config, connect_database, get_llm_response, convert_result_to_csv


class MySQLChatApp:
    def __init__(self):
        self.init_session()
        self.setup_ui()

    def init_session(self):
        # Initialize session state if not already initialized
        if "chat" not in st.session_state:
            st.session_state.chat = []
        if "chat_histories" not in st.session_state:
            st.session_state.chat_histories = {}
        if "active_chat" not in st.session_state:
            st.session_state.active_chat = None
        if "logged_in" not in st.session_state:
            st.session_state.logged_in = False

    def setup_ui(self):
        # Show login page if not logged in
        if not st.session_state.logged_in:
            self.show_login_page()
        else:
            # Main page with database and chat functionality
            self.setup_main_page()

    def show_login_page(self):
        st.title("Login to MySQL Chat App")

        # Login form
        username = st.text_input("Username", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")
        login_button = st.button("Login")

        # Check if credentials are correct
        if login_button:
            if username == config["auth"]["username"] and password == config["auth"]["password"]:
                st.session_state.logged_in = True
                st.success("Login successful! Redirecting to the app...")
                st.rerun()  # Reload the page after successful login
            else:
                st.error("Invalid username or password!")

    def setup_main_page(self):
        st.set_page_config(page_title="Chat with MySQL DB", layout="centered")
        st.title("Chat with Your MySQL Database")
        self.setup_sidebar()
        self.handle_chat()

    def setup_sidebar(self):
        with st.sidebar:
            # Database connection section with an expander
            with st.expander("📡 Connect to Database", expanded=True):
                st.title('🔗 Connect to Database')
                st.text_input(label="Host", key="host", value=config["database"]["host"])
                st.text_input(label="Port", key="port", value=str(config["database"]["port"]))
                st.text_input(label="Username", key="username", value=config["database"]["username"])
                st.text_input(label="Password", key="password", type="password", value=config["database"]["password"])
                st.text_input(label="Database", key="database", value=config["database"]["name"])
                if st.button("Connect"):
                    connect_database(
                        host=st.session_state.host,
                        user=st.session_state.username,
                        password=st.session_state.password,
                        database=st.session_state.database,
                        port=st.session_state.port,
                    )

            st.markdown("---")

            # Chat History section
            st.title("🗂️ Chat History")

            # New Chat button to start a fresh conversation
            if st.button("➕ New Chat"):
                new_chat_name = f"Chat {len(st.session_state.chat_histories) + 1}"
                st.session_state.chat_histories[new_chat_name] = []
                st.session_state.active_chat = new_chat_name
                st.session_state.chat = []
                st.session_state.conversation_history = []

            # Display existing chat histories as expandable sections
            for chat_title in list(st.session_state.chat_histories.keys()):
                with st.expander(chat_title, expanded=(chat_title == st.session_state.active_chat)):
                    if st.button(f"🟢 Open {chat_title}", key=f"open_{chat_title}"):
                        st.session_state.active_chat = chat_title
                        st.session_state.chat = st.session_state.chat_histories[chat_title]
                        st.session_state.conversation_history = [
                            msg for msg in st.session_state.chat if msg["role"] in ["user", "assistant"]
                        ]

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
