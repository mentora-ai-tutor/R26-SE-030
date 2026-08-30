import os
from abc import ABC, abstractmethod
from langchain_openai import ChatOpenAI

class BaseAgent(ABC):
    def __init__(self, model_name: str = "gpt-4o-mini", temperature: float = 0.2):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is missing.")
        
        self.llm = ChatOpenAI(
            model=model_name,
            temperature=temperature,
            openai_api_key=api_key
        )

    @abstractmethod
    def process(self, input_data: dict) -> dict:
        """Process input data and return structured output."""
        pass