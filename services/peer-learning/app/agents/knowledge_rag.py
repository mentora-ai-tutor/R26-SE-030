import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from app.rag.vector_store import get_retriever

load_dotenv()

# Context ගොනු එකතු කරගැනීමට Helper Function එකක්
def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)

def get_knowledge_agent():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY එක .env හි නොමැත.")

    # 1. LLM Model එක සකස් කිරීම
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.2,
        openai_api_key=api_key
    )

    # 2. Vector DB Retriever එක ලබා ගැනීම (MongoDB embeddings)
    retriever = RunnableLambda(get_retriever())

    # 3. System Prompt එක සැකසීම (Java Tutor Agent)
    system_prompt = """
    You are an expert AI Java Learning Assistant for university students. 
    Use the following retrieved context from Java documentation and lecture notes to answer the student's question accurately.
    
    Guidelines:
    - Keep your answer clear, educational, and easy to understand.
    - Provide short code snippets/examples where appropriate.
    - If you do not know the answer or if it's not in the context, state that clearly instead of guessing.

    Context:
    {context}

    Question: {question}
    
    Answer:
    """

    prompt = ChatPromptTemplate.from_template(system_prompt)

    # 4. RAG Chain එක සකස් කිරීම
    rag_chain = (
        {"context": retriever | format_docs, "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )

    return rag_chain

# Test කිරීම සඳහා
if __name__ == "__main__":
    agent = get_knowledge_agent()
    test_query = "What is an Interface in Java and why is it used?"
    print(f"\nUser Question: {test_query}\n")
    print("Agent Responding...\n")
    response = agent.invoke(test_query)
    print("----- AI Response -----")
    print(response)