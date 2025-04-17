
# Chat with Your MySQL Database using LLM

This project is a **Streamlit web app** that allows you to ask natural language questions about your MySQL database and get back actual SQL query results — powered entirely by a **locally hosted LLM using Ollama**.

## Features

- Connect to any MySQL database through a simple UI  
- Ask questions in plain English  
- LLM generates raw SQL queries using the database schema  
- Formatted results returned in a chat interface  
- Runs entirely locally — no external API or internet required  
- Fully configurable through a YAML config file  

## Setup Instructions

### 1. Clone the repository

```bash
git clone https://github.com/your-username/Querybot.git
cd Querybot
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```
### 4. Update the config file
Edit config.yaml with your MySQL database credentials and LLM settings:

#### yaml
```bash
llm:
  base_url: "http://localhost:11434"
  model: "cnjack/mistral-samll-3.1:24b-it-q4_K_S"
  log_path: "prompts.jsonl"

database:
  host: "127.0.0.1"
  port: 3306
  username: "root"
  password: "yourpassword"
  name: "your_database"

```
### Running the App
```bash 
streamlit run app.py
```

This will launch the Streamlit app in your web browser.

### Project Structure
The project is structured as follows:

```bash 
├── src                 # Main Streamlit application
├── config              # Config
├── scripts             # scripts
├── requirements.txt    # Python dependencies
└── README.md           # Project documentation
```

## Tech Stack
```
Python 3.8+
Streamlit
LangChain
Ollama 
MySQL
```









