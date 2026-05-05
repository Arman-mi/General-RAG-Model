Backend now supports on-demand indexing for any site (demo-scale).

**Backend**
- Create venv: `python -m venv .venv` then `source .venv/Scripts/activate` (PowerShell: `.venv\\Scripts\\Activate.ps1`)
- Install deps: `pip install -r src/backend/requirements.txt`
- Run API: `cd src/backend; uvicorn main:app --reload`

**Frontend**
- Open `src/frontend/index.html` (or serve it) and:
  1) Enter a website URL and click **Index**
  2) Once status is **Ready**, start chatting
