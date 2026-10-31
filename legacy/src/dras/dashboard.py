from __future__ import annotations

import base64
import hashlib
from uuid import uuid4

import httpx
import streamlit as st

from dras.config import Settings

# Streamlit reruns the script in the same process. Build a fresh settings object
# so local .env changes do not remain hidden behind the API's process-wide cache.
settings = Settings()
API = settings.api_base_url
if "://" not in API:
    API = f"http://{API}"
TOKEN = settings.service_token
ALLOWLIST = settings.allowed_assessors

st.set_page_config(page_title="DRAS — Restricted pilot", page_icon="📚", layout="wide")
st.markdown("""
<style>
:root { --ink:#12212b; --blue:#174f68; --paper:#f6f4ee; --line:#d8d4ca; }
.stApp { background:var(--paper); color:var(--ink); }
[data-testid="stSidebar"] { background:#e9eee9; border-right:1px solid var(--line); }
.pilot { padding:.75rem 1rem; border:1px solid #d5b65c; background:#fff8df; border-radius:.4rem; }
.eyebrow { letter-spacing:.12em; text-transform:uppercase; font-size:.75rem; color:var(--blue); font-weight:700; }
</style>
""", unsafe_allow_html=True)


def current_email() -> str:
    try:
        if getattr(st, "user", None) and st.user.is_logged_in:
            return str(st.user.email).lower()
    except Exception:
        pass
    if settings.env == "development":
        return st.sidebar.text_input("Development assessor email", next(iter(ALLOWLIST)))
    st.error("Sign in through the configured OIDC provider to continue.")
    if st.button("Sign in"):
        st.login()
    st.stop()


email = current_email().strip().lower()
if email not in ALLOWLIST:
    st.error("This account is not on the assessor allowlist.")
    st.stop()


def headers(mutation: bool = False, version: int | None = None) -> dict[str, str]:
    result = {"X-Service-Token": TOKEN, "X-Assessor-Email": email}
    if mutation:
        result["Idempotency-Key"] = str(uuid4())
    if version is not None:
        result["Expected-Version"] = str(version)
    return result


def request(method: str, path: str, **kwargs):
    try:
        timeout = 600 if path.endswith("/review") else 120
        response = httpx.request(method, f"{API}{path}", timeout=timeout, **kwargs)
        response.raise_for_status()
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            st.error(
                f"The private API returned an invalid response for {path} "
                f"(HTTP {response.status_code})."
            )
    except httpx.HTTPStatusError as exc:
        try:
            payload = exc.response.json()
            detail = payload.get("detail", str(exc)) if isinstance(payload, dict) else payload
        except ValueError:
            detail = exc.response.text.strip() or f"Private API returned HTTP {exc.response.status_code}"
        st.error(str(detail))
    except httpx.HTTPError as exc:
        st.error(f"Private API unavailable: {exc}")
    return None


def binary_request(path: str) -> bytes | None:
    try:
        response = httpx.get(f"{API}{path}", headers=headers(), timeout=120)
        response.raise_for_status()
        return response.content
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get("detail", str(exc))
        except ValueError:
            detail = exc.response.text.strip() or f"Private API returned HTTP {exc.response.status_code}"
        st.error(str(detail))
    except httpx.HTTPError as exc:
        st.error(f"Private API unavailable: {exc}")
    return None


st.markdown('<div class="eyebrow">Restricted single-assessor pilot</div>', unsafe_allow_html=True)
st.title("Dissertation Review Automation System")
st.markdown('<div class="pilot">AI suggestions are decision support only. DRAS has not been validated as a production examiner; official exports require direct assessor approval.</div>', unsafe_allow_html=True)

assessments = request("GET", "/v1/assessments", headers=headers()) or []
label_map = {f"{item['metadata'].get('candidate_name') or 'Untitled'} · {item['state']} · v{item['version']}": item["id"] for item in assessments}

with st.sidebar:
    st.caption(f"Signed in as {email}")
    mode = st.radio("Workspace", ["Assessment history", "New assessment", "Review workspace"])

if mode == "New assessment":
    st.header("Start an assessment")
    st.write("Upload the dissertation first. DRAS will extract title-page details for you to verify before the assessment is created.")
    source = st.file_uploader(
        "Dissertation file",
        type=["pdf", "docx", "doc"],
        help="Upload one digital PDF, DOCX, or legacy Word DOC, up to 100 MB.",
        key="new_assessment_source",
    )
    if source:
        source_bytes = source.getvalue()
        source_fingerprint = hashlib.sha256(source_bytes).hexdigest()
        if st.session_state.get("intake_source_fingerprint") != source_fingerprint:
            st.session_state["intake_source_fingerprint"] = source_fingerprint
            st.session_state.pop("intake_metadata", None)
            st.session_state.pop("intake_metadata_attempted", None)
        st.caption(f"{source.name} · {len(source_bytes) / (1024 * 1024):.1f} MB")
        if st.session_state.get("intake_metadata_attempted") != source_fingerprint:
            st.session_state["intake_metadata_attempted"] = source_fingerprint
            with st.spinner("Reading the title page…"):
                extracted = request(
                    "POST",
                    "/v1/metadata/extract",
                    headers=headers(),
                    files={"source": (source.name, source_bytes, source.type)},
                )
            if extracted:
                st.session_state["intake_metadata"] = extracted
                st.success("Details extracted. Review and correct them before continuing.")
        elif not st.session_state.get("intake_metadata"):
            if st.button("Retry metadata extraction", icon=":material/refresh:"):
                st.session_state.pop("intake_metadata_attempted", None)
                st.rerun()

    extracted = st.session_state.get("intake_metadata")
    if extracted:
        for warning in extracted.get("warnings", []):
            st.warning(warning)
        values = extracted.get("metadata", {})
        confidence = extracted.get("confidence", {})
        st.subheader("Confirm dissertation details")
        st.caption("These values came from the document. You remain responsible for confirming their accuracy.")
        with st.form("new"):
            col1, col2 = st.columns(2)
            candidate = col1.text_input(
                "Candidate name",
                value=values.get("candidate_name") or "",
                help=f"Extraction confidence: {confidence.get('candidate_name', 0):.0%}",
            )
            registration = col2.text_input(
                "Registration number",
                value=values.get("registration_number") or "",
                help=f"Extraction confidence: {confidence.get('registration_number', 0):.0%}",
            )
            supervisor = col1.text_input(
                "Supervisor name",
                value=values.get("supervisor_name") or "",
                help=f"Extraction confidence: {confidence.get('supervisor_name', 0):.0%}",
            )
            assessor = col2.text_input("Assessor name")
            title = st.text_area(
                "Dissertation title",
                value=values.get("dissertation_title") or "",
                help=f"Extraction confidence: {confidence.get('dissertation_title', 0):.0%}",
            )
            consent = st.checkbox("I confirm institutional authorization for external AI processing of this dissertation.")
            submitted = st.form_submit_button(
                "Create assessment",
                type="primary",
                icon=":material/add_notes:",
            )
        if submitted and source:
            created = request("POST", "/v1/assessments", headers=headers(True), json={"metadata": {"candidate_name": candidate or None, "registration_number": registration or None, "dissertation_title": title or None, "supervisor_name": supervisor or None, "assessor_name": assessor or None, "assessor_email": email}, "external_processing_authorized": consent})
            if created:
                uploaded = request("POST", f"/v1/assessments/{created['id']}/source", headers=headers(True, created["version"]), files={"source": (source.name, source_bytes, source.type)})
                if uploaded:
                    st.success("Assessment created and source stored privately. Continue in the review workspace to extract the full dissertation.")
                    st.session_state["assessment_id"] = created["id"]
                    st.session_state.pop("intake_metadata", None)
                    st.session_state.pop("intake_source_fingerprint", None)
                    st.session_state.pop("intake_metadata_attempted", None)

elif mode == "Assessment history":
    st.header("Assessment history")
    if not assessments:
        st.info("No assessments yet.")
    for item in assessments:
        with st.container(border=True):
            col1, col2, col3 = st.columns([3, 2, 1])
            col1.subheader(item["metadata"].get("candidate_name") or "Untitled assessment")
            col1.caption(item["metadata"].get("dissertation_title") or "Title not supplied")
            col2.metric("Status", item["state"].replace("_", " ").title())
            if col3.button("Open", key=f"open-{item['id']}"):
                st.session_state["assessment_id"] = item["id"]
                st.info("Select Review workspace in the sidebar.")

else:
    if label_map:
        selected_label = st.selectbox("Assessment", list(label_map), index=0)
        assessment_id = st.session_state.get("assessment_id", label_map[selected_label])
    else:
        st.info("Create an assessment first.")
        st.stop()
    detail = request("GET", f"/v1/assessments/{assessment_id}", headers=headers())
    if not detail:
        st.stop()
    processing_config = request("GET", "/v1/config/processing", headers=headers()) or {}
    st.subheader(detail["metadata"].get("candidate_name") or "Untitled assessment")
    st.caption(f"{detail['state'].replace('_', ' ').title()} · record version {detail['version']} · rubric {detail['rubric_version']}")
    action1, action2, action3 = st.columns(3)
    if action1.button("Extract source", disabled=detail["state"] not in ["uploaded", "failed"]):
        if request("POST", f"/v1/assessments/{assessment_id}/extract", headers=headers(True), json={"expected_version": detail["version"], "data": {}}):
            st.rerun()
    if action2.button("Prepare review", disabled=detail["state"] not in ["extracted", "awaiting_approval"]):
        if request("POST", f"/v1/assessments/{assessment_id}/review", headers=headers(True), json={"expected_version": detail["version"], "data": {}}):
            st.rerun()
    if action3.button("Run final validation"):
        if request("POST", f"/v1/assessments/{assessment_id}/validate", headers=headers(True), json={"expected_version": detail["version"], "data": {}}):
            st.rerun()

    pages = (detail.get("dissertation") or {}).get("pages", [])
    warnings = (detail.get("dissertation") or {}).get("warnings", [])
    source_name = detail.get("source_filename") or "dissertation"
    source_bytes = binary_request(f"/v1/assessments/{assessment_id}/source")
    rendered_pdf = (
        binary_request(f"/v1/assessments/{assessment_id}/source/rendered")
        if detail.get("rendered_source_available")
        else None
    )
    document_pane, controls_pane = st.columns([1.25, 1], gap="large")

    with document_pane:
        st.subheader("Dissertation")
        st.caption(source_name)
        if rendered_pdf:
            encoded_pdf = base64.b64encode(rendered_pdf).decode("ascii")
            st.iframe(
                f"data:application/pdf;base64,{encoded_pdf}",
                height=1050,
                alt="Uploaded dissertation PDF",
            )
        elif source_bytes:
            st.info(
                "Convert this Word document to PDF to enable page-faithful viewing and citations."
            )
            st.caption(
                "This uses Microsoft Word's native PDF export. Word may open briefly, and macOS "
                "may ask for Automation permission on the first conversion."
            )
            if st.button(
                "Convert to PDF",
                type="primary",
                icon=":material/picture_as_pdf:",
                width="stretch",
            ):
                with st.spinner("Converting the document and rebuilding page references…"):
                    converted = request(
                        "POST",
                        f"/v1/assessments/{assessment_id}/source/render",
                        headers=headers(True),
                        json={"expected_version": detail["version"], "data": {}},
                    )
                if converted:
                    st.rerun()
            st.download_button(
                "Download original document",
                source_bytes,
                file_name=source_name,
                icon=":material/download:",
                width="stretch",
            )
            if pages:
                st.text_area(
                    "Full extracted document text",
                    pages[0]["text"],
                    height=900,
                    disabled=True,
                    key=f"document-text-{assessment_id}",
                )
        else:
            st.info("Upload and extract a source document to display it here.")

    with controls_pane.expander(
        "External AI processing",
        icon=":material/security:",
        expanded=not detail.get("external_processing_authorized", False),
    ):
        if processing_config.get("openai_configured"):
            st.success(
                f"Server API key configured · model {processing_config.get('review_model')} · "
                "response storage disabled"
            )
        else:
            st.error(
                "No server API key is configured. Add DRAS_OPENAI_API_KEY to .env and restart "
                "the API before authorizing processing."
            )
        with st.form("external-processing-authorization"):
            authorize_processing = st.checkbox(
                "I confirm institutional authorization to send the minimum required "
                "dissertation text to OpenAI for this assessment.",
                value=detail.get("external_processing_authorized", False),
            )
            save_processing = st.form_submit_button("Save processing authorization")
        if save_processing:
            updated = request(
                "PATCH",
                f"/v1/assessments/{assessment_id}/processing",
                headers=headers(True),
                json={
                    "expected_version": detail["version"],
                    "data": {"authorized": authorize_processing},
                },
            )
            if updated:
                st.rerun()

    if warnings:
        unresolved_blocking = [
            warning
            for warning in warnings
            if warning.get("blocking") and not warning.get("resolved")
        ]
        if unresolved_blocking:
            controls_pane.warning(
                "Automated review is paused until the document has reliable page citations. "
                "Use Convert to PDF in the document pane. If you have already checked the "
                "original visually, you may instead resolve the warning below."
            )
        else:
            controls_pane.success(
                "The extraction warning was resolved by the assessor. Automated review may proceed."
            )
        with controls_pane.form("warnings"):
            warning_updates = []
            invalid_resolution = False
            for warning in warnings:
                page_label = f"Page {warning['page']}" if warning.get("page") else "Document-level warning"
                st.markdown(f"**{page_label}** — {warning['message']}")
                resolved = st.checkbox(
                    "I visually inspected the original and want to continue",
                    value=warning["resolved"],
                    key=f"resolved-{warning['code']}-{warning.get('page')}",
                )
                note = st.text_input(
                    "Resolution note (required when resolved)",
                    value=warning.get("resolution_note") or "",
                    placeholder=(
                        "Example: I opened the original in Word and confirmed the core sections "
                        "are readable."
                    ),
                    key=f"note-{warning['code']}-{warning.get('page')}",
                )
                invalid_resolution = invalid_resolution or (resolved and not note.strip())
                warning_updates.append({"code": warning["code"], "page": warning.get("page"), "resolved": resolved, "resolution_note": note.strip() or None})
            save_warnings = st.form_submit_button("Save warning resolutions")
        if save_warnings:
            if invalid_resolution:
                controls_pane.error("Add a resolution note for every warning marked as resolved.")
            elif request("PATCH", f"/v1/assessments/{assessment_id}/warnings", headers=headers(True), json={"expected_version": detail["version"], "data": {"warnings": warning_updates}}):
                    st.rerun()

    tabs = controls_pane.tabs(["Sections", "Checklist", "Scoring", "Validation", "Artifacts"])
    with tabs[0]:
        st.markdown("#### Section review")
        for review in detail.get("reviews", []):
            with st.expander(review["section"].replace("_", " ").title()):
                comment = st.text_area("Approved comment", review.get("assessor_comment") or review.get("proposed_comment") or "", key=f"comment-{review['section']}")
                status = st.selectbox("Decision", ["pending", "approved", "rejected"], index=["pending", "approved", "rejected"].index(review["approval_status"]), key=f"decision-{review['section']}")
                if st.button("Save section", key=f"save-{review['section']}"):
                    updated = request("PATCH", f"/v1/assessments/{assessment_id}/sections/{review['section']}", headers=headers(True), json={"expected_version": detail["version"], "data": {"assessor_comment": comment, "approval_status": status}})
                    if updated:
                        st.rerun()
    with tabs[1]:
        with st.form("checklist"):
            item_updates = []
            invalid_checklist = False
            for item in detail["checklist"]:
                st.markdown(f"**{item['number']}. {item['question']}**")
                proposal = item["proposed_answer"] if item.get("justification") else "Pending automated review"
                prefix = "Human attestation required · " if item["human_attestation_required"] else ""
                st.caption(f"{prefix}System proposal: {proposal}")
                options = ["Pending", "Yes", "No", "Cannot answer"]
                current = item.get("approved_answer") or "Pending"
                answer = st.selectbox("Assessor response", options, index=options.index(current), key=f"answer-{item['number']}")
                note = st.text_input("Assessor note", value=item.get("assessor_note") or "", key=f"check-note-{item['number']}")
                approved = st.checkbox("Approve response", value=item["approved"], key=f"check-approved-{item['number']}")
                invalid_checklist = invalid_checklist or (approved and answer == "Pending")
                item_updates.append({"number": item["number"], "approved_answer": None if answer == "Pending" else answer, "assessor_note": note, "approved": approved})
            save_checklist = st.form_submit_button("Save checklist")
        if save_checklist:
            if invalid_checklist:
                st.error("A pending checklist response cannot be approved.")
            elif request("PATCH", f"/v1/assessments/{assessment_id}/checklist", headers=headers(True), json={"expected_version": detail["version"], "data": {"items": item_updates}}):
                    st.rerun()
    with tabs[2]:
        st.warning("Confidential — never shown in the student-facing report.")
        with st.form("scores"):
            score_updates = []
            invalid_score = False
            for score in detail["scores"]:
                left_score, right_score = st.columns([1, 3])
                approved_score = left_score.number_input(f"{score['criterion']} / {score['maximum']}", 0, score["maximum"], score.get("approved"), key=f"score-{score['criterion']}")
                justification = right_score.text_input("Justification", value=score.get("justification") or "", key=f"score-note-{score['criterion']}")
                approved = st.checkbox("Approve score", value=score["status"] == "approved", key=f"score-approved-{score['criterion']}")
                invalid_score = invalid_score or (approved and approved_score is None)
                score_updates.append({"criterion": score["criterion"], "approved": approved_score, "justification": justification, "status": "approved" if approved else "pending"})
            save_scores = st.form_submit_button("Save confidential scores")
        if save_scores:
            if invalid_score:
                st.error("Enter a score before approving it.")
            elif request("PATCH", f"/v1/assessments/{assessment_id}/scores", headers=headers(True), json={"expected_version": detail["version"], "data": {"scores": score_updates}}):
                    st.rerun()
    with tabs[3]:
        with st.form("final-decisions"):
            decisions = detail.get("decisions", {})
            publishability = st.selectbox("Is this work publishable?", ["Pending", "Yes", "No"], index=0 if decisions.get("publishable") is None else 1 if decisions.get("publishable") else 2)
            publishability_approved = st.checkbox("Approve publishability decision", value=decisions.get("publishability_approved", False))
            award_confirmed = st.checkbox("I directly confirm the award-adequacy judgment recorded in checklist item 13", value=decisions.get("award_adequacy_confirmed", False))
            general_comments = st.text_area("General comments", value=decisions.get("general_comments", ""))
            if st.form_submit_button("Save final decisions"):
                value = None if publishability == "Pending" else publishability == "Yes"
                if request("PATCH", f"/v1/assessments/{assessment_id}/decisions", headers=headers(True), json={"expected_version": detail["version"], "data": {"publishable": value, "publishability_approved": publishability_approved, "award_adequacy_confirmed": award_confirmed, "general_comments": general_comments}}):
                    st.rerun()
        validation = detail.get("validation")
        if validation:
            st.success("Ready to finalize" if validation["valid"] else "Validation found blocking items")
            st.dataframe(validation["issues"], width="stretch")
        else:
            st.info("Validation has not run.")
        if st.button("Finalize and generate artifacts", disabled=not validation or not validation["valid"]):
            if request("POST", f"/v1/assessments/{assessment_id}/finalize", headers=headers(True), json={"expected_version": detail["version"], "data": {}}):
                st.rerun()
    with tabs[4]:
        artifacts = request("GET", f"/v1/assessments/{assessment_id}/artifacts", headers=headers()) or []
        for artifact in artifacts:
            data = httpx.get(artifact["url"], timeout=120).content if artifact.get("url") else httpx.get(f"{API}/v1/assessments/{assessment_id}/artifacts/{artifact['name']}", headers=headers()).content
            st.download_button(artifact["name"], data, file_name=artifact["name"], key=f"download-{artifact['name']}")

