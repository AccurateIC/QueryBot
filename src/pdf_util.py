import os
import logging
import yaml
import tempfile
import ocrmypdf
from typing import Dict
from langchain_ollama import OllamaLLM
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import FastEmbedEmbeddings
from langchain_community.document_loaders import PyPDFLoader, UnstructuredPDFLoader
from langchain.schema.output_parser import StrOutputParser
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.prompts import PromptTemplate
from langchain.schema.runnable import RunnablePassthrough
from langchain_community.vectorstores.utils import filter_complex_metadata


# Load config from YAML
def load_config(path: str = "/home/chirag/Documents/QueryBot/config/config.yaml") -> Dict:
    with open(path, "r") as file:
        return yaml.safe_load(file)

config = load_config()


class ChatPDF:
    def __init__(self):
        llm_config = config["llm"]

        self.model = OllamaLLM(
            base_url=llm_config["base_url"],
            model=llm_config["model"],
            temperature=0.1,
            num_ctx=4096,
            top_k=30
        )

        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=512,
            chunk_overlap=128,
            length_function=len,
            add_start_index=True
        )

        self.prompt_template = """
        <s> [INST] You are an expert PDF content assistant. Answer the question based ONLY on the following context. 
        If you don't know the answer, say you don't know. DON'T make up answers.
        
        Context: {context}
        
        Question: {question} 
        
        Answer: [/INST]
        """
        self.prompt = PromptTemplate.from_template(self.prompt_template)

        self.vector_store = None
        self.retriever = None
        self.chain = None

    def ingest(self, pdf_file_path: str):
        try:
            # Step 1: Preprocess scanned PDFs using OCRmyPDF
            with tempfile.TemporaryDirectory() as tmpdir:
                ocr_output_path = os.path.join(tmpdir, "searchable.pdf")
                try:
                    ocrmypdf.ocr(
                        pdf_file_path,
                        ocr_output_path,
                        deskew=True,
                        clean=True,
                        progress_bar=False
                    )
                    logging.info(f"OCR applied successfully: {pdf_file_path}")
                except Exception as ocr_error:
                    logging.warning(f"OCRmyPDF failed, using original file: {ocr_error}")
                    ocr_output_path = pdf_file_path  # fallback to original

                # Step 2: Try loading with PyPDFLoader, fallback to UnstructuredPDFLoader
                try:
                    loader = PyPDFLoader(ocr_output_path)
                    docs = loader.load()
                except Exception as e:
                    logging.warning(f"PyPDFLoader failed, falling back to UnstructuredPDFLoader: {e}")
                    loader = UnstructuredPDFLoader(ocr_output_path)
                    docs = loader.load()

            if not docs:
                raise ValueError("PDF appears to be empty or unreadable")

            chunks = self.text_splitter.split_documents(docs)
            chunks = filter_complex_metadata(chunks)

            # Filter out empty or whitespace-only chunks
            chunks = [chunk for chunk in chunks if chunk.page_content.strip()]

            if not chunks:
                raise ValueError("No valid content found in PDF after processing.")

            self.vector_store = Chroma.from_documents(
                documents=chunks,
                embedding=FastEmbedEmbeddings(
                    model_name="BAAI/bge-small-en-v1.5"
                ),
                persist_directory="./chroma_db"
            )

            self.retriever = self.vector_store.as_retriever(
                search_type="mmr",
                search_kwargs={
                    "k": 5,
                    "fetch_k": 20,
                    "lambda_mult": 0.5
                }
            )

            self.chain = (
                {"context": self.retriever, "question": RunnablePassthrough()}
                | self.prompt
                | self.model
                | StrOutputParser()
            )

            return True
        except Exception as e:
            logging.error(f"Error ingesting PDF: {str(e)}")
            return False

    def ask(self, question: str):
        if not self.chain:
            return "Please load a PDF document first."

        try:
            clean_question = question.strip()
            if not clean_question:
                return "Please provide a valid question."

            relevant_docs = self.retriever.get_relevant_documents(clean_question)
            if not relevant_docs:
                return "No relevant information found in the document."

            return self.chain.invoke(clean_question)

        except Exception as e:
            logging.error(f"Error answering question: {str(e)}")
            return "An error occurred while processing your question."

    def clear(self):
        """Reset the internal state (e.g., after uploading a new PDF)"""
        self.vector_store = None
        self.retriever = None
        self.chain = None
