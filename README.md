# General RAG Model (Website → Chat)

Live demo: https://general-rag-model.onrender.com/

This is a small demo app that lets you:
1) Enter a website URL
2) Crawl and extract text from a limited set of pages
3) Build embeddings and a temporary vector index
4) Ask questions that are grounded in retrieved excerpts, with clickable citations

The app replaces the index each time you index a new site (so storage does not grow).

## How it works

**Indexing (crawl → clean → embed)**
- The frontend calls `POST /api/site` with a user-provided URL.
- The backend crawls a small number of same-site HTML pages, extracts main text, splits it into chunks, embeds the chunks, and stores them in a fresh Chroma collection for that run.
- The frontend polls `GET /api/site/{site_id}` until the status is `done`.

**Chat (RAG)**
- The frontend calls `POST /api/chat` with `{ message, site_id }`.
- The backend retrieves relevant chunks from Chroma, then asks the LLM to answer using only those excerpts.
- The response includes `citations` (URLs used).

## Run locally

### Backend
1) Create a venv: `python -m venv .venv`
2) Activate it:
   - PowerShell: `.venv\\Scripts\\Activate.ps1`
   - Git Bash: `source .venv/Scripts/activate`
3) Install deps: `pip install -r src/backend/requirements.txt`
4) Set env var `OPENAI_API_KEY` (for example in `src/backend/.env`)
5) Run: `cd src/backend; uvicorn main:app --reload`

### Frontend
- Open `src/frontend/index.html` (or serve the `src/frontend` folder).
- Enter a website URL, click **Index website**, then chat once it’s **Ready**.

## Notes / limitations
- This is a demo crawler: it only follows same-site links and skips most non-HTML assets.
- It intentionally limits pages for speed and cost.
- The backend refuses to crawl localhost/private network hosts to reduce SSRF risk.
