from app.agents.base_agent import BaseAgent
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

class PeerMatchingAgent(BaseAgent):
    def find_peer(self, student_profile: dict, available_peers: list) -> str:
        prompt = ChatPromptTemplate.from_template("""
        You are an Intelligent Peer Matching Agent for Java learners.
        Match the target student with the best peer based on their current Java topic and skill level.
        
        Target Student: {student_profile}
        Available Peers Pool: {peers_pool}
        
        Analyze the profiles and select the best peer for collaborative learning. Explain why.
        """)
        
        chain = prompt | self.llm | StrOutputParser()
        return chain.invoke({
            "student_profile": str(student_profile),
            "peers_pool": str(available_peers)
        })

    def process(self, input_data: dict) -> dict:
        target_student = input_data.get("student", {})
        peers = input_data.get("peers", [])
        match_result = self.find_peer(target_student, peers)
        return {"match_result": match_result}