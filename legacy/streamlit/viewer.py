"""Show the uploaded dissertation beside the feedback and jump to the passage a comment cites."""

import json
import re
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path

import mammoth
import pymupdf
import streamlit as st
from streamlit_pdf_viewer import pdf_viewer

PAGE_CSS = """
body { font-family: 'Times New Roman', serif; font-size: 15px; line-height: 1.5; padding: 16px 22px; color: #222; }
table { border-collapse: collapse; margin: 8px 0; } td, th { border: 1px solid #bbb; padding: 3px 6px; }
img { max-width: 100%; } ::selection { background: #ffe066; color: #000; } mark { background: #ffe066; }
"""

FIND_JS = """
<script>
const q = %s;
if (q) {
  const sel = window.getSelection(); sel.removeAllRanges();
  if (window.find(q, false, false, true, false, false, false)) {
    const range = sel.getRangeAt(0);
    range.startContainer.parentElement.scrollIntoView({block: 'center'});
    try { const m = document.createElement('mark'); range.surroundContents(m); sel.removeAllRanges(); } catch (e) {}
  }
}
</script>
"""


def _snippet(quote: str, words: int = 12) -> str:
    """Searching a long quote fails on line breaks and odd punctuation; the first words are enough."""
    return " ".join(re.sub(r"[“”]", '"', quote or "").replace("’", "'").split()[:words])


@st.cache_data(show_spinner=False)
def _to_html(filename: str, data: bytes) -> str:
    if filename.lower().endswith(".docx"):
        return mammoth.convert_to_html(BytesIO(data)).value
    with tempfile.TemporaryDirectory() as tmp:  # .doc: macOS converter keeps tables
        src = Path(tmp) / "source.doc"
        src.write_bytes(data)
        out = subprocess.run(["textutil", "-convert", "html", "-stdout", str(src)],
                             capture_output=True, text=True, check=False)
    return out.stdout or "<p>Could not display this document.</p>"


def _pdf_hits(data: bytes, snippet: str) -> list[dict]:
    if not snippet:
        return []
    with pymupdf.open(stream=data, filetype="pdf") as pdf:
        for number, page in enumerate(pdf, 1):
            rects = page.search_for(snippet)
            if rects:
                return [{"page": number, "x": r.x0, "y": r.y0, "width": r.width, "height": r.height,
                         "color": "#ffe066"} for r in rects]
    return []


def show(filename: str, data: bytes, quote: str = "", height: int = 760) -> None:
    snippet = _snippet(quote)
    if filename.lower().endswith(".pdf"):
        hits = _pdf_hits(data, snippet)
        pdf_viewer(data, height=height, annotations=hits, render_text=True, annotation_outline_size=2,
                   scroll_to_annotation=1 if hits else None, key=f"pdf-{len(hits)}-{hash(snippet)}")
        if snippet and not hits:
            st.caption("Couldn't find that passage in the document.")
        return
    body = re.sub(r"(?is)<script.*?</script>", "", _to_html(filename, data))  # the page runs in an iframe: no document scripts
    st.iframe(f"<style>{PAGE_CSS}</style>{body}{FIND_JS % json.dumps(snippet)}", height=height)
