import os
import shutil
import warnings
import sys
import re
from typing import List, Dict, Any
# --- Loaders ---
from langchain_community.document_loaders import (
    DirectoryLoader,
    PyPDFLoader,
    CSVLoader,
    TextLoader,
    UnstructuredExcelLoader,
    UnstructuredImageLoader
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores.utils import filter_complex_metadata
# --- Qdrant & Embeddings ---
from langchain_qdrant import QdrantVectorStore, FastEmbedSparse
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams

warnings.filterwarnings("ignore")
# --- CONFIGURATION ---
DATA_PATH = "data/"
QDRANT_URL = "http://localhost:6333"
COLLECTION_NAME = "logistics_db"
# --- MODELS ---
# Dense: Nomic Embed V1.5 (High performance, supports Matryoshka but we use standard)
DENSE_MODEL_NAME = "nomic-ai/nomic-embed-text-v1.5"
# Sparse: Generated via FastEmbed (uses Prithivida/Splade_PP_en_v1 or similar under the hood)
SPARSE_MODEL_NAME = "prithivida/Splade_PP_en_v1"


def extract_entities(text: str) -> Dict[str, List[str]]:
    """
    Extracts structured entities for 'Knowledge Graph' style lookups.
    - Product IDs (e.g., PROD-1234, SK-99)
    - Acronyms (e.g., ETA, BOL, POD)
    - Emails
    """
    entities = {
        "product_ids": [],
        "acronyms": [],
        "emails": []
    }

    # Regex Patterns
    # ID: Capital letters + hyphen + numbers (e.g., SKU-123)
    id_pattern = r'\b[A-Z]{2,4}-\d{3,}\b'
    # Acronyms: 2+ Capital letters (avoiding common words like 'I', 'A')
    acronym_pattern = r'\b[A-Z]{2,}\b'
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    entities["product_ids"] = list(set(re.findall(id_pattern, text)))
    entities["emails"] = list(set(re.findall(email_pattern, text)))

    # Filter acronyms to avoid noise
    raw_acronyms = set(re.findall(acronym_pattern, text))
    # Exclude common noise if needed, for now keep all CAPS
    entities["acronyms"] = list(raw_acronyms)
    return entities


def ingest_file(file_path):
    """
    Smart router that picks the correct loader based on extension.
    Returns a list of documents.
    """
    ext = os.path.splitext(file_path)[1].lower()
    docs = []
    try:
        if ext == ".pdf":
            loader = PyPDFLoader(file_path)
            docs = loader.load()
        elif ext == ".csv":
            loader = CSVLoader(file_path)
            docs = loader.load()
        elif ext in [".xlsx", ".xls"]:
            loader = UnstructuredExcelLoader(file_path, mode="elements")
            docs = loader.load()
        elif ext in [".txt", ".md", ".json"]:
            loader = TextLoader(file_path, encoding='utf-8')
            docs = loader.load()
        elif ext in [".jpg", ".jpeg", ".png", ".bmp"]:
            try:
                loader = UnstructuredImageLoader(file_path)
                docs = loader.load()
            except Exception as e:
                print(f"      ⚠️ Image Error ({os.path.basename(file_path)}): Tesseract ORC might be missing. {e}")
                return []
        else:
            print(f"      ⚠️ Skipping unsupported file: {os.path.basename(file_path)}")
            return []
        # --- ENRICHMENT: Knowledge Graph Logic ---
        for doc in docs:
            ents = extract_entities(doc.page_content)
            # Flatten for metadata (Vector DBs prefer flat lists/strings)
            doc.metadata["entities_product_ids"] = ", ".join(ents["product_ids"])
            doc.metadata["entities_acronyms"] = ", ".join(ents["acronyms"])
            doc.metadata["entities_emails"] = ", ".join(ents["emails"])

            # Construct a "graph_node" simulation in metadata
            doc.metadata["graph_node_id"] = f"{os.path.basename(file_path)}:{doc.metadata.get('page', 0)}"
        print(f"      - Loaded {len(docs)} initial segments from {os.path.basename(file_path)}")
        return docs
    except Exception as e:
        print(f"      ❌ Failed to load {os.path.basename(file_path)}: {e}")
        return []


def create_vector_db():
    print(f"--> Starting Hybrid Data Ingestion (Qdrant)...")
    print(f"    (Dense: {DENSE_MODEL_NAME} | Sparse: Splade)")
    if not os.path.exists(DATA_PATH):
        print(f"❌ Error: Data directory '{DATA_PATH}' not found.")
        return
    # 1. Load Files
    all_start_docs = []
    files_found = 0
    for root, dirs, files in os.walk(DATA_PATH):
        for file in files:
            file_path = os.path.join(root, file)
            files_found += 1
            file_docs = ingest_file(file_path)
            all_start_docs.extend(file_docs)
    if files_found == 0 or not all_start_docs:
        print("❌ No documents found/loaded.")
        return
    # 2. Split
    print(f"\n   ...Splitting {len(all_start_docs)} raw documents...")
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = text_splitter.split_documents(all_start_docs)
    chunks = filter_complex_metadata(chunks)
    print(f"      - Final Knowledge Base: {len(chunks)} chunks.")
    # 3. Initialize Embeddings & Qdrant
    print("   ...Initializing Models & Vector DB connection...")

    # Dense Embeddings
    dense_embeddings = FastEmbedEmbeddings(model_name=DENSE_MODEL_NAME)

    # Sparse Embeddings (Splade)
    sparse_embeddings = FastEmbedSparse(model_name=SPARSE_MODEL_NAME)
    # Connect to Qdrant
    client = QdrantClient(url=QDRANT_URL)

    # Re-create collection to ensure clean slate (Optional - Remove for incremental)
    if client.collection_exists(COLLECTION_NAME):
        print("      - Re-creating collection (Wiping old data)...")
        client.delete_collection(COLLECTION_NAME)
    # 4. Ingest
    print("\n   ...Indexing Vectors (This uses Hybrid: Dense + Sparse payload)...")
    try:
        QdrantVectorStore.from_documents(
            documents=chunks,
            embedding=dense_embeddings,
            sparse_embedding=sparse_embeddings,
            url=QDRANT_URL,
            collection_name=COLLECTION_NAME,
            retrieval_mode="hybrid",  # Enable hybrid search by default
            force_recreate=True
        )
        print(f"\n--> ✅ Ingestion Complete! Qdrant is live at {QDRANT_URL}")
        print(f"       - Dense Model: {DENSE_MODEL_NAME}")
        print(f"       - Graph Entities Extracted: Yes")

    except Exception as e:
        print(f"\n❌ Error creating database: {e}")
        print("👉 Make sure Docker is running: docker run -p 6333:6333 qdrant/qdrant")


if __name__ == "__main__":
    create_vector_db()
    
