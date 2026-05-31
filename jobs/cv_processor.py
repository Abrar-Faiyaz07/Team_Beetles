import os
import re
import uuid
from pathlib import Path
from typing import Optional

# ─── 1. TEXT EXTRACTION ──────────────────────────────────────────────────────

def extract_text_from_pdf(file_path: str) -> str:
    """Extract raw text from a PDF using PyMuPDF (fitz)."""
    import fitz
    doc = fitz.open(file_path)
    pages = [page.get_text("text") for page in doc]
    doc.close()
    return "\n".join(pages)


def extract_text_from_docx(file_path: str) -> str:
    """Extract raw text from a .docx file."""
    from docx import Document
    doc = Document(file_path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def extract_text(file_path: str) -> str:
    """Auto-detect format and extract text."""
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        return extract_text_from_pdf(file_path)
    elif ext in (".docx", ".doc"):
        return extract_text_from_docx(file_path)
    else:
        raise ValueError(f"Unsupported file type: {ext}. Use PDF or DOCX.")


# ─── 2. SECTION-AWARE CHUNKING ───────────────────────────────────────────────

SECTION_PATTERNS = {
    "personal_info":   r"(personal\s+info|contact|about\s+me|profile|summary|objective)",
    "education":       r"(education|academic|qualification|degree|university|college)",
    "experience":      r"(experience|employment|work\s+history|career|internship|job)",
    "skills":          r"(skill|competenc|technolog|tool|stack|language|framework|expertise)",
    "projects":        r"(project|portfolio|work\s+sample|side\s+project|open.?source)",
    "certifications":  r"(certif|award|honor|achievement|course|training|badge)",
    "publications":    r"(publication|paper|research|journal|conference|thesis)",
    "extracurricular": r"(extra.?curricular|volunteer|activit|club|society|leadership)",
    "references":      r"(reference|referee)",
}

def classify_heading(line: str) -> Optional[str]:
    """Return the section key if the line looks like a CV section heading."""
    cleaned = line.strip()
    if not cleaned or len(cleaned.split()) > 6:
        return None
    for section, pattern in SECTION_PATTERNS.items():
        if re.search(pattern, cleaned, re.IGNORECASE):
            return section
    return None


def chunk_cv_by_sections(raw_text: str) -> dict[str, str]:
    """Split CV text into labelled sections."""
    lines = raw_text.splitlines()
    sections: dict[str, list[str]] = {}
    current_section = "general"

    for line in lines:
        heading = classify_heading(line)
        if heading:
            current_section = heading
            sections.setdefault(current_section, [])
        else:
            sections.setdefault(current_section, []).append(line)

    return {
        k: "\n".join(v).strip()
        for k, v in sections.items()
        if "\n".join(v).strip()
    }


def split_into_chunks(text: str, max_chars: int = 500, overlap: int = 50) -> list[str]:
    """Further split a long section into overlapping sub-chunks."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks, current = [], ""

    for sentence in sentences:
        if len(current) + len(sentence) <= max_chars:
            current += (" " if current else "") + sentence
        else:
            if current:
                chunks.append(current.strip())
            current = current[-overlap:] + " " + sentence if current else sentence

    if current.strip():
        chunks.append(current.strip())

    return chunks if chunks else [text[:max_chars]]


def build_chunks(sections: dict[str, str], max_chars: int = 500) -> list[dict]:
    """Produce a flat list of chunk records ready for embedding."""
    records = []
    for section, content in sections.items():
        sub_chunks = split_into_chunks(content, max_chars=max_chars)
        for i, chunk_text in enumerate(sub_chunks):
            records.append({
                "id":         f"{section}_{i}_{uuid.uuid4().hex[:8]}",
                "section":    section,
                "text":       chunk_text,
                "char_count": len(chunk_text),
            })
    return records


# ─── 3. EMBEDDING ────────────────────────────────────────────────────────────

def load_embedding_model(model_name: str = "all-MiniLM-L6-v2"):
    """Load a sentence-transformers model."""
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model_name)


def embed_chunks(chunks: list[dict], model) -> list[dict]:
    """Add an 'embedding' list to each chunk record."""
    texts = [c["text"] for c in chunks]
    embeddings = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
    for chunk, emb in zip(chunks, embeddings):
        chunk["embedding"] = emb.tolist()
    return chunks


# ─── 4. VECTOR DB (ChromaDB) ─────────────────────────────────────────────────

def get_or_create_collection(db_path: str, collection_name: str):
    """Return a ChromaDB persistent collection."""
    import chromadb
    client = chromadb.PersistentClient(path=db_path)
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )
    return collection


def store_chunks(collection, chunks: list[dict], user_id: str, cv_filename: str):
    """Upsert all chunk embeddings into ChromaDB."""
    ids        = [c["id"] for c in chunks]
    embeddings = [c["embedding"] for c in chunks]
    documents  = [c["text"] for c in chunks]
    metadatas  = [
        {
            "section":     c["section"],
            "char_count":  c["char_count"],
            "user_id":     user_id,
            "cv_filename": cv_filename,
        }
        for c in chunks
    ]

    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
    )
    return len(ids)


# ─── 5. QUERY HELPER ─────────────────────────────────────────────────────────

def query_cv(
    query_text: str,
    db_path: str,
    collection_name: str,
    user_id: str,
    top_k: int = 5,
    model_name: str = "all-MiniLM-L6-v2",
) -> list[dict]:
    """Semantic search over the stored CV chunks."""
    model      = load_embedding_model(model_name)
    collection = get_or_create_collection(db_path, collection_name)

    query_embedding = model.encode([query_text])[0].tolist()
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where={"user_id": user_id},
        include=["documents", "metadatas", "distances"],
    )

    hits = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        hits.append({
            "text":     doc,
            "section":  meta["section"],
            "score":    round(1 - dist, 4),
            "user_id":  meta["user_id"],
        })
    return hits


def get_full_cv_text(db_path: str, collection_name: str, user_id: str) -> str:
    """Retrieve the full CV text from ChromaDB for a user."""
    collection = get_or_create_collection(db_path, collection_name)
    results = collection.get(
        where={"user_id": user_id},
        include=["documents", "metadatas"],
    )
    
    if not results["documents"]:
        return ""
    
    # Group by section and join
    sections = {}
    for doc, meta in zip(results["documents"], results["metadatas"]):
        section = meta.get("section", "general")
        if section not in sections:
            sections[section] = []
        sections[section].append(doc)
    
    full_text = ""
    for section, texts in sections.items():
        full_text += f"\n[{section.upper()}]\n"
        full_text += " ".join(texts)
    
    return full_text.strip()


# ─── 6. MAIN PIPELINE ────────────────────────────────────────────────────────

def run_pipeline(
    cv_path: str,
    db_path: str     = "./careerpilot_db",
    collection: str  = "cv_chunks",
    user_id: str     = "default_user",
    model_name: str  = "all-MiniLM-L6-v2",
    chunk_size: int  = 500,
):
    """End-to-end: ingest → chunk → embed → store."""
    # Step 1 — Extract
    raw_text = extract_text(cv_path)

    # Step 2 — Chunk
    sections = chunk_cv_by_sections(raw_text)
    chunks   = build_chunks(sections, max_chars=chunk_size)

    # Step 3 — Embed
    model  = load_embedding_model(model_name)
    chunks = embed_chunks(chunks, model)

    # Step 4 — Store
    col = get_or_create_collection(db_path, collection)
    count = store_chunks(col, chunks, user_id=user_id, cv_filename=Path(cv_path).name)

    return {
        "chunks_stored": count,
        "sections_found": list(sections.keys()),
        "raw_text": raw_text,
    }