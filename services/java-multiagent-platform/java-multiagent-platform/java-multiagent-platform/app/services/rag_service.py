import os
import logging
from typing import Optional
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

# Vector Store එකෙන් Context ගන්නා Function එක Import කිරීමට උත්සාහ කිරීම
try:
    from app.rag.vector_store import get_retriever
except ImportError:
    get_retriever = None


class RAGService:
    def __init__(self):
        # Environment Variable එකෙන් API Key එක ලබා ගැනීම
        api_key = os.getenv("OPENAI_API_KEY", "dummy_key")
        
        # LLM Model එක Initialize කිරීම
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.3,
            api_key=api_key
        )

    def get_relevant_context(self, query: str) -> str:
        """
        Vector DB / ChromaDB එකෙන් ප්‍රශ්නයට අදාළ RAG Context එක ලබා ගැනීම.
        Vector DB එක නැත්නම් හෝ Error එකක් ආවොත් Fallback Text එකක් ලබා දෙයි.
        """
        if get_retriever:
            try:
                retriever = get_retriever(k=2)
                retrieved_docs = retriever.get_relevant_documents(query)
                if retrieved_docs:
                    return "\n\n".join([doc.page_content for doc in retrieved_docs])
            except Exception as e:
                logger.warning(f"Vector store retrieval failed or not initialized: {e}")
        
        # Default Fallback Context
        return "Core Java fundamentals documentation regarding variables, loops, data types, and logic execution flow."


# App එක පුරාම එකම Instance එක (Singleton) භාවිත කිරීමට Export කිරීම
rag_service = RAGService()