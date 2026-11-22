# DRAS as a container (built for Render's free tier: 512 MB RAM). Listens on $PORT, 10000 if unset.
FROM python:3.12-slim

# LibreOffice turns DOC/DOCX into the page view and reads .doc text; the fonts stand in for Word's.
RUN apt-get update && apt-get install -y --no-install-recommends \
      libreoffice-writer fonts-liberation fonts-dejavu fonts-crosextra-carlito fonts-crosextra-caladea \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Create the app folder as the user: older Docker builders make WORKDIR root-owned, and uv then cannot write to it.
RUN useradd -m -u 1000 user && mkdir -p /home/user/app && chown user:user /home/user/app
USER user
# DRAS_WORKERS=1: three LibreOffice conversions at once do not fit in 512 MB; raise it on a bigger machine.
ENV HOME=/home/user DRAS_DATA=/home/user/data DRAS_WORKERS=1 UV_COMPILE_BYTECODE=1
WORKDIR /home/user/app

COPY --chown=user pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY --chown=user grader.py reports.py server.py ./
COPY --chown=user frontend ./frontend

EXPOSE 10000
# One process only: the job queue lives in memory.
CMD ["sh", "-c", "exec uv run --no-sync uvicorn server:app --host 0.0.0.0 --port ${PORT:-10000}"]
