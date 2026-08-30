import os
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

def load_and_split_pdf(pdf_path: str = "app/rag/data/java_docs.pdf"):
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found at path: {pdf_path}")
        
    # File එක හිස්දැයි පරීක්ෂා කිරීම (0 bytes check)
    if os.path.getsize(pdf_path) == 0:
        raise ValueError(f"The file at {pdf_path} is empty (0 bytes). Please replace it with a valid PDF file.")
        
    print(f"Loading document from {pdf_path}...")
    loader = PyPDFLoader(pdf_path)
    documents = loader.load()
    
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200
    )
    chunks = text_splitter.split_documents(documents)
    print(f"Total chunks created: {len(chunks)}")
    return chunks