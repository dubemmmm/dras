# DRAS — dissertation review

Upload one or many dissertations (PDF, DOC or DOCX). An LLM drafts each WAPCP assessment, three at a time
(`DRAS_WORKERS`). The assessor opens each one, checks it against the document, edits anything, confirms, and
downloads the reports. Jobs, grades and edits are saved in `data/jobs/` and survive a restart:

- **Assessment report** — checklist and section comments in the WAPCP format.
- **Confidential scoring** — scores out of 60, for the assessor only.

## Run

```
cp .env.example .env     # add DRAS_OPENAI_API_KEY
uv run uvicorn server:app --port 8502
```

Open http://localhost:8502.

## Layout

| File | Job |
|---|---|
| `grader.py` | Extract text, call the LLM once, return a structured `Review` |
| `reports.py` | Build the two `.docx` reports |
| `server.py` | FastAPI: job queue, serve the document, locate quotes in PDFs, build reports |
| `frontend/` | Plain HTML, CSS and JS (no build step). PDFs render with pdf.js from cdnjs |

DOC and DOCX files are shown as PDF pages. The server tries, in order: Microsoft Word on macOS (exact Word pagination),
LibreOffice (`brew install --cask libreoffice`; page breaks can differ slightly), then a plain HTML view (`.doc` needs macOS `textutil`).

`legacy/` holds the old platform and the Streamlit version.
