import os
import tempfile
import base64
import streamlit as st
from utils import config, connect_database, get_llm_response, convert_result_to_csv, classify_query_type, handle_restricted_response
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
            "user_role": None,
            "pdf_assistant": ChatPDF(),
            "pdf_messages": [],
            "pdf_processed": False,
            "chat_mode": None,
            "uploaded_files": [],
            "temp_file_paths": [],
            "conversation_history": []
        }
        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value

    def setup_ui(self):
        if not st.session_state.logged_in:
            self.show_login_page()
        else:
            st.set_page_config(page_title="QueryBot", layout="centered", initial_sidebar_state="expanded")
            self.setup_sidebar()
            self.handle_chat()

    def show_login_page(self):
        st.markdown(
            f"""
            <div style="text-align: center;">
                <img src="data:image/png;base64,{self.get_base64_image('/home/chirag/Documents/QueryBot/src/logo.png')}" width="150" />
            </div>
            """,
            unsafe_allow_html=True
        )

        st.markdown(
            """
            <h1 style='text-align: center; font-size: 2.5em;'>QueryBot</h1>
            """,
            unsafe_allow_html=True
        )

        # Center username and password inputs
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            username = st.text_input(
                "Username", 
                key="login_username", 
                label_visibility="collapsed", 
                placeholder="Username", 
                max_chars=20
            )
            password = st.text_input(
                "Password", 
                type="password", 
                key="login_password", 
                label_visibility="collapsed", 
                placeholder="Password", 
                max_chars=20
            )

            # Wrap the button in a div with style to center it horizontally
            button_html = """
            <div style="display: flex; justify-content: center; margin-top: 10px;">
                <button style="width: 100%; max-width: 200px;">Login</button>
            </div>
            """

            # But Streamlit button can't be replaced with HTML button directly,
            # So instead we do normal st.button + add CSS to center it

            # Add the button inside col2, then center it with CSS using st.markdown and custom style
            if st.button("Login", key="login_button", help="Click to login"):
                authenticated = False
                for user in config["auth"]["users"]:
                    if (username == user["username"] and password == user["password"]):
                        st.session_state.logged_in = True
                        st.session_state.user_role = user["role"]
                        authenticated = True
                        break
                
                if authenticated:
                    st.success("Login successful! Redirecting to the app...")
                    st.rerun()
                else:
                    st.error("Invalid username or password!")

        # Custom CSS to center the button inside the middle column
        st.markdown(
            """
            <style>
            div.stButton > button:first-child {
                margin: 0 auto;
                display: block;
                max-width: 200px;
                width: 100%;
            }
            </style>
            """,
            unsafe_allow_html=True
        )



    def get_base64_image(self, image_path):
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()

    def setup_sidebar(self):
        with st.sidebar:
            st.image("/home/chirag/Documents/QueryBot/src/logo.png", width=200)

            if st.session_state.logged_in:
                user_role = st.session_state.user_role.upper()
                st.markdown(
                    f"""
                    <p style="
                        font-weight: 700; 
                        font-size: 1.1em; 
                        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                        user-select: none;
                    ">
                        <span style="background-color: #ffea00; padding: 4px 8px; border-radius: 4px; color: #333;">
                            Role: {user_role}
                        </span> 
                    </p>
                    """,
                    unsafe_allow_html=True
                )

            if st.session_state.user_role == "hr":
                st.subheader("Database Connection")
                self.db_connection_ui()
            else:
                st.info("Employee access: Restricted use of database")

            st.subheader("Upload a Document")
            uploaded_files = st.file_uploader(
                "Upload PDF document",
                type=["pdf"],
                key="file_uploader",
                accept_multiple_files=True,
                label_visibility="collapsed"
            )
            self.handle_pdf_upload(uploaded_files)

            st.subheader("Chat History")
            self.chat_history_ui()

            # --- LOGOUT BUTTON AT THE VERY END ---
            if st.session_state.logged_in:
                st.markdown("<br>", unsafe_allow_html=True)  # Add a bit of spacing

                # Custom CSS to style the Logout button red
                st.markdown(
                    """
                    <style>
                    div.stButton > button:first-child {
                        background-color: #e63946;  /* red */
                        color: white;
                        border: none;
                        padding: 8px 24px;
                        border-radius: 6px;
                        font-weight: bold;
                        width: 100%;
                        max-width: 200px;
                        margin: 0 auto;
                        display: block;
                    }
                    div.stButton > button:first-child:hover {
                        background-color: #d62828;
                    }
                    </style>
                    """,
                    unsafe_allow_html=True
                )

                if st.button("Logout"):
                    # Clear login-related session state
                    st.session_state.logged_in = False
                    st.session_state.user_role = None
                    st.session_state.chat = []
                    st.session_state.chat_histories = {}
                    st.session_state.active_chat = None
                    st.session_state.pdf_messages = []
                    st.session_state.pdf_processed = False
                    st.session_state.chat_mode = None
                    st.session_state.conversation_history = []
                    # Reload app
                    st.rerun()



    def db_connection_ui(self):
        with st.expander("Database Settings", expanded=True):
            st.text_input("Host", key="host", value=config["database"]["host"])
            st.text_input("Port", key="port", value=str(config["database"]["port"]))
            st.text_input("Username", key="username", value=config["database"]["username"])
            st.text_input("Password", key="password", type="password", value=config["database"]["password"])
            st.text_input("Database", key="database", value=config["database"]["name"])

            connect_button = st.button("Connect to Database", key="connect_button")
            if connect_button:
                connect_database(
                    host=st.session_state.host,
                    user=st.session_state.username,
                    password=st.session_state.password,
                    database=st.session_state.database,
                    port=st.session_state.port,
                )

    def chat_history_ui(self):
        if st.button("New Chat"):
            new_chat_name = f"Chat {len(st.session_state.chat_histories) + 1}"
            st.session_state.chat_histories[new_chat_name] = []
            st.session_state.active_chat = new_chat_name
            st.session_state.chat = []
            st.session_state.pdf_messages = []
            st.session_state.chat_mode = None
            st.session_state.conversation_history = []

        for chat_title in list(st.session_state.chat_histories.keys()):
            with st.expander(chat_title, expanded=(chat_title == st.session_state.active_chat)):
                if st.button(f"Open {chat_title}", key=f"open_{chat_title}"):
                    st.session_state.active_chat = chat_title
                    st.session_state.chat = st.session_state.chat_histories[chat_title]
                    st.session_state.pdf_messages = [
                        (msg["content"], msg["role"] == "user") for msg in st.session_state.chat if msg["role"] in ["user", "assistant"]
                    ]

    def handle_chat(self):
        if not st.session_state.chat:
            welcome_msg = """
            <div style="padding: 1em; background-color: #f0f2f6; border-radius: 10px; margin-bottom: 1em;">
                <h3 style="margin-bottom: 0.5em;">Welcome to QueryBot!</h3>
                <p style="margin: 0;">You can ask questions about:</p>
                <ul>
                    <li><b>Database</b> (e.g., "Show me employee information")</li>
                    <li><b>Uploaded PDF documents</b> (e.g., "Summarize this report")</li>
                </ul>
            """
            if st.session_state.user_role == "employee":
                welcome_msg += """As an employee, your access to database is restricted.
                """
            welcome_msg += "</div>"
            st.markdown(welcome_msg, unsafe_allow_html=True)
            
        question = st.chat_input("Ask a question about PDF or Database")

        if st.session_state.active_chat is None:
            new_chat_name = f"Chat {len(st.session_state.chat_histories) + 1}"
            st.session_state.chat_histories[new_chat_name] = []
            st.session_state.active_chat = new_chat_name
            st.session_state.chat = []
            st.session_state.pdf_messages = []
            st.session_state.chat_mode = None
            st.session_state.conversation_history = []

        for msg in st.session_state.chat:
            st.chat_message(msg["role"]).markdown(msg["content"])

        if question:
            query_type = classify_query_type(question)
            st.session_state.chat_mode = query_type

            st.chat_message("user").markdown(question)
            st.session_state.chat.append({"role": "user", "content": question})
            st.session_state.chat_histories[st.session_state.active_chat] = list(st.session_state.chat)

            if query_type == "MySQL":
                if "db" not in st.session_state or not st.session_state.db:
                    st.error("Please connect to the database first.")
                    return

                response, raw_result = get_llm_response(question)
                
                # Handle restricted access differently for employees
                if st.session_state.user_role == "employee":
                    response = handle_restricted_response(question, response)
                    
                st.chat_message("assistant").markdown(response)
                st.session_state.chat.append({"role": "assistant", "content": response})
                st.session_state.chat_histories[st.session_state.active_chat] = list(st.session_state.chat)

                if raw_result and st.session_state.user_role == "hr":
                    csv = convert_result_to_csv(raw_result)
                    st.download_button(
                        label="Download table as CSV",
                        data=csv,
                        file_name="query_results.csv",
                        mime="text/csv"
                    )

            else:
                if not st.session_state.pdf_processed:
                    st.error("Please upload and process a PDF first.")
                    return

                with st.spinner("Thinking..."):
                    response = st.session_state.pdf_assistant.ask(question)

                st.chat_message("assistant").markdown(response)
                st.session_state.chat.append({"role": "assistant", "content": response})
                st.session_state.chat_histories[st.session_state.active_chat] = list(st.session_state.chat)

    def handle_pdf_upload(self, uploaded_files):
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
                    with st.spinner(f"Processing {file.name}..."):
                        st.session_state.pdf_assistant.ingest(file_path)

                st.session_state.pdf_processed = True
                st.success("PDF processing complete!")
                st.rerun()

if __name__ == "__main__":
    IntegratedChatApp()