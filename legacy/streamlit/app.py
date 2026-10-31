import streamlit as st

from grader import CHECKLIST, SCORE_MAXIMA, STUDENT_SECTIONS, ChecklistAnswer, CriterionScore, Review, SectionComment, grade
from reports import confidential_report, main_report
from viewer import show

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
ANSWERS = ["Yes", "No", "Cannot answer"]
PUBLISHABLE = ["Yes", "No", "Cannot assess"]
PANEL_HEIGHT = 700

st.set_page_config(page_title="Dissertation Grader", page_icon="📄", layout="wide")
ss = st.session_state


def locate(quote: str) -> None:
    ss.locate = quote


def evidence_button(quote: str, key: str) -> None:
    st.button("📍 Show in document", key=key, on_click=locate, args=(quote,), disabled=not quote,
              help=quote or "The model gave no supporting passage for this item.")


# ---- upload ------------------------------------------------------------------

top = st.columns([3, 1], vertical_alignment="bottom")
upload = top[0].file_uploader("Dissertation", type=["pdf", "docx", "doc"])
if upload and top[1].button("Grade it", type="primary", use_container_width=True):
    try:
        with st.spinner("Reading and grading — this can take a few minutes…"):
            review = grade(upload.name, upload.getvalue())
        ss.update(review=review, file=(upload.name, upload.getvalue()), locate="", confirmed=None,
                  gid=ss.get("gid", 0) + 1)  # new widget keys, so edits from a previous file never leak in
    except Exception as exc:
        st.error(str(exc))

review: Review | None = ss.get("review")
if not review:
    st.stop()

g = ss.gid
name, data = ss.file
stem = name.rsplit(".", 1)[0]
left, right = st.columns(2, gap="medium")
# keep the document in view while the feedback scrolls
st.markdown(
    "<style>[data-testid='stColumn']:has(#doc-panel){position:sticky;top:3.5rem;align-self:flex-start}</style>",
    unsafe_allow_html=True,
)

# ---- left: the document ------------------------------------------------------

with left:
    st.markdown("<span id='doc-panel'></span>", unsafe_allow_html=True)
    st.subheader("Dissertation")
    show(name, data, ss.get("locate", ""), height=PANEL_HEIGHT)

# ---- right: editable feedback ------------------------------------------------

with right:
    st.subheader("Feedback")
    action_bar = st.container()  # filled after the edits are collected, but shown above them

    with st.container():
        st.markdown("##### Candidate")
        meta = {
            "candidate_name": st.text_input("Name of candidate", review.candidate_name, key=f"name{g}"),
            "registration_number": st.text_input("Registration number", review.registration_number, key=f"reg{g}"),
            "title": st.text_input("Title of dissertation", review.title, key=f"title{g}"),
            "supervisor": st.text_input("Supervisor", review.supervisor, key=f"sup{g}"),
        }

        st.markdown("##### Student-facing comments")
        given = {c.section.strip().lower(): c for c in review.section_comments}
        sections = []
        for i, section in enumerate(STUDENT_SECTIONS):
            old = given.get(section.lower())
            text = st.text_area(section, old.comment if old else "", key=f"sec{i}-{g}")
            quote = old.quote if old else ""
            evidence_button(quote, f"secq{i}-{g}")
            sections.append(SectionComment(section=section, comment=text, quote=quote))
        publishable = st.radio("Publishable?", PUBLISHABLE, PUBLISHABLE.index(review.publishable),
                               horizontal=True, key=f"pub{g}")
        general = st.text_area("General comments on the work", review.general_comments, key=f"gen{g}")

        st.markdown("##### Checklist (confidential)")
        answers = {c.number: c for c in review.checklist}
        checklist = []
        for i, question in enumerate(CHECKLIST, 1):
            old = answers.get(i)
            st.markdown(f"**{i}. {question}**")
            answer = st.radio("Response", ANSWERS, ANSWERS.index(old.answer) if old else 2, horizontal=True,
                              key=f"ans{i}-{g}", label_visibility="collapsed")
            comment = st.text_input("Comment", old.comment if old else "", key=f"cmt{i}-{g}")
            quote = old.quote if old else ""
            evidence_button(quote, f"ansq{i}-{g}")
            checklist.append(ChecklistAnswer(number=i, answer=answer, comment=comment, quote=quote))

        st.markdown("##### Scores (confidential)")
        old_scores = {s.criterion: s for s in review.scores}
        scores = []
        for i, (criterion, maximum) in enumerate(SCORE_MAXIMA.items()):
            old = old_scores.get(criterion)
            score = st.number_input(f"{criterion} (max {maximum})", 0, maximum, min(old.score, maximum) if old else 0,
                                    key=f"score{i}-{g}")
            why = st.text_area("Justification", old.justification if old else "", key=f"why{i}-{g}")
            quote = old.quote if old else ""
            evidence_button(quote, f"scoreq{i}-{g}")
            scores.append(CriterionScore(criterion=criterion, score=score, justification=why, quote=quote))

    final = Review(**meta, checklist=checklist, section_comments=sections, publishable=publishable,
                   general_comments=general, scores=scores)

# ---- confirm, then download --------------------------------------------------

with action_bar:
    signature = final.model_dump_json()
    total = sum(s.score for s in final.scores)
    if st.button("✓ Confirm — I have reviewed this", type="primary", use_container_width=True):
        ss.confirmed = signature
    if ss.get("confirmed") == signature:
        st.success(f"Confirmed. Total score {total} / 60.")
        a, b = st.columns(2)
        a.download_button("⬇ Assessment report", main_report(final), f"{stem} - Detailed Assessment Report.docx",
                          DOCX, use_container_width=True)
        b.download_button("⬇ Confidential scoring", confidential_report(final),
                          f"{stem} - CONFIDENTIAL scoring.docx", DOCX, use_container_width=True)
    else:
        st.caption(f"Total score {total} / 60 · Edit anything, then confirm to unlock the downloads."
                   + (" You have edited since confirming." if ss.get("confirmed") else ""))
