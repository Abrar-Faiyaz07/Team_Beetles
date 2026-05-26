# CV Processing Pipeline & RAG Core Documentation

This document explains the architecture and implementation of the CV Processing Pipeline created for the **CareerPilot** hackathon project.

## 1. Project Overview
The goal was to build a pipeline that takes a resume (PDF or DOCX), processes it, and makes it searchable for an AI assistant. This is the foundation of **Pillar 2: Profile & Resume Intelligence (RAG Core)**.

## 2. Architecture: How it Works

The pipeline follows the **RAG (Retrieval-Augmented Generation)** pattern:

### Step A: Ingestion (File Reading)
- **Library:** `pypdf` for PDF files and `docx2txt` for Word documents.
- **Process:** We open the binary file, extract every line of text, and clean up extra whitespace.

### Step B: Chunking (Section Segmentation)
- **Strategy:** Instead of cutting text at random intervals (like every 500 characters), we use **Section-Based Chunking**.
- **Logic:** The script searches for keywords like "EXPERIENCE", "SKILLS", or "EDUCATION" on short lines. 
- **Benefit:** This keeps related information together (e.g., all your skills stay in one chunk), which makes the AI's response much more accurate.

### Step C: Embedding (Vectorization)
- **What is an Embedding?** It's a way to turn text into a list of numbers (a vector) that represents its meaning.
- **The Challenge:** Modern libraries like `sentence-transformers` require C++ compilers and heavy math libraries (`numpy`) that often fail to install on new Python versions.
- **The Solution:** I implemented a **Pure Python TF-IDF Vectorizer**.
    - **TF (Term Frequency):** How often a word appears in a section.
    - **IDF (Inverse Document Frequency):** How unique a word is across the whole CV.
    - **Result:** Words like "Python" or "Developer" get high scores in relevant sections, while common words like "the" or "and" are ignored.

### Step D: Vector DB (Storage & Search)
- **Storage:** All sections and their "number versions" (vectors) are saved in `vector_store.json`.
- **Search (Cosine Similarity):** When you search for "Python Developer", the script:
    1. Turns your query into a vector.
    2. Calculates the "angle" between your query vector and every CV section vector.
    3. Returns the sections with the highest similarity score (closest to 1.0).

---

## 3. Implementation Details (The Code)

- **`cv_processor.py`**: The heart of the system.
    - `PurePythonTFIDF`: Replaces heavy AI models with a lightweight math-based approach.
    - `SimpleVectorStore`: A simple JSON database that acts as your vector store.
    - `CVProcessor`: The coordinator that handles the workflow.

---

## 4. Learning Summary for Your Team
- **Why no API?** We chose a local approach to ensure the app works offline and during the hackathon without needing credit cards or tokens.
- **Why Pure Python?** It guarantees "it just works" on any computer, regardless of which Python version or OS (Windows/Linux) they use.
- **Is it "Real AI"?** While not a Neural Network, TF-IDF is a classic Machine Learning algorithm that is highly efficient for text matching and is still used in professional search engines like Elasticsearch.

---

## 5. Usage Commands (Windows)
```bash
# To "learn" a new resume (adds to the existing database):
py cv_processor.py "my_resume.pdf"

# To search across all processed resumes:
py cv_processor.py search "What are my skills?"
```

## 6. Troubleshooting
- **'python' is not recognized:** On Windows, use `py` instead of `python`.
- **ModuleNotFoundError:** Ensure you are using the virtual environment. Run `.\.venv\Scripts\Activate.ps1` in PowerShell.
- **Empty Search Results:** Make sure you have processed at least one CV first using the command in Step 5.
- **Corrupted vector_store.json:** If the script reports an error loading the JSON, delete `vector_store.json` and re-process your CVs.

## 7. Recent Improvements
- **Incremental Processing:** The pipeline now appends new CVs to the database instead of overwriting them.
- **Header Preservation:** Section headers (like "SKILLS") are now kept inside the indexed content to improve search relevance.
- **Resilient Loading:** Added checks for empty or corrupted storage files.
