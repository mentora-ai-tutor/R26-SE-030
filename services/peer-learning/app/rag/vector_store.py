import os
import json
import logging
import numpy as np
from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from openai import OpenAI
from typing import List, Dict, Any

from app.rag.document_loader import load_and_split_pdf
from app.services.mongodb import get_collection

load_dotenv()

logger = logging.getLogger("vector_store")
KNOWLEDGE_COLLECTION = "knowledge_chunks"


def get_embeddings():
    """OpenAI Embeddings Model එක Initialize කිරීම."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY එක .env file එකෙහි නොමැත. කරුණාකර එය පරීක්ෂා කරන්න.")
    return OpenAIEmbeddings(
        model="text-embedding-3-small",
        openai_api_key=api_key,
    )


def initialize_vector_store():
    """
    PDF එක Load කර Chunk වලට කඩා embeddings සාදා MongoDB collection එකක සුරකියි.
    """
    chunks = load_and_split_pdf()
    texts = [chunk.page_content for chunk in chunks]
    embeddings = get_embeddings().embed_documents(texts)

    collection = get_collection(KNOWLEDGE_COLLECTION)
    collection.delete_many({})

    documents = [
        {
            "text": chunk.page_content,
            "metadata": chunk.metadata,
            "embedding": embeddings[i],
            "chunk_index": i,
        }
        for i, chunk in enumerate(chunks)
    ]
    collection.insert_many(documents)

    print(
        f"Vector Store එක සාර්ථකව initialize කර MongoDB collection "
        f"'{KNOWLEDGE_COLLECTION}' හි සුරකින ලදී!"
    )
    return collection


def get_retriever(k: int = 3):
    """
    MongoDB හි ගබඩා කර ඇති embeddings භාවිතයෙන් cosine similarity අනුව
    වඩාත්ම අදාළ Context chunk k ගණනක් Retrieve කරන callable එකක් ලබා දෙයි.
    """
    def _retrieve(query: str):
        query_embedding = get_embeddings().embed_query(query)
        query_vec = np.asarray(query_embedding, dtype=np.float64)
        query_norm = np.linalg.norm(query_vec)
        if query_norm == 0:
            return []

        collection = get_collection(KNOWLEDGE_COLLECTION)

        scored = []
        for doc in collection.find({}, {"text": 1, "metadata": 1, "embedding": 1}):
            vec = np.asarray(doc.get("embedding", []), dtype=np.float64)
            vec_norm = np.linalg.norm(vec)
            if vec.size == 0 or vec_norm == 0:
                continue
            similarity = float(np.dot(query_vec, vec) / (query_norm * vec_norm))
            scored.append((similarity, doc))

        scored.sort(key=lambda item: item[0], reverse=True)

        return [
            Document(
                page_content=doc["text"],
                metadata=doc.get("metadata", {}),
            )
            for _, doc in scored[:k]
        ]

    return _retrieve


# --- NEW: Personalized RAG Lesson Generation Logic ---
class RAGContentService:
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=api_key) if api_key else None
        self.model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def generate_personalized_content(self, student_id: str, weak_topics: List[str], score: float) -> Dict[str, Any]:
        """
        ශිෂ්‍යයාගේ ලකුණු සහ weak topics අනුව Vector Store එකෙන් Context Retrieve කර 
        Targeted Tutorial, Practice Code සහ Mini Exercise එක සාදයි.
        """
        if not self.client:
            return {"status": "error", "message": "OPENAI_API_KEY missing."}

        # 1. MongoDB Vector Store එකෙන් Weak Topics වලට අදාළ Java Context Retrieve කිරීම
        retriever = get_retriever(k=3)
        retrieved_docs = []
        for topic in weak_topics:
            docs = retriever(topic)
            retrieved_docs.extend([d.page_content for d in docs])

        context_text = "\n\n".join(retrieved_docs) if retrieved_docs else "Core Java Concepts Documentation"

        # 2. OpenAI RAG Prompt එක මගින් Personalized Lesson එක සෑදීම
        prompt = f"""
        You are an expert Java Pedagogy RAG Agent.
        Student ID: '{student_id}'
        Current Score: {score}%
        Identified Weak Topics: {weak_topics}

        Retrieved RAG Knowledge Base Context:
        {context_text}

        Generate a targeted, personalized lesson strictly in valid JSON format with keys:
        1. "topic_overview": Brief explanation addressing their specific doubts.
        2. "targeted_tutorial": Step-by-step clear tutorial to fix their specific weaknesses.
        3. "practice_code": Complete, clean, commented Java code snippet showcasing the fix.
        4. "practice_exercise": A mini challenge question for the student to attempt.
        """

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "You are a RAG Educational Agent for Java. Always output valid JSON format."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.5
            )

            lesson_content = json.loads(response.choices[0].message.content.strip())

            return {
                "status": "success",
                "student_id": student_id,
                "score": score,
                "weak_topics": weak_topics,
                "lesson": lesson_content
            }

        except Exception as e:
            logger.error(f"Error generating RAG lesson: {str(e)}")
            return {"status": "error", "message": str(e)}


rag_content_service = RAGContentService()

if __name__ == "__main__":
    initialize_vector_store()