# indexing.py
"""
Runnable script to process markdown files in DOCS_DIR
and index them into Qdrant (child chunks) and JSON files (parent chunks).

Run with: python indexing.py
"""

import os
import glob
import json
from pathlib import Path
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter
)

import config
from components import child_vector_store, initialize_directories

def index_documents():
    """Index documents using the hierarchical Parent/Child strategy."""
    print("\n" + "="*50)
    print("Starting Hierarchical Indexing")
    print("="*50 + "\n")
    
    # Parent splitter: by Markdown headers
    parent_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=config.HEADERS_TO_SPLIT_ON,
        strip_headers=False
    )
    
    # Child splitter: by character count
    child_splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHILD_CHUNK_SIZE,
        chunk_overlap=config.CHILD_CHUNK_OVERLAP
    )
    
    all_child_chunks = []
    all_parent_pairs = []
    
    # Check if docs directory has files
    md_files = sorted(glob.glob(os.path.join(config.DOCS_DIR, "*.md")))
    if not md_files:
        print(f"⚠️  No .md files found in {config.DOCS_DIR}/")
        print("Please add your Markdown documents to continue.")
        return
    
    # Process each document
    for doc_path_str in md_files:
        doc_path = Path(doc_path_str)
        print(f"📄 Processing: {doc_path.name}")
        
        try:
            with open(doc_path, "r", encoding="utf-8") as f:
                md_text = f.read()
        except Exception as e:
            print(f"❌ Error reading {doc_path.name}: {e}")
            continue
        
        # Split into parent chunks
        parent_chunks = parent_splitter.split_text(md_text)
        
        for i, p_chunk in enumerate(parent_chunks):
            # Add metadata
            p_chunk.metadata["source"] = str(doc_path)
            parent_id = f"{doc_path.stem}_parent_{i}"
            p_chunk.metadata["parent_id"] = parent_id
            
            # Store parent reference
            all_parent_pairs.append((parent_id, p_chunk))
            
            # Split into child chunks
            child_chunks = child_splitter.split_documents([p_chunk])
            all_child_chunks.extend(child_chunks)
    
    # Save child chunks to Qdrant
    if all_child_chunks:
        print(f"\n🔍 Indexing {len(all_child_chunks)} child chunks into Qdrant...")
        try:
            child_vector_store.add_documents(all_child_chunks)
            print("✓ Child chunks indexed successfully")
        except Exception as e:
            print(f"❌ Error indexing child chunks: {e}")
            return
    else:
        print("⚠️  No child chunks to index")
        return
    
    # Save parent chunks to JSON files
    if all_parent_pairs:
        print(f"💾 Saving {len(all_parent_pairs)} parent chunks to JSON...")
        
        # Clear existing parent files
        for item in os.listdir(config.PARENT_STORE_PATH):
            os.remove(os.path.join(config.PARENT_STORE_PATH, item))
        
        # Save each parent chunk
        for parent_id, doc in all_parent_pairs:
            doc_dict = {
                "page_content": doc.page_content,
                "metadata": doc.metadata
            }
            file_path = os.path.join(config.PARENT_STORE_PATH, f"{parent_id}.json")
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(doc_dict, f, ensure_ascii=False, indent=2)
        
        print("✓ Parent chunks saved successfully")
    
    print("\n" + "="*50)
    print("✓ Indexing Complete!")
    print("="*50 + "\n")

if __name__ == "__main__":
    # Ensure directories exist before indexing
    initialize_directories()
    # Run the indexing process
    index_documents()