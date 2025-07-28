import lancedb
from sentence_transformers import SentenceTransformer
import hashlib
from typing import List, Dict, Any
import pyarrow as pa

# --- FIX: Load the model once and reuse it. ---
# This prevents the slow model loading on every database instantiation.
MODEL = SentenceTransformer("all-MiniLM-L6-v2")

class FastHTMLDatabase:
    def __init__(self, db_path="./lancedb"):
        self.db_path = db_path
        # Use the pre-loaded global model
        self.model = MODEL
        self.db = lancedb.connect(db_path)
        self.setup_tables()
    
    def setup_tables(self):
        """Create tables if they don't exist"""
        table_names = self.db.table_names()
        
        if "fasthtml_docs" not in table_names:
            docs_schema = pa.schema([
                pa.field("id", pa.string()),
                pa.field("url", pa.string()),
                pa.field("title", pa.string()),
                pa.field("xml_content", pa.string()),
                pa.field("url_hash", pa.string())
            ])
            self.db.create_table("fasthtml_docs", schema=docs_schema)
        
        if "fasthtml_chunks" not in table_names:
            sample_embedding = self.model.encode("sample text")
            chunks_schema = pa.schema([
                pa.field("id", pa.string()),
                pa.field("doc_id", pa.string()),
                pa.field("url", pa.string()),
                pa.field("section_title", pa.string()),
                pa.field("section_level", pa.int32()),
                pa.field("content", pa.string()),
                # The field name 'vector' is important for LanceDB to auto-detect
                pa.field("vector", pa.list_(pa.float32(), len(sample_embedding)))
            ])
            # --- FIX: Removed the unsupported 'vector_column_name' argument ---
            self.db.create_table("fasthtml_chunks", schema=chunks_schema)

        self.docs_table = self.db.open_table("fasthtml_docs")
        self.chunks_table = self.db.open_table("fasthtml_chunks")
    
    def url_exists(self, url: str) -> bool:
        """Check if URL already exists in database"""
        url_hash = hashlib.md5(url.encode()).hexdigest()
        # Use count_rows for an efficient check
        return self.docs_table.count_rows(f"url_hash = '{url_hash}'") > 0
    
    def store_document(self, url: str, xml_content: str, title: str = ""):
        """Store full XML document"""
        url_hash = hashlib.md5(url.encode()).hexdigest()
        doc_id = f"doc_{url_hash}"
        
        doc_data = {
            "id": doc_id, "url": url, "title": title,
            "xml_content": xml_content, "url_hash": url_hash
        }
        
        self.docs_table.add([doc_data])
        return doc_id
    
    def store_chunks(self, doc_id: str, url: str, chunks: List[Dict[str, Any]]):
        """Store chunked sections with embeddings"""
        chunk_data = []
        
        # Batch encode for better performance
        contents_to_encode = [chunk['content'] for chunk in chunks]
        if not contents_to_encode: return
        
        embeddings = self.model.encode(contents_to_encode)
        
        for i, chunk in enumerate(chunks):
            chunk_record = {
                "id": f"{doc_id}_chunk_{i}",
                "doc_id": doc_id,
                "url": url,
                "section_title": chunk.get('title', ''),
                "section_level": chunk.get('level', 1),
                "content": chunk['content'],
                "vector": embeddings[i].tolist()
            }
            chunk_data.append(chunk_record)
        
        if chunk_data:
            self.chunks_table.add(chunk_data)
    
    def search_similar(self, query: str, limit: int = 5) -> List[Dict]:
        """Search for similar chunks"""
        query_embedding = self.model.encode(query)
        
        results = (self.chunks_table
                   .search(query_embedding)
                   .limit(limit)
                   .to_list())
        
        return results
    
    def get_document_count(self) -> int:
        """Get total number of documents efficiently."""
        return self.docs_table.count_rows()
    
    def get_chunk_count(self) -> int:
        """Get total number of chunks efficiently."""
        return self.chunks_table.count_rows()
    
    def get_all_documents(self) -> List[Dict]:
        """Get all documents with basic info"""
        df = self.docs_table.to_pandas()
        return df[["id", "url", "title"]].to_dict('records')

    def get_document_xml(self, doc_id: str) -> str:
        """Get XML content for a specific document"""
        df = self.docs_table.to_pandas()
        filtered = df[df['id'] == doc_id]
        return filtered['xml_content'].iloc[0] if not filtered.empty else ""
    
    def get_document_chunks(self, doc_id: str) -> List[Dict]:
        """Get all chunks for a specific document"""
        df = self.chunks_table.to_pandas()
        filtered = df[df['doc_id'] == doc_id]
        return filtered[["id", "section_title", "content", "section_level"]].to_dict('records')
