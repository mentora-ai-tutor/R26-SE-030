from app.agents.base_agent import BaseAgent
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

class ModeratorAgent(BaseAgent):
    def validate_content(self, user_message: str) -> dict:
        prompt = ChatPromptTemplate.from_template("""
        You are a content safety and relevance moderator for a Java Educational Platform.
        Analyze the following student input:
        
        Input: "{message}"
        
        Check for:
        1. Toxicity, inappropriate language, or harmful content.
        2. Relevance to Programming, Java, Computer Science, or Academic Learning.
        
        Respond strictly in this format:
        IS_SAFE: [YES/NO]
        IS_RELEVANT: [YES/NO]
        REASON: [Brief explanation]
        """)
        
        chain = prompt | self.llm | StrOutputParser()
        result = chain.invoke({"message": user_message})
        
        is_safe = "IS_SAFE: YES" in result
        is_relevant = "IS_RELEVANT: YES" in result
        
        return {
            "is_allowed": is_safe and is_relevant,
            "raw_moderation": result
        }

    def process(self, input_data: dict) -> dict:
        message = input_data.get("message", "")
        return self.validate_content(message)