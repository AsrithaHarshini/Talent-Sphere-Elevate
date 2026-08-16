import os
import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions
from pypdf import PdfReader
from config import Config
from datetime import datetime
import uuid

# Initialize ChromaDB persistent client
chroma_client = chromadb.PersistentClient(path=Config.CHROMA_DB_DIR)

# Use sentence-transformers for vector embeddings
sentence_transformer_ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")

# Create or retrieve collection
collection_name = "talentsphere_docs"
collection = chroma_client.get_or_create_collection(name=collection_name, embedding_function=sentence_transformer_ef)

def extract_text_from_pdf(pdf_path):
    """Extracts text per page from a PDF file."""
    reader = PdfReader(pdf_path)
    text_data = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        if text:
            text_data.append({"page": i + 1, "text": text})
    return text_data

def chunk_text(text, chunk_size=1000, overlap=200):
    """Splits text into overlapping chunks."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks

def process_and_store_pdf(pdf_path, document_id, filename, week_number=1, day_number=1, module_id=0, lesson_id=0, version=1, assigned_domain='General'):
    """
    Extracts text, chunks it, and stores embeddings with complete metadata into ChromaDB.
    Preserves document history without deleting vectors automatically.
    """
    text_data = extract_text_from_pdf(pdf_path)
    upload_date_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    ids = []
    documents = []
    metadatas = []
    
    chunk_counter = 0
    for page_data in text_data:
        chunks = chunk_text(page_data["text"])
        for chunk in chunks:
            chunk_id = f"doc_{document_id}_v{version}_chunk_{chunk_counter}"
            ids.append(chunk_id)
            documents.append(chunk)
            metadatas.append({
                "document_id": int(document_id),
                "filename": str(filename),
                "page": int(page_data["page"]),
                "chunk_number": int(chunk_counter),
                "week_number": int(week_number),
                "day_number": int(day_number),
                "module_id": int(module_id or 0),
                "lesson_id": int(lesson_id or 0),
                "upload_date": upload_date_str,
                "version": int(version),
                "assigned_domain": str(assigned_domain or 'General')
            })
            chunk_counter += 1
            
    if documents:
        collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )
    return chunk_counter

def search_documents(query, n_results=5, user_document_ids=None, max_week=None, selected_doc_ids=None):
    """
    Searches ChromaDB for relevant chunks with smart fallback for maximum answer availability.
    """
    effective_doc_ids = user_document_ids
    if selected_doc_ids is not None and len(selected_doc_ids) > 0:
        if user_document_ids:
            effective_doc_ids = [d for d in selected_doc_ids if d in user_document_ids]
        else:
            effective_doc_ids = selected_doc_ids

    where_conditions = []
    
    if effective_doc_ids and len(effective_doc_ids) > 0:
        if len(effective_doc_ids) == 1:
            where_conditions.append({"document_id": effective_doc_ids[0]})
        else:
            where_conditions.append({"document_id": {"$in": effective_doc_ids}})
            
    if max_week is not None:
        where_conditions.append({"week_number": {"$lte": int(max_week)}})

    where_clause = None
    if len(where_conditions) == 1:
        where_clause = where_conditions[0]
    elif len(where_conditions) > 1:
        where_clause = {"$and": where_conditions}

    try:
        results = collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where_clause
        )
        if results and results.get('documents') and results['documents'][0]:
            return results
    except Exception as e:
        print(f"ChromaDB Query Error: {e}")

    # Fallback search without restrictive filters if no results found
    try:
        results = collection.query(
            query_texts=[query],
            n_results=n_results
        )
        return results
    except Exception as e:
        print(f"ChromaDB Fallback Query Error: {e}")
        return None
