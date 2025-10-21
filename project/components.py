# components.py
"""
Initializes and configures the core components:
- Directory creation
- LLM
- Embedding models (dense and sparse)
- Qdrant Client and Vector Store
"""

import os
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_qdrant.fastembed_sparse import FastEmbedSparse
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from langchain_ollama import ChatOllama
# from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_qdrant import QdrantVectorStore
from langchain_qdrant.qdrant import RetrievalMode

import config  # Import our settings

def initialize_directories():
    """Create necessary directories if they don't exist."""
    os.makedirs(config.DOCS_DIR, exist_ok=True)
    os.makedirs(config.PARENT_STORE_PATH, exist_ok=True)
    print("✓ Directories initialized.")

# --- 1. Initialize LLM ---
print("Initializing LLM...")
llm = ChatOllama(
    model=config.LLM_MODEL, 
    temperature=config.LLM_TEMPERATURE
)
# Alternative: Google Gemini
# llm = ChatGoogleGenerativeAI(
#     model=config.GEMINI_MODEL, 
#     temperature=config.LLM_TEMPERATURE
# )

# --- 2. Initialize Embeddings ---
print("Initializing Embedding models...")
dense_embeddings = HuggingFaceEmbeddings(
    model_name=config.DENSE_MODEL
)

sparse_embeddings = FastEmbedSparse(
    model_name=config.SPARSE_MODEL
)

# --- 3. Initialize Qdrant Client ---
print("Initializing Qdrant Client...")
client = QdrantClient(path=config.QDRANT_DB_PATH)

# --- 4. Collection Helper Function ---
def ensure_collection(collection_name):
    """Create the Qdrant collection if it doesn't exist."""
    try:
        embedding_dimension = len(dense_embeddings.embed_query("test query"))
    except Exception as e:
        print(f"Error calculating embedding dimension: {e}")
        # Set a common default dimension if calculation fails
        embedding_dimension = 768 
        print(f"Warning: Using default embedding dimension: {embedding_dimension}")

    if not client.collection_exists(collection_name):
        print(f"Creating collection: {collection_name}...")
        client.create_collection(
            collection_name=collection_name,
            vectors_config=qmodels.VectorParams(
                size=embedding_dimension,
                distance=qmodels.Distance.COSINE
            ),
            sparse_vectors_config={
                config.SPARSE_VECTOR_NAME: qmodels.SparseVectorParams()
            },
        )
        print(f"✓ Collection created: {collection_name}")
    else:
        print(f"✓ Collection already exists: {collection_name}")

# --- 5. Initialize Vector Store ---
print("Initializing Qdrant Vector Store...")
# Ensure the collection exists before initializing the store
ensure_collection(config.CHILD_COLLECTION)

child_vector_store = QdrantVectorStore(
    client=client,
    collection_name=config.CHILD_COLLECTION,
    embedding=dense_embeddings,
    sparse_embedding=sparse_embeddings,
    retrieval_mode=RetrievalMode.HYBRID,
    sparse_vector_name=config.SPARSE_VECTOR_NAME
)

print("\n✓ All core components initialized.\n")