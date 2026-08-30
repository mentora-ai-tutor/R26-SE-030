import os
from typing import TypedDict, Sequence
from dotenv import load_dotenv

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from app.agents.knowledge_rag import get_knowledge_agent

load_dotenv()

# Define the State for the Agent Graph
class AgentState(TypedDict):
    messages: Sequence[BaseMessage]
    next_node: str
    user_id: str

# Knowledge Node: Queries the RAG Agent for Java concepts
def knowledge_node(state: AgentState):
    messages = state["messages"]
    last_message = messages[-1].content
    
    knowledge_agent = get_knowledge_agent()
    response = knowledge_agent.invoke(last_message)
    
    return {
        "messages": list(messages) + [AIMessage(content=response)]
    }

# Router Node: Directs traffic based on message intent
def router_node(state: AgentState):
    messages = state["messages"]
    last_message = messages[-1].content.lower()
    
    # Routes to Knowledge Agent by default for Java queries
    return "knowledge_agent"

# Build the LangGraph Graph
def create_agent_graph():
    workflow = StateGraph(AgentState)
    
    # Add Nodes
    workflow.add_node("knowledge_agent", knowledge_node)
    
    # Define Entry Point and Edges
    workflow.set_entry_point("knowledge_agent")
    workflow.add_edge("knowledge_agent", END)
    
    app = workflow.compile()
    return app

# Test execution locally
if __name__ == "__main__":
    graph = create_agent_graph()
    initial_state = {
        "messages": [HumanMessage(content="What is Abstraction in Java?")],
        "next_node": "",
        "user_id": "student_123"
    }
    
    print("\n--- Testing LangGraph Orchestrator ---")
    result = graph.invoke(initial_state)
    print("\nFinal Output:\n")
    print(result["messages"][-1].content)