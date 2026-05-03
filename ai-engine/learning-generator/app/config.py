import os

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3:8b")
OLLAMA_CODE_MODEL = os.getenv("OLLAMA_CODE_MODEL", "qwen2.5-coder:7b")
EXECUTION_TIMEOUT = int(os.getenv("EXECUTION_TIMEOUT", "15"))
RUN_TIMEOUT = int(os.getenv("RUN_TIMEOUT", "10"))
JAVA_HOME = os.getenv("JAVA_HOME", "")
TEMP_DIR = os.getenv("TEMP_DIR", "/tmp/java-sandbox")
