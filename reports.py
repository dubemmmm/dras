"""Two Word documents laid out like WAPCP's Detailed_Assessment_report template.

main_report():         the Checklist page, then the "Detailed Assessment Report" for the student.
confidential_report(): the confidential Scoring page only.
Signatures, assessor name/contact and dates are left as dotted lines for a human.
"""

from io import BytesIO

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from pydantic import BaseModel

from grader import CHECKLIST, SCORE_MAXIMA, Review

FONT = "Times New Roman"
DOTS = "…………………………………………………………………………………"
LINE = "…" * 80
CENTER, JUSTIFY = WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.JUSTIFY

# (label in template, bold prompt, italic guidance) per detailed-report section
SECTIONS = [
    ("Abstract", "Comments on the Abstract", "Abstract",
     "Note: Abstract should not be more than one page. The abstract represents a concise but holistic overview of the entire project, highlighting the key elements of all the various components. The abstract should be structured into: Objectives, Methods, Results, and Conclusion."),
    ("Introduction", "Comments on Introduction", "Introduction",
     "This should contain information on Background, General and Specific review of relevant literature, Rationale or Justification, General and Specific Objectives."),
    ("Methods", "Comments on the Method", "Methods",
     "This section consists of methods of data collection and methods of data analysis. Data collection sub-section should indicate: Design, Setting, Population/Sample, and Data collection instrument. Data analysis should indicate the relevant descriptive and inferential statistics that were performed and the Package or Tool that was employed."),
    ("Results", "Comments on the Results", "Results",
     "Results should first be summarized in texts (sentences) while the details are presented in Tables and Figures. Duplication of results is not permitted."),
    ("Discussion", "Comments on Discussion", "Discussion",
     "The purpose of discussion is not to rehash the results. Discussion should interpret the results, compare with other studies, and give the implications of the findings. Furthermore, discussion should the indicate direction for future research or unanswered questions, and the limitations of the study."),
    ("Conclusion", "Comments on Conclusion", "Conclusion",
     "Conclusion should be based on the objectives of the study. Recommendations, if at all necessary, should be based on the work and not the political or professional aspirations of the author."),
    ("References", "Comments on References", "References",
     "References should employ the Harvard style. Inside the text, cite author, year in parenthesis and at the end, arrange the references alphabetically."),
    ("Appendices", "Comments on Appendix", "Appendix",
     "Relevant instrument of data collection such as questionnaire or interview format and copy of letter of ethical approval should be attached."),
    ("General Presentation", "Comments on General Presentation", "General Presentation",
     "Dissertation should be divided into 5 chapters: Introduction including literature review, Methods, Results, Discussion, and Conclusion. Is the work neat, cosnistnecy in font size, editorial issues, language etc…."),
]


# children of <w:pPr> that must come after <w:shd>
_AFTER_SHD = (
    "w:tabs", "w:suppressAutoHyphens", "w:kinsoku", "w:wordWrap", "w:overflowPunct", "w:topLinePunct",
    "w:autoSpaceDE", "w:autoSpaceDN", "w:bidi", "w:adjustRightInd", "w:snapToGrid", "w:spacing", "w:ind",
    "w:contextualSpacing", "w:mirrorIndents", "w:suppressOverlap", "w:jc", "w:textDirection",
    "w:textAlignment", "w:textboxTightWrap", "w:outlineLvl", "w:divId", "w:cnfStyle", "w:rPr",
    "w:sectPr", "w:pPrChange",
)


# ---- low-level helpers -------------------------------------------------------


class Assessor(BaseModel):
    """Printed under the scoring table; the signature and date stay blank for a human."""

    name: str = "DR EBELE ONWUCHULUBA"
    email: str = "eonwuchuluba@unilag.edu.ng"
    phone: str = "08060636490"


def _font(run, size, bold=False, italic=False, color=None, name=FONT):
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    run.font.size = Pt(size)
    run.bold, run.italic = bold or None, italic or None  # omit rather than write val=0
    if color:
        run.font.color.rgb = color


def _para(container, parts, size=11, align=None, after=10, indent=None, hanging=None,
          page_break=False, shade=None, color=None):
    """parts: str, or list of str / (text, bold, italic) tuples."""
    p = container.add_paragraph()
    pf = p.paragraph_format
    pf.space_after, pf.space_before, pf.line_spacing = Pt(after), Pt(0), 1.15
    if align is not None:
        p.alignment = align
    if indent is not None:
        pf.left_indent = Pt(indent)
    if hanging is not None:
        pf.first_line_indent = Pt(-hanging)
    pf.page_break_before = page_break or None
    if shade:
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:fill"), shade)
        p._p.get_or_add_pPr().insert_element_before(shd, *_AFTER_SHD)  # keep schema order for Word
    for part in [parts] if isinstance(parts, str) else parts:
        text, bold, italic = (part, False, False) if isinstance(part, str) else part
        _font(p.add_run(text), size, bold, italic, color)
    return p


def _body(doc, label, text, placeholder=LINE):
    """'Label: text' in the template's bold-label style; multi-paragraph text flows beneath."""
    chunks = [c.strip() for c in (text or "").split("\n") if c.strip()] or [placeholder]
    _para(doc, [(f"{label}: ", True, False), chunks[0]], align=JUSTIFY)
    for chunk in chunks[1:]:
        _para(doc, chunk, align=JUSTIFY)


def _banner(doc, text, size, page_break=False):
    _para(doc, [(text, True, False)], size=size, align=CENTER, shade="000000",
          color=RGBColor(255, 255, 255), page_break=page_break)


def _field(paragraph, instruction, color=None):
    for kind, text in (("begin", None), (None, instruction), ("end", None)):
        run = paragraph.add_run()
        _font(run, 10, color=color, name="Calibri")
        if kind:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), kind)
        else:
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = text
        run._r.append(el)


def _new_doc() -> Document:
    doc = Document()
    s = doc.sections[0]
    s.page_width, s.page_height = Inches(8.5), Inches(11)
    s.left_margin = s.right_margin = Inches(1.25)
    s.top_margin = s.bottom_margin = Inches(1)
    style = doc.styles["Normal"]
    style.font.name, style.font.size = FONT, Pt(11)
    style.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    footer = s.footer.paragraphs[0]
    grey = RGBColor(0x59, 0x59, 0x59)
    _font(footer.add_run("Page "), 10, color=grey, name="Calibri")
    _field(footer, "PAGE", grey)
    _font(footer.add_run(" of "), 10, color=grey, name="Calibri")
    _field(footer, "NUMPAGES", grey)
    return doc


def _bytes(doc: Document) -> bytes:
    out = BytesIO()
    doc.save(out)
    return out.getvalue()


def _cell(cell, text="", size=11, bold=False, align=CENTER, valign=WD_CELL_VERTICAL_ALIGNMENT.CENTER):
    cell.vertical_alignment = valign
    p = cell.paragraphs[0]
    p.alignment = align
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.space_before = Pt(2)
    if text:
        _font(p.add_run(text), size, bold)


def _widths(table, inches):
    table.autofit = False
    for row in table.rows:
        for cell, w in zip(row.cells, inches):
            cell.width = Inches(w)


def _identity(doc, r: Review) -> None:
    """NAME OF CANDIDATE / REGISTRATION NUMBER / TITLE / (supervisor)."""
    for label, value in (("NAME OF CANDIDATE", r.candidate_name), ("REGISTRATION NUMBER", r.registration_number)):
        _para(doc, [(label, True, False), f": {value or LINE}"], align=JUSTIFY)
    _para(doc, [("TITLE OF DISSERTATION", True, False), f": {r.title or LINE}"], align=JUSTIFY)


# ---- the three template pages ------------------------------------------------


def _checklist_page(doc, r: Review) -> None:
    _para(doc, [("CHECKLIST FOR DISSERTATION ASSESSMENT", True, False)], size=16, align=CENTER)
    _para(doc, f"Name of Candidate: {r.candidate_name or '…………………………………'}   Reg. No: {r.registration_number or '……….…………'}", size=12)

    t = doc.add_table(rows=2, cols=6, style="Table Grid")
    t.alignment = CENTER
    for col, text in ((0, "S/N"), (1, "Item to be Assessed"), (5, "Comments")):
        _cell(t.cell(0, col).merge(t.cell(1, col)), text, 11, True)
    resp = t.cell(0, 2).merge(t.cell(0, 4))
    _cell(resp, "Response (tick as appropriate)", 10, True)
    for col, text in zip((2, 3, 4), ("Yes", "No", "Cannot answer")):
        _cell(t.cell(1, col), text, 10, True)

    answers = {c.number: c for c in r.checklist}
    for i, question in enumerate(CHECKLIST, 1):
        cells = t.add_row().cells
        a = answers.get(i)
        _cell(cells[0], str(i), 10.5)
        _cell(cells[1], question, 10.5, align=JUSTIFY)
        for col, option in zip((2, 3, 4), ("Yes", "No", "Cannot answer")):
            _cell(cells[col], "✓" if a and a.answer == option else "", 11)
        _cell(cells[5], a.comment if a else "", 10, align=WD_ALIGN_PARAGRAPH.LEFT)
    _widths(t, (0.37, 2.55, 0.41, 0.37, 0.58, 1.72))

    _para(doc, "", size=10)
    _para(doc, f"Any General Comments: {LINE}")
    _para(doc, LINE, after=4)
    _para(doc, "", size=5)
    _para(doc, f"Name of Assessor: {DOTS}  Signature: …………………….….")


def _detailed_report_page(doc, r: Review, page_break: bool) -> None:
    _para(doc, [("WEST AFRICAN POSTGRADUATE COLLEGE OF PHARMACISTS", True, False)], size=16, align=CENTER, page_break=page_break)
    _para(doc, [("ASSESSMENT OF DISSERTATION REPORT", True, False)], size=16, align=CENTER)
    _identity(doc, r)
    _para(doc, [("NAME OF DISSERTATION SUPERVISOR: ", True, False), r.supervisor or LINE], align=JUSTIFY)
    _banner(doc, "DETAILED ASSESSMENT REPORT", 12)
    _para(doc, [("(Please note that this section will be given to the student to improve the quality of the dissertation)", True, False)], align=JUSTIFY)

    comments = {c.section.strip().lower(): c.comment for c in r.section_comments}
    for key, prompt, heading, guidance in SECTIONS:
        _para(doc, [(heading, True, False), ": ", (guidance, False, True)], align=JUSTIFY, indent=13.5, hanging=13.5)
        _body(doc, prompt, comments.get(key.lower()))

    _para(doc, "", size=11)
    yes, no = (("✓", "…….…") if r.publishable == "Yes" else ("………….", "✓") if r.publishable == "No" else ("………….", "……….…."))
    _para(doc, [(f"Is this work publishable? Yes: {yes}    No {no}", True, False)], indent=18)
    _para(doc, "", size=11)
    _body(doc, "General Comments on the work", r.general_comments)


def _leader_line(doc, label, value="", bold=False, size=11, after=10, extra=None):
    """'LABEL: value' with a dotted leader running to the right margin when value is empty."""
    p = _para(doc, [(f"{label}: " if label else "", bold, False)], size=size, after=after)
    if value:
        _font(p.add_run(value), size)
    else:
        p.paragraph_format.tab_stops.add_tab_stop(Inches(6), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
        _font(p.add_run("\t"), size)
    return p


def _scoring_page(doc, r: Review, a: Assessor, page_break: bool = False) -> None:
    # black highlight sits behind the text only, as in the template
    p = _para(doc, "", align=CENTER, after=12)
    if page_break:
        p.paragraph_format.page_break_before = True
    run = p.add_run("This Page is confidential and would not be made available to the student")
    _font(run, 14, bold=True, color=RGBColor(255, 255, 255), name="Calibri")
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), "000000")
    run._r.get_or_add_rPr().append(shd)

    _leader_line(doc, "NAME OF CANDIDATE", r.candidate_name, bold=True, size=10.5)
    _leader_line(doc, "REGISTRATION NUMBER", r.registration_number, bold=True, size=10.5)
    _leader_line(doc, "TITLE OF DISSERTATION", r.title, bold=True, size=10.5)
    if not r.title:
        for _ in range(2):
            _leader_line(doc, "", size=10.5)
    p = _para(doc, "", align=CENTER, after=2)
    _font(p.add_run("SCORING OF DISSERTATION"), 12, bold=True, name="Calibri")

    scores = {s.criterion: s.score for s in r.scores}
    t = doc.add_table(rows=1, cols=4, style="Table Grid")
    t.alignment = CENTER
    for cell, text in zip(t.rows[0].cells, ("S/N", "Item", "Maximum Score", "Actual Score")):
        _cell(cell, text, 12, True)
    for i, (name, maximum) in enumerate(SCORE_MAXIMA.items(), 1):
        c = t.add_row().cells
        _cell(c[0], str(i), 12)
        _cell(c[1], name, 12, align=WD_ALIGN_PARAGRAPH.LEFT)
        _cell(c[2], str(maximum), 12)
        _cell(c[3], str(scores[name]) if name in scores else "", 12)
    c = t.add_row().cells
    _cell(c[0]), _cell(c[1], "Oral Defence", 12, align=WD_ALIGN_PARAGRAPH.LEFT), _cell(c[2], "-", 12), _cell(c[3], "-", 12)
    c = t.add_row().cells
    _cell(c[0]), _cell(c[1], "Total Score", 12, align=WD_ALIGN_PARAGRAPH.LEFT), _cell(c[2], "-", 12), _cell(c[3], str(sum(scores.values())), 12)
    for row in t.rows[1:]:
        row.height = Inches(0.36)
    _widths(t, (0.42, 3.26, 1.55, 1.13))

    _para(doc, "", size=11)
    for label, value in (("Name of Assessor", a.name), ("Email Address", a.email), ("Telephone", a.phone)):
        _leader_line(doc, label, value, size=11, after=14)
    p = _para(doc, [("Signature: ", False, False)], size=11, after=10)
    p.paragraph_format.tab_stops.add_tab_stop(Inches(3.7), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
    p.paragraph_format.tab_stops.add_tab_stop(Inches(6), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
    _font(p.add_run("\t Date: \t"), 11)


# ---- public ------------------------------------------------------------------


def main_report(r: Review) -> bytes:
    doc = _new_doc()
    _checklist_page(doc, r)
    _detailed_report_page(doc, r, page_break=True)
    return _bytes(doc)


def combined_report(r: Review, assessor: Assessor | None = None) -> bytes:
    """Assessment report followed by the confidential scoring page. For the assessor's records, not the student."""
    doc = _new_doc()
    _checklist_page(doc, r)
    _detailed_report_page(doc, r, page_break=True)
    _scoring_page(doc, r, assessor or Assessor(), page_break=True)
    return _bytes(doc)


def confidential_report(r: Review, assessor: Assessor | None = None) -> bytes:
    doc = _new_doc()
    _scoring_page(doc, r, assessor or Assessor())
    return _bytes(doc)
