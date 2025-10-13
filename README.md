<p align="center">
<img alt="Agentic RAG for Dummies Logo" src="assets/logo.png" width="300px">
</p>

<h1 align="center">Agentic RAG for Dummies</h1>

<p align="center">
  <strong>Build a production-ready Agentic RAG system with LangGraph in just a few lines of code</strong>
</p>

<p align="center">
  <a href="#overview">Overview</a> •
  <a href="#how-it-works">How It Works</a> •
  <a href="#installation">Installation</a> •
  <a href="#step-by-step-implementation">Implementation</a> •
  <a href="#usage">Usage</a>
</p>

---

## Overview

This repository demonstrates how to build an **Agentic RAG (Retrieval-Augmented Generation)** system using LangGraph with minimal code. Unlike traditional RAG systems that retrieve and respond in a single step, Agentic RAG uses an AI agent that can:

- 🔍 **Intelligently search** through document summaries
- 🎯 **Decide which documents** are relevant
- 📄 **Retrieve full documents** only when needed
- 🤖 **Leverage long-context LLMs** to generate accurate answers
- 🔄 **Self-correct** and retry if the answer isn't satisfactory

### The Approach

Instead of chunking documents and retrieving small pieces, we:

1. **Generate summaries** for each document (PDF)
2. **Store summaries** in a vector database with hybrid search (dense + sparse)
3. **Let the agent** search summaries first to find relevant documents
4. **Retrieve full documents** and leverage the LLM's long context window
5. **Generate accurate answers** using complete document context

This approach reduces hallucinations and improves answer quality by giving the LLM full context rather than fragmented chunks.

---

## How It Works

```
User Query → Agent → Search Summaries → Evaluate Relevance → 
Retrieve Full Documents → Generate Answer → Verify Quality → Return Response
```

The agent orchestrates the entire retrieval process, making intelligent decisions about which documents to fetch and when to retry.

---

## Installation

This project is designed to run on **Google Colab**. Install all dependencies with:

```bash
!pip install --quiet --upgrade langgraph
!pip install -qU "langchain[google-genai]"
!pip install -qU langchain langchain-community langchain-qdrant langchain-huggingface qdrant-client fastembed flashrank
!pip install --upgrade gradio
```

---

## Step-by-Step Implementation

### Step 1: Configure the LLM

First, we set up our language model. We're using Google's Gemini 2.0 Flash for its excellent long-context capabilities.

```python
import os
from langchain_google_genai import ChatGoogleGenerativeAI

# Set your Google API key
os.environ["GOOGLE_API_KEY"] = "your-api-key-here"

# Initialize the LLM with zero temperature for consistent outputs
llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash-001", 
    temperature=0
)
```

**Why this matters:** The LLM is the brain of our system. Gemini 2.0 Flash can handle very long contexts (up to 1M tokens), making it perfect for processing entire documents.

---

### Step 2: Set Up Vector Database with Hybrid Search

We use Qdrant for vector storage with hybrid search (combining semantic and keyword-based retrieval).

```python
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_qdrant.fastembed_sparse import FastEmbedSparse
from langchain_qdrant import QdrantVectorStore
from langchain_qdrant.qdrant import RetrievalMode

# Configuration
DOCUMENT_DIR = "docs"
SUMMARY_DIR = "summaries"
DB_PATH = "qdrant_db"
SUMMARY_COLLECTION = "document_summaries"
CHUNK_COLLECTION = "document_chunks"

# Initialize embeddings
dense_embeddings = HuggingFaceEmbeddings(
    model_name="intfloat/multilingual-e5-large"
)
sparse_embeddings = FastEmbedSparse(
    model_name="Qdrant/bm25"
)

# Create Qdrant client
client = QdrantClient(path=DB_PATH)
embedding_dimension = len(dense_embeddings.embed_query("test"))

def ensure_collection(collection_name):
    """Create collection if it doesn't exist"""
    if not client.collection_exists(collection_name):
        client.create_collection(
            collection_name=collection_name,
            vectors_config=qmodels.VectorParams(
                size=embedding_dimension, 
                distance=qmodels.Distance.COSINE
            ),
            sparse_vectors_config={
                "sparse": qmodels.SparseVectorParams()
            },
        )

# Create collections
ensure_collection(SUMMARY_COLLECTION)
ensure_collection(CHUNK_COLLECTION)

# Initialize vector stores
summary_vector_store = QdrantVectorStore(
    client=client,
    collection_name=SUMMARY_COLLECTION,
    embedding=dense_embeddings,
    sparse_embedding=sparse_embeddings,
    retrieval_mode=RetrievalMode.HYBRID,
    sparse_vector_name="sparse"
)
```

**Why hybrid search?** Dense embeddings capture semantic meaning, while sparse embeddings (BM25) capture exact keyword matches. Together, they provide more robust retrieval.

---

### Step 3: Load Document Summaries

We load pre-generated summaries and index them in our vector database.

```python
import os
import glob
import re
from langchain.schema import Document

summary_documents = []

# Load all summary files
for file_path in sorted(glob.glob(os.path.join(SUMMARY_DIR, "*_summary.md"))):
    base_name = os.path.basename(file_path)
    # Extract document ID from filename
    document_id = re.sub(r"_summary\.md$", "", base_name, flags=re.I).lower()
    
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    summary_documents.append(
        Document(
            page_content=content,
            metadata={"document_id": document_id, "source": base_name}
        )
    )

# Index summaries in vector database
_ = summary_vector_store.add_documents(summary_documents)
```

**Why summaries?** Summaries are concise and faster to search. The agent uses them as a "table of contents" to quickly identify relevant documents.

---

### Step 4: Define Agent Tools

The agent needs tools to interact with the retrieval system.

```python
from pathlib import Path

def search_summaries(query: str, k: int = 3):
    """
    Search for the top K most relevant document summaries.
    
    Args:
        query: The search query
        k: Number of results to return
        
    Returns:
        List of relevant summary documents
    """
    return summary_vector_store.similarity_search(query, k=k)

def retrieve_full_documents(summaries: list):
    """
    Retrieve complete documents based on summary metadata.
    
    Args:
        summaries: List of summary documents
        
    Returns:
        List of full document contents
    """
    full_documents = []
    
    for summary in summaries:
        # Get document ID from metadata
        document_id = summary.metadata.get("document_id")
        if not document_id:
            continue
            
        # Construct path to full document
        document_path = Path(DOCUMENT_DIR) / f"{document_id}.md"
        
        if document_path.exists():
            with open(document_path, 'r', encoding='utf-8') as f:
                content = f.read()
                full_documents.append(content)
    
    return full_documents

# Bind tools to LLM
llm_with_tools = llm.bind_tools([search_summaries, retrieve_full_documents])
```

**Why two separate tools?** This gives the agent fine-grained control. It can search summaries first, evaluate them, and only retrieve full documents if needed.

---

### Step 5: Create the Agent System Prompt

The system prompt defines the agent's behavior and reasoning process.

```python
from langchain_core.messages import SystemMessage

SYSTEM_PROMPT = """You are an intelligent document retrieval assistant. Your goal is to answer user questions accurately using available documents.

Follow this reasoning process:

1. **Analyze the query**: Understand what the user is asking for
2. **Search summaries**: Use the search_summaries tool to find relevant documents (decide how many to retrieve)
3. **Evaluate relevance**: Review the summaries and determine which documents are likely to contain the answer
4. **Retrieve full documents**: Use retrieve_full_documents to get complete content for relevant documents
5. **Verify relevance**: Check if the full documents actually contain the needed information
6. **Generate answer**: Provide a clear, detailed answer based on the document content
7. **Quality check**: Verify your answer addresses the user's question
8. **Retry if needed**: If the answer isn't satisfactory, try different search terms or documents (maximum 3 attempts)

Important guidelines:
- Only retrieve documents that are clearly relevant to the query
- If no relevant documents are found after 3 attempts, explain what information is missing
- Be concise but thorough in your responses
- Always base your answers on the retrieved documents, don't make up information
"""

system_message = SystemMessage(content=SYSTEM_PROMPT)
```

**Why this prompt?** It gives the agent a clear decision-making framework, encouraging it to think step-by-step and self-correct when needed.

---

### Step 6: Build the LangGraph Agent

Now we create the agent graph that orchestrates the retrieval flow.

```python
from langchain_core.messages import HumanMessage
from langgraph.graph import MessagesState, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import InMemorySaver

# Define the agent's decision-making node
def agent_node(state: MessagesState):
    """Agent decides which tool to call or generates final response"""
    return {
        "messages": llm_with_tools.invoke(
            [system_message] + state["messages"]
        )
    }

# Initialize memory for conversation history
memory = InMemorySaver()

# Build the graph
graph_builder = StateGraph(MessagesState)

# Add nodes
graph_builder.add_node("agent", agent_node)
graph_builder.add_node("tools", ToolNode([search_summaries, retrieve_full_documents]))

# Define edges
graph_builder.add_edge(START, "agent")
graph_builder.add_conditional_edges(
    "agent",
    tools_condition,  # Decides if tools are needed or if we should end
)
graph_builder.add_edge("tools", "agent")  # After tool use, return to agent

# Compile the graph
agent_graph = graph_builder.compile()

# Visualize the graph (optional)
from IPython.display import Image, display
display(Image(agent_graph.get_graph(xray=True).draw_mermaid_png()))
```

**What's happening here?** The agent evaluates the user's message, decides if it needs to call tools, processes the tool results, and generates a final answer. This loop continues until the agent is satisfied.

---

### Step 7: Create a Chat Interface

Finally, we wrap everything in a simple Gradio interface.

```python
import gradio as gr

def chat_with_agent(message, history):
    """Process user message and return agent's response"""
    result = agent_graph.invoke({
        "messages": [HumanMessage(content=message)]
    })
    return result["messages"][-1].content

# Launch Gradio interface
demo = gr.ChatInterface(fn=chat_with_agent)
demo.launch(share=False)
```

**And you're done!** You now have a fully functional Agentic RAG system that intelligently searches through documents and generates accurate answers.

---

## Usage

1. **Prepare your documents**: Place your documents in the `docs/` folder (in Markdown format)
2. **Generate summaries**: Create summaries for each document and save them in `summaries/` folder with `_summary.md` suffix
3. **Run the notebook**: Execute all cells in order
4. **Chat with your documents**: Use the Gradio interface to ask questions

### Example Interaction

```
User: "What are the best practices for data security?"

Agent: [Searches summaries] → [Finds 2 relevant documents] → 
       [Retrieves full documents] → [Generates comprehensive answer]
```

---

## Key Advantages

✅ **Simple**: Just a few lines of code to build a complete system  
✅ **Intelligent**: Agent makes smart decisions about retrieval  
✅ **Accurate**: Uses full document context instead of small chunks  
✅ **Self-correcting**: Can retry and refine searches  
✅ **Scalable**: Hybrid search handles large document collections  

---

## License

MIT License - Feel free to use this for learning and building your own projects!

---

## Contributing

Contributions are welcome! Open an issue or submit a pull request.
