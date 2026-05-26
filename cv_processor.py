"""
CareerPilot — CV Processing Pipeline
=====================================
Pipeline:  PDF/DOCX ingestion → section-aware chunking → embedding → ChromaDB

Dependencies (install once):
    pip install pymupdf python-docx chromadb sentence-transformers

Usage:
    python cv_pipeline.py --cv path/to/cv.pdf
    python cv_pipeline.py --cv path/to/cv.docx
    python cv_pipeline.py --cv path/to/cv.pdf --db_path ./career_pilot_db --collection my_cv

After running, you can query the DB with:
    python cv_pipeline.py --query "What are my skills?" --user_id user_123
"""

import argparse
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Optional

# ─── 1. TEXT EXTRACTION ──────────────────────────────────────────────────────

def extract_text_from_pdf(file_path: str) -> str:
    """Extract raw text from a PDF using PyMuPDF (fitz)."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        sys.exit("Install PyMuPDF:  pip install pymupdf")

    doc = fitz.open(file_path)
    pages = [page.get_text("text") for page in doc]
    doc.close()
    return "\n".join(pages)


def extract_text_from_docx(file_path: str) -> str:
    """Extract raw text from a .docx file."""
    try:
        from docx import Document
    except ImportError:
        sys.exit("Install python-docx:  pip install python-docx")

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
        sys.exit(f"Unsupported file type: {ext}. Use PDF or DOCX.")


# ─── 2. SECTION-AWARE CHUNKING ───────────────────────────────────────────────

# Common CV section headings (case-insensitive)
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
    # A heading is usually short (≤ 6 words) and matches one of our patterns
    if not cleaned or len(cleaned.split()) > 6:
        return None
    for section, pattern in SECTION_PATTERNS.items():
        if re.search(pattern, cleaned, re.IGNORECASE):
            return section
    return None


def chunk_cv_by_sections(raw_text: str) -> dict[str, str]:
    """
    Split CV text into labelled sections.
    Returns a dict: { section_label: section_text }
    Unsectioned content is grouped under 'general'.
    """
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

    # Join lines back and strip empty sections
    return {
        k: "\n".join(v).strip()
        for k, v in sections.items()
        if "\n".join(v).strip()
    }


def split_into_chunks(text: str, max_chars: int = 500, overlap: int = 50) -> list[str]:
    """
    Further split a long section into overlapping sub-chunks.
    Splits on sentence boundaries where possible.
    """
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks, current = [], ""

    for sentence in sentences:
        if len(current) + len(sentence) <= max_chars:
            current += (" " if current else "") + sentence
        else:
            if current:
                chunks.append(current.strip())
            # Start new chunk with overlap from end of previous
            current = current[-overlap:] + " " + sentence if current else sentence

    if current.strip():
        chunks.append(current.strip())

    return chunks if chunks else [text[:max_chars]]


def build_chunks(sections: dict[str, str], max_chars: int = 500) -> list[dict]:
    """
    Produce a flat list of chunk records ready for embedding.
    Each record: { id, section, text, char_count }
    """
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
    """Load a sentence-transformers model (fast, free, local)."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        sys.exit("Install sentence-transformers:  pip install sentence-transformers")

    print(f"[embed] Loading model '{model_name}' …")
    return SentenceTransformer(model_name)


def embed_chunks(chunks: list[dict], model) -> list[dict]:
    """Add an 'embedding' list to each chunk record."""
    texts = [c["text"] for c in chunks]
    print(f"[embed] Embedding {len(texts)} chunks …")
    embeddings = model.encode(texts, show_progress_bar=True, convert_to_numpy=True)
    for chunk, emb in zip(chunks, embeddings):
        chunk["embedding"] = emb.tolist()
    return chunks


# ─── 4. VECTOR DB (ChromaDB) ─────────────────────────────────────────────────

def get_or_create_collection(db_path: str, collection_name: str):
    """Return a ChromaDB persistent collection."""
    try:
        import chromadb
    except ImportError:
        sys.exit("Install chromadb:  pip install chromadb")

    client = chromadb.PersistentClient(path=db_path)
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},   # cosine similarity
    )
    print(f"[chroma] Using collection '{collection_name}' at '{db_path}'")
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
    print(f"[chroma] Stored {len(ids)} chunks.")


# ─── 5. QUERY HELPER ─────────────────────────────────────────────────────────

def query_cv(
    query_text: str,
    db_path: str,
    collection_name: str,
    user_id: str,
    top_k: int = 5,
    model_name: str = "all-MiniLM-L6-v2",
) -> list[dict]:
    """
    Semantic search over the stored CV chunks.
    Returns the top_k most relevant chunks with metadata.
    """
    model      = load_embedding_model(model_name)
    collection = get_or_create_collection(db_path, collection_name)

    query_embedding = model.encode([query_text])[0].tolist()
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where={"user_id": user_id},        # filter to this user's CV only
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
            "score":    round(1 - dist, 4),   # cosine similarity (0–1)
            "user_id":  meta["user_id"],
        })
    return hits


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
    print(f"\n{'='*55}")
    print(f"  CareerPilot CV Pipeline")
    print(f"{'='*55}")
    print(f"  File    : {cv_path}")
    print(f"  User    : {user_id}")
    print(f"  DB path : {db_path}")
    print(f"{'='*55}\n")

    # Step 1 — Extract
    print("[1/4] Extracting text …")
    raw_text = extract_text(cv_path)
    print(f"      {len(raw_text)} characters extracted.\n")

    # Step 2 — Chunk
    print("[2/4] Chunking by sections …")
    sections = chunk_cv_by_sections(raw_text)
    print(f"      Sections found: {list(sections.keys())}")
    chunks   = build_chunks(sections, max_chars=chunk_size)
    print(f"      Total chunks  : {len(chunks)}\n")

    # Step 3 — Embed
    print("[3/4] Embedding …")
    model  = load_embedding_model(model_name)
    chunks = embed_chunks(chunks, model)
    print()

    # Step 4 — Store
    print("[4/4] Storing in ChromaDB …")
    col = get_or_create_collection(db_path, collection)
    store_chunks(col, chunks, user_id=user_id, cv_filename=Path(cv_path).name)

    print(f"\n✅  Pipeline complete. {len(chunks)} chunks stored for user '{user_id}'.")
    print(f"    Vector DB at: {os.path.abspath(db_path)}\n")

    return chunks   # useful when called as a module


# ─── 7. CLI ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CareerPilot CV Processing Pipeline")

    # Pipeline mode
    parser.add_argument("--cv",         help="Path to CV file (PDF or DOCX)")
    parser.add_argument("--user_id",    default="user_001", help="Unique user identifier")
    parser.add_argument("--db_path",    default="./careerpilot_db", help="ChromaDB storage path")
    parser.add_argument("--collection", default="cv_chunks",        help="ChromaDB collection name")
    parser.add_argument("--model",      default="all-MiniLM-L6-v2", help="Sentence-transformer model")
    parser.add_argument("--chunk_size", default=500, type=int,      help="Max chars per chunk")

    # Query mode
    parser.add_argument("--query", help="Semantic query against stored CV (skips ingestion)")
    parser.add_argument("--top_k", default=5, type=int, help="Number of results to return")

    args = parser.parse_args()

    if args.query:
        # ── Query mode ──────────────────────────────────────────────────────
        results = query_cv(
            query_text      = args.query,
            db_path         = args.db_path,
            collection_name = args.collection,
            user_id         = args.user_id,
            top_k           = args.top_k,
            model_name      = args.model,
        )
        print(f"\nTop {len(results)} results for: \"{args.query}\"\n")
        for i, r in enumerate(results, 1):
            print(f"  [{i}] Section: {r['section']}  |  Score: {r['score']}")
            print(f"      {r['text'][:200]}{'…' if len(r['text']) > 200 else ''}\n")

    elif args.cv:
        # ── Pipeline mode ────────────────────────────────────────────────────
        if not os.path.exists(args.cv):
            sys.exit(f"File not found: {args.cv}")

        run_pipeline(
            cv_path    = args.cv,
            db_path    = args.db_path,
            collection = args.collection,
            user_id    = args.user_id,
            model_name = args.model,
            chunk_size = args.chunk_size,
        )
    else:
        parser.print_help()