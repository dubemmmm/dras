# DRAS — Dissertation Review Automation System

DRAS is a restricted, single-assessor pilot for evidence-backed WAPCP dissertation review. It is decision support, not an autonomous examiner, and has **not** been validated for academic reliability or production use.

The repository provides a Streamlit dashboard, private FastAPI API, SQLAlchemy/Alembic persistence, Celery worker hook, deterministic PDF/DOCX extraction checks, assessor-controlled checklist and scoring, validation/finalization gates, separated DOCX reports, and deletion tombstones. New-assessment intake extracts candidate name, registration number, supervisor, and dissertation title from the uploaded title page before asking the assessor to confirm them.

## Run locally

Requires Python 3.12–3.15 and `uv`.

```bash
cp .env.example .env
uv sync --dev
uv run alembic upgrade head
uv run uvicorn dras.api:app --reload
uv run streamlit run src/dras/dashboard.py
```

To enable assessor-authorized OpenAI review locally, put a newly created project API key only in
the ignored `.env` file (never in `.env.example`), then restart the API:

```dotenv
DRAS_OPENAI_API_KEY=your-new-project-key
```

In the review workspace, expand **External AI processing**, confirm the server reports that the
key is configured, approve processing for that specific assessment, and then select
**Prepare review**. Requests use the Responses API with structured outputs, no tools, and
`store=False`; model suggestions still require assessor approval.

Or configure PostgreSQL/Redis in `.env` and run `docker compose up --build`.

## Safety boundaries

- The API is private-service authenticated and enforces an assessor email allowlist and per-assessment ownership.
- Browser clients do not call the API directly; Streamlit supplies the private service credential.
- Every mutation requires an idempotency header and expected version where a record already exists. Version conflicts return `409`.
- Source validation checks extension, MIME declaration, signature, archive safety, encryption, size, and page limits. Production must provide a real malware-scanning service; the local adapter recognizes only the EICAR test signature.
- External AI processing is disabled without an API key and institutional authorization. The provider uses the Responses API, strict Pydantic parsing, `store=False`, no tools, and versioned injection-resistant instructions.
- Word uploads are converted to a private PDF before page-aware extraction. DRAS uses LibreOffice when installed and falls back to Microsoft Word automation on macOS. The first macOS conversion may ask you to allow Terminal or Python to control Microsoft Word under **System Settings → Privacy & Security → Automation**. If conversion is unavailable, the original Word file is preserved and automated review remains blocked by an extraction warning. OCR is deliberately out of scope.
- Final reports consume only a passing assessor-approved snapshot. The student report excludes the standalone Literature Review review and all score data. In production, finalization fails closed unless LibreOffice produces nonblank PDFs; release operations must additionally render those files to PNGs and visually inspect them.
- Deletion removes active local objects and database rows, leaving only the required tombstone. Configure backup expiry to seven days or less.

See [docs/security.md](docs/security.md) for deployment controls and residual risks.

## Verification

```bash
uv run ruff check .
uv run pytest --cov=dras
```

DOCX report visual QA additionally requires LibreOffice and Poppler:

```bash
env TMPDIR=/private/tmp python /path/to/documents-skill/render_docx.py report.docx --output_dir render --emit_pdf
```

## Pilot limitations

No OCR, multi-assessor workflow, electronic signatures, institutional pass/fail decision, plagiarism detection, bibliographic existence lookup, or university-system integration is implemented. The academic AI review orchestration is intentionally gated pending representative, assessor-reviewed evaluation data and formal authorization.

