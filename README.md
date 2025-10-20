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
  <a href="#usage">Usage</a> •
  <a href="#upcoming-features">Upcoming Features</a>
</p>

<p align="center">
  <strong>Quickstart here 👉</strong> 
  <a href="https://colab.research.google.com/gist/GiovanniPasq/5e52799638f66657c5069a5dd0e292ff/agentic-rag-for-dummies.ipynb">
    <img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"/>
  </a>
</p>

<p align="center">
  <a href="https://www.youtube.com/watch?v=54gWDC3vppA" target="_blank">
    <img src="https://img.shields.io/badge/YouTube-%23FF0000.svg?style=for-the-badge&logo=YouTube&logoColor=white" alt="Watch on YouTube">
  </a>
</p>

<p align="center">
  <img alt="Agentic RAG Demo" src="assets/demo.gif" width="500px">
</p>

---

## Overview

This repository demonstrates how to build an **Agentic RAG (Retrieval-Augmented Generation)** system using LangGraph with minimal code. Unlike traditional RAG systems that retrieve and respond in a single step, Agentic RAG uses an AI agent that can:

- 🔍 **Intelligently search** through documents
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
!pip install -qU langchain langchain-community langchain-qdrant langchain-huggingface qdrant-client fastembed flashrank langchain-core
!pip install --upgrade gradio

# Optional: if you want to use Ollama with local models
!pip install -qU langchain-ollama
```

---

## Step-by-Step Implementation

### Step 1: Configure the LLM

First, we set up our language model. We're using Google's Gemini 2.0 Flash for its excellent long-context capabilities.

```python
import os
import getpass
from langchain_google_genai import ChatGoogleGenerativeAI

# Set your Google API key
if not os.environ.get("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = getpass.getpass("Enter your Google API key: ")

# Initialize the LLM with zero temperature for consistent outputs
llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0)
```

**Alternative: Using Ollama with Local Models**

If you prefer to use local models with Ollama, you can replace the above code with:

```python
from langchain_ollama.chat_models import ChatOllama

# Initialize Ollama with your chosen model
llm = ChatOllama(
    model="qwen3:4b",  # or any other installed model, as long as it supports a context length of at least 256k tokens
    temperature=0
)
```

**Why this matters:** The LLM is the brain of our system. Gemini 2.0 Flash can handle very long contexts (up to 1M tokens), making it perfect for processing entire documents. If you use Ollama, make sure your chosen model supports long contexts and function calling.

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

# Initialize embeddings
dense_embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-mpnet-base-v2" #"intfloat/multilingual-e5-large"
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
from langchain_core.documents import Document

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
from typing import List
from pathlib import Path

def search_summaries(query: str, k: int = 3) -> List[dict]:
    """
    Search for the top K most relevant document summaries.
    
    Args:
        query: The search query
        k: Number of results to return
        
    Returns:
        List of relevant summary documents with their metadata
    """
    results = summary_vector_store.similarity_search(query, k=k)
    # Convert to dict format that can be passed between tools
    return [
        {
            "content": doc.page_content,
            "document_id": doc.metadata.get("document_id", ""),
            "source": doc.metadata.get("source", "")
        }
        for doc in results
    ]

def retrieve_full_documents(document_ids: List[str]) -> List[str]:
    """
    Retrieve complete documents based on document IDs.
    
    Args:
        document_ids: List of document IDs to retrieve
        
    Returns:
        List of full document contents
    """
    full_documents = []
    
    for doc_id in document_ids:
        if not doc_id:
            continue
            
        # Construct path to full document
        document_path = Path(DOCUMENT_DIR) / f"{doc_id}{'.md' if not doc_id.endswith('.md') else ''}"        
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

SYSTEM_PROMPT = """You are an intelligent document retrieval assistant specialized in answering questions accurately using available documents.

Your task follows this precise workflow:

1. **Analyze the question**: 
   - Understand what the user is asking
   - Identify the main topic and any sub-topics

2. **Rewrite and split if necessary**: 
   - Rephrase the question if it's unclear
   - If the question covers multiple different topics, split it into sub-queries
   - Each sub-query should address a single, specific topic

3. **Retrieve top X summary documents**: 
   - Decide how many summary documents to retrieve (the X value is your choice based on query complexity)
   - Use the search_summaries tool for each sub-query
   - Evaluate each retrieved summary to determine if it's relevant to the question
   - Discard irrelevant summaries

4. **Return exact document names**: 
   - From the relevant summaries, extract the exact document_id with extension
   - List which documents you're going to retrieve

5. **Retrieve complete documents and provide answer**: 
   - Use the retrieve_full_documents tool with the document_ids
   - Read the full documents to find the answer

6. **Verify document relevance**: 
   - Check if each complete document is actually pertinent to the question
   - Discard documents that are not relevant
   - **If NONE of the documents are relevant, GO BACK TO STEP 1 and try again with different search terms**

7. **Provide clear and detailed answer**: 
   - Give a comprehensive response based on the documents
   - Explain concepts clearly, assuming the user has no prior knowledge of the topic
   - Use simple language and avoid jargon when possible

8. **Verify answer completeness**: 
   - Check that your complete answer is relevant and fully addresses the question
   - Ensure all sub-queries (if any) have been answered

9. **If answer is not satisfactory**: 
   - **GO BACK TO STEP 1** and start the process again with a different approach

10. **Loop limit**: 
    - **Repeat this entire loop a MAXIMUM of 3 times**
    - After 3 complete attempts, if you're still not confident in your answer, politely ask the user to rephrase their question more clearly

**Critical rules**:
- You MUST follow steps 1-10 in order
- You MUST go back to step 1 if documents are not relevant (step 6) or answer is not satisfactory (step 9)
- You MUST NOT exceed 3 complete loops through the entire process
- Always base your answers strictly on the retrieved documents
- Never make up information that isn't in the documents
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

# Define the agent's decision-making node
def agent_node(state: MessagesState):
    """Agent decides which tool to call or generates final response"""
    return {
        "messages": llm_with_tools.invoke(
            [system_message] + state["messages"]
        )
    }

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

1. **Convert PDFs to Markdown** 
2. **Prepare your documents**: Place your documents in the `docs/` folder (in Markdown format)
3. **Generate summaries**: Create summaries for each document and save them in `summaries/` folder with `_summary.md` suffix
4. **Run the notebook**: Execute all cells in order
5. **Chat with your documents**: Use the Gradio interface to ask questions

### Example Interaction

```
User: "What are the best practices for data security?"

Agent: [Searches summaries] → [Finds 2 relevant documents] → 
       [Retrieves full documents] → [Generates comprehensive answer]
```

---

### Need Help Converting PDFs to Markdown?

If you need guidance on how to transform your PDFs into **Markdown**, check out this companion notebook for a complete walkthrough:

📘 **[PDF to Markdown Conversion Notebook](https://colab.research.google.com/gist/GiovanniPasq/fdea06b09b396fe626156e4f38b6e091/pdf_to_md.ipynb)**  

---

## Key Advantages

✅ **Simple**: Just a few lines of code to build a complete system  
✅ **Intelligent**: Agent makes smart decisions about retrieval  
✅ **Accurate**: Uses full document context instead of small chunks  
✅ **Self-correcting**: Can retry and refine searches  
✅ **Scalable**: Hybrid search handles large document collections  
✅ **Flexible**: Works with both cloud (Gemini) and local models (Ollama)

---

## Upcoming Features

Stay tuned! We're actively working on adding powerful new capabilities:

### 💬 Conversation Memory Management
The agent will maintain context across multiple questions, understanding references to previous queries.

**Example:**
```
User: "How do I install SQL?"
Agent: [Provides installation instructions]

User: "How do I update it?"
Agent: [Understands "it" refers to SQL and provides update instructions]
```

The system will analyze the conversation history and resolve pronouns and implicit references automatically.

### 🔄 Human-in-the-Loop Feedback
Interactive feedback loop to continuously improve answer quality.

**How it works:**
1. Agent provides an answer
2. System asks: "Was this answer helpful?"
3. If **YES**: Conversation continues normally
4. If **NO**: Agent re-analyzes the question, tries different retrieval strategies, and generates an improved response

### 📊 Document Chunking Alternative
Option to use intelligent document chunking instead of summaries for more granular retrieval.

**How it works:**
- Documents are split into semantically meaningful chunks
- Each chunk is embedded and stored separately
- Agent retrieves relevant chunks instead of full documents
- Ideal for very large documents or when specific sections are needed

---

## License

MIT License - Feel free to use this for learning and building your own projects!

---

## Contributing

Contributions are welcome! Open an issue or submit a pull request.
