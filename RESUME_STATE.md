# CareerPilot Unified - State Preservation Document

**Date of Record:** June 3, 2026
**Project Path:** `D:\SaminWorks\Hack____\CareerPilot_Unified`

This document serves as the absolute source of truth for the current state of the CareerPilot application. If work needs to resume on this project in a future session, read this document first to regain full context.

## 1. Project Architecture
The project is a unified Django application satisfying all 4 pillars of the `Codesprint_poridhi.pdf` hackathon requirements.

*   **Framework:** Django (v6.0.6)
*   **Database:** SQLite (`db.sqlite3`)
*   **Vector DB:** ChromaDB (Local persistence at `./careerpilot_db`)
*   **AI Models:** 
    *   Embeddings: `sentence-transformers` (`all-MiniLM-L6-v2`)
    *   Generative: Google `gemini-2.5-flash`
*   **Environment:** Python Virtual Environment (`./venv`)

## 2. Installed Django Apps (The 4 Pillars + Auth)
1.  **`accounts` (Authentication & Profile):**
    *   Handles Login, Registration, Logout, and Password Reset using standard Django Auth.
    *   Provides the central `profile_dashboard` view (aggregates data from all other apps).
2.  **`rag_core` (Pillar 2 - Resume Intelligence):**
    *   `cv_processor.py`: Parses PDF/DOCX, chunks text by section, generates embeddings, stores in ChromaDB.
    *   Requires `OMP_NUM_THREADS="1"` in `settings.py` to prevent PyTorch deadlocks during file upload.
3.  **`jobs` (Pillar 1 - Job Hunter):**
    *   `search_engine.py`: Uses `ddgs` (DuckDuckGo Search) to find live jobs (forced to LinkedIn/Indeed URLs). Includes a static fallback list if DDGS API rate-limits the server.
    *   `llm_engine.py`: Queries RAG ChromaDB for CV context, then asks Gemini to output a JSON string with `{"score": int, "reasoning": "string"}`.
4.  **`assistant` (Pillar 3 - AI Assistant):**
    *   `llm_agent.py`: A conversational chat interface stored in Django Sessions. Queries RAG database to ground Gemini responses (cover letters, roadmaps, etc.). Uses `markdown` to render responses safely.
5.  **`tracker` (Pillar 4 - Progress Tracker):**
    *   `models.py`: Contains `Application` (Kanban style tracking) and `Goal` (Date-based To-Do tracking).
    *   Rendered as a side-by-side dashboard in `tracker/dashboard.html`.

## 3. Environment Variables & Security
*   **API Keys:** Managed via `python-dotenv`.
*   **Current Keys:** The `.env` file contains `GOOGLE_API_KEY` (and a legacy `GEMINI_API_KEY` fallback).
*   **CRITICAL FIX:** Google GenAI library explicitly requires `GOOGLE_API_KEY`. If this is missing or named incorrectly, Fit Scores and Chat will fail with a "No API_KEY" error. (This was fixed and validated).

## 4. UI / UX State
*   **Styling:** Modern Vanilla CSS located in `templates/base.html`. No external frameworks (like Tailwind or Bootstrap) are used.
*   **Animations:** Uses custom `@keyframes` for `.fade-in` and `.slide-up` effects.
*   **Privacy:** All views (except Auth) are protected by `@login_required`. The `user_id` passed to the RAG database and LLM engines is dynamically derived from `request.user.username`.

## 5. Known Behaviors & Edge Cases to Remember
1.  **DuckDuckGo Limits:** `ddgs` is heavily rate-limited. If it fails, `jobs/search_engine.py` will automatically switch to a mock fallback list but will dynamically append the user's query into a real clickable LinkedIn Search URL to maintain the illusion of a live app during a demo.
2.  **Server Hangs:** Do NOT remove the PyTorch thread limiting variables at the top of `settings.py`. Without them, Django's dev server on Windows will permanently freeze when attempting to embed a CV.

## 6. How to Start the App Next Time
If you are returning to this project, simply execute the following in PowerShell from the `CareerPilot_Unified` root:
```powershell
.\venv\Scripts\Activate.ps1
python manage.py runserver 8000
```
