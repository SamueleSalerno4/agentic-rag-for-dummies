# agent.py
"""
Defines the retrieval tools, system prompt,
and builds the agent LangGraph.
"""

import os
import json
from typing import List
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import MessagesState, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

import config
# Import initialized components
from components import llm, child_vector_store

# --- 1. Define Retrieval Tools ---

def search_child_chunks(query: str, k: int = 5) -> List[dict]:
    """
    Search for the top K most relevant child chunks.
    """
    print(f"--- Tool: search_child_chunks (Query: '{query}', K: {k}) ---")
    try:
        results = child_vector_store.similarity_search(query, k=k)
        return [
            {
                "content": doc.page_content,
                "parent_id": doc.metadata.get("parent_id", ""),
                "source": doc.metadata.get("source", "")
            }
            for doc in results
        ]
    except Exception as e:
        print(f"Error searching child chunks: {e}")
        return []

def retrieve_parent_chunks(parent_ids: List[str]) -> List[dict]:
    """
    Retrieve full parent chunks by their IDs.
    """
    print(f"--- Tool: retrieve_parent_chunks (IDs: {parent_ids}) ---")
    unique_ids = sorted(list(set(parent_ids)))
    results = []
    
    for parent_id in unique_ids:
        file_path = os.path.join(config.PARENT_STORE_PATH, f"{parent_id}.json")
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    doc_dict = json.load(f)
                    results.append({
                        "content": doc_dict["page_content"],
                        "parent_id": parent_id,
                        "metadata": doc_dict["metadata"]
                    })
            except Exception as e:
                print(f"Error loading parent chunk {parent_id}: {e}")
    
    return results

# --- 2. Bind Tools to LLM ---
tools = [search_child_chunks, retrieve_parent_chunks]
llm_with_tools = llm.bind_tools(tools)

# --- 3. Define System Prompt ---
SYSTEM_PROMPT = """You are an intelligent assistant specialized in answering questions using documents.

Follow this precise workflow:

**1. Analyze the Question**
- Understand what the user is asking
- Identify main topics
- If complex, split into focused subqueries
- Process each subquery through steps 2-7

**2. Retrieve Child Chunks**
- Use `search_child_chunks` to find relevant small chunks
- Choose an appropriate K value (default: 5)

**3. Evaluate Child Chunks**
- Read retrieved content carefully
- Determine relevance to the question
- Identify `parent_id`s of most relevant chunks
- If chunks contain ALL needed information, skip to step 6

**4. Assess Need for Context**
- If chunks are fragmented, unclear, or incomplete
- If they only partially answer the question
- Then retrieve parent chunks

**5. Retrieve Parent Chunks (if needed)**
- Use `retrieve_parent_chunks` with unique `parent_id`s
- Read parent chunks for full context

**6. Generate Answer**
- Base answer exclusively on retrieved information
- Combine subquery answers if applicable
- Explain concepts clearly
- Cite source files (without extension) using metadata
- Example: "This information comes from '[filename]'"

**7. Verify and Iterate**
- If initial search found nothing relevant: rephrase query and retry
- If parent chunks insufficient: restart from step 1
- Maximum 3 attempts per question/subquery
- After 3 attempts, ask user to rephrase

**Critical Rules:**
- Follow steps 1-7 for every question/subquery
- Answer only from retrieved chunks
- Never fabricate information
- Always cite sources
"""

system_message = SystemMessage(content=SYSTEM_PROMPT)

# --- 4. Define Graph Nodes ---

def agent_node(state: MessagesState):
    """
    Agent decision-making node.
    Decides which tool to call or generates final response.
    """
    print("--- Node: agent ---")
    messages = [system_message] + state["messages"]
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}

# The ToolNode handles the execution of the tools
tool_node = ToolNode(tools)

# --- 5. Build the Graph ---
print("Compiling agent graph...")
graph_builder = StateGraph(MessagesState)

# Add nodes
graph_builder.add_node("agent", agent_node)
graph_builder.add_node("tools", tool_node)

# Define edges
graph_builder.add_edge(START, "agent")
graph_builder.add_conditional_edges(
    "agent",
    tools_condition,  # Routes to 'tools' if tool_calls exist, else to END
)
graph_builder.add_edge("tools", "agent") # Return to agent after tools run

# Compile the graph
agent_graph = graph_builder.compile()
print("✓ Agent graph compiled successfully.")