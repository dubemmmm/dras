# Dissertation Review Automation System (DRAS)

## Executive Summary

DRAS is an AI-assisted application for reviewing postgraduate theses and dissertations and generating structured assessment reports. Its initial standard is the 2026 West African Postgraduate College of Pharmacists (WAPCP) Dissertation Assessment Report.

The system is intended to reduce the assessor's manual workload without replacing academic judgment. It extracts and structures a dissertation, applies institutional assessment criteria, produces evidence-backed findings and reviewer comments, proposes checklist responses and confidential scores, and populates the official assessment documents. An authorized assessor must inspect, edit, and approve the results before finalization.

## Intended Users and Workflow

The primary users are dissertation assessors, supervisors, examination committees, and authorized research reviewers.

The end-to-end workflow is:

1. The assessor uploads one PDF or DOCX dissertation and confirms available metadata, such as the candidate's name, registration number, dissertation title, supervisor, assessor, and date.
2. The system extracts the document while preserving its section hierarchy, page references, tables, figures, references, appendices, and extraction warnings.
3. Deterministic checks and AI review evaluate the dissertation section by section and across sections.
4. The system creates structured findings, evidence citations, draft reviewer comments, proposed checklist responses, and provisional scores.
5. Validation checks the completeness, consistency, evidence, score limits, confidentiality, and report formatting.
6. The assessor inspects the evidence, edits or rejects findings, adjusts responses and scores, and records approval.
7. DRAS exports separate student-facing and confidential Word/PDF reports.

Missing or ambiguous information must remain unconfirmed. The system must never invent metadata, evidence, signatures, facts, or academic judgments.

## Target Architecture

The initial implementation uses a Streamlit review dashboard connected to a FastAPI backend.

```text
Streamlit Review Dashboard
Upload -> Inspect -> Edit -> Approve -> Export
                    |
              FastAPI Backend
       Assessment orchestration and storage
                    |
       +------------+-------------+
       |                          |
Extraction Engine          Review Skill + LLM
PDF/DOCX parsing,          Academic analysis and
layout/structure checks    reviewer-comment drafting
       |                          |
Validation Engine          Report Generator
Schemas, evidence,         Word templates and
checklists, scoring        PDF export
       +------------+-------------+
                    |
             Assessor Approval
Evidence, comments, checklist, confidential scores
                    |
       +------------+-------------+
       |                          |
Assessment Report           Scoring Report
Student-facing              Confidential
```

Recommended technologies are Python, Streamlit, FastAPI, PyMuPDF, python-docx, Pydantic, JSON, SQLite, and Pytest. The language-model provider should be abstracted so it can be changed without rewriting the workflow. Scanned pages, complex layouts, and figures require a separate visual-inspection or OCR path when ordinary extraction is unreliable.

## Core Assessment Process

### Document understanding

DRAS must detect the title and preliminary pages, table of contents, chapter hierarchy, paragraphs, tables, figures, references, appendices, and relevant metadata. Section identification should combine headings, layout, and semantic classification rather than depend only on keywords. The original dissertation must remain unchanged.

The extracted content is converted into a structured dissertation model containing content, page mappings, research objectives or hypotheses, methods, reported findings, citations, appendices, and extraction warnings. This validated representation—not unrestricted model output—must drive the final reports.

### Deterministic and AI evaluation

Code should perform reliable mechanical checks wherever possible, including section presence, abstract length and headings, chapter structure, table and figure numbering, reference ordering and matching, appendix presence, score calculations, and numerical consistency. The system must distinguish an absent item from one that cannot be verified.

The LLM should perform academic interpretation: assessing coherence, methodological justification, adequacy of explanation, meaning of results, quality of discussion, and appropriateness of conclusions. Its outputs must conform to typed schemas and cite supporting evidence.

Cross-section checks must compare:

- Abstract with the complete dissertation.
- Objectives with Methods.
- Methods with Results.
- Results with Discussion.
- Objectives and findings with the Conclusion.
- In-text citations with the reference list.

## Assessment Coverage

The system evaluates:

- **Abstract:** required Objectives, Methods, Results, and Conclusion structure; one-page limit; accuracy, completeness, and consistency with the dissertation.
- **Introduction:** background, research problem, rationale, objectives, questions or hypotheses, logical organization, and relevance.
- **Methods:** design, setting, population, eligibility, sampling, sample size, instruments, validation or reliability, procedures, quality control, analysis, software, ethics, reproducibility, and alignment with the objectives.
- **Results:** objective alignment, organization, completeness, credible reporting, tables and figures, numerical and denominator consistency, statistical reporting, duplication, and unsupported interpretation.
- **Discussion:** interpretation rather than repetition, comparison with prior work, explanation of similarities and differences, implications, limitations, unanswered questions, and avoidance of claims beyond the evidence.
- **Conclusion:** alignment with objectives and results, qualified claims, concision, and evidence-based recommendations.
- **References:** Harvard author-date style, alphabetical order, formatting consistency, missing details, and citation/reference mismatches. Publication authenticity must not be claimed unless a bibliographic service verifies it.
- **Appendices:** referenced research instruments, ethics documentation, and other necessary supporting material. Document presence is distinct from authenticity or adequacy.
- **General presentation:** five-chapter organization, numbering, language, formatting, tables, figures, captions, readability, and professionalism.

The Literature Review is evaluated internally for confidential scoring but must not receive a separate student-facing detailed comment. Its internal review covers relevance, adequacy, synthesis, critical analysis, research gaps, organization, and alignment with the study.

## Evidence and Reviewer Comments

Every substantive criticism must be traceable to the dissertation. Each internal finding should record its section, criterion, description, supporting excerpt or location, page reference, significance, recommended correction, severity, verification status, and uncertainty.

Severity levels are:

- Major revision.
- Minor revision.
- Editorial correction.
- Verification required.

Unverified suspicions must never be presented as confirmed deficiencies. Student-facing comments should be specific, constructive, academically grounded, natural in tone, and clear about both the issue and the required improvement. Supported strengths may also be included.

## Checklist, Scoring, and Publishability

DRAS must prepare all 13 WAPCP checklist responses using **Yes**, **No**, or **Cannot answer**, with evidence or an explicit confirmation requirement. Questions must be interpreted individually because a “Yes” is not always favorable—for example, whether the Discussion repeats the Results.

Human confirmation is mandatory for personal attestations and high-stakes judgments, including whether the assessor personally read a section, originality, final suitability for the FPCPharm award, and the final publishability decision.

Confidential scoring uses the institutional categories below:

| Criterion | Maximum |
|---|---:|
| Literature Review | 10 |
| Study Objectives | 5 |
| Methods | 10 |
| Results | 10 |
| Discussion | 10 |
| Conclusion | 5 |
| References | 5 |
| Originality | 5 |
| **Total** | **60** |

Each proposed score requires a justification and assessor-approved scoring guide. Originality is provisional, unsupported scores remain pending, and no unofficial institutional pass threshold may be invented. The Oral Defence line stays unchanged unless an authorized workflow supplies a result.

The AI may recommend that a work is potentially publishable, publishable after substantial revisions, not presently suitable, or not assessable from available evidence. The assessor must approve the official Yes/No response. Publishability and adequacy for the academic award are separate judgments.

## Required Outputs

DRAS must preserve the official template's headings, checklist wording, and scoring structure while allowing comments to expand without truncation. It produces four outputs:

1. **Assessment Checklist:** candidate details, 13 proposed/approved responses, supporting comments, general comments, and authorized assessor information.
2. **Detailed Assessment Report:** student-facing comments on the Abstract, Introduction, Methods, Results, Discussion, Conclusion, References, Appendix, General Presentation, publishability, and the work overall. It excludes a separate Literature Review comment.
3. **Confidential Scoring Report:** candidate details, all eight proposed/approved scores, total, assessor fields, and date/signature fields. It must never be included in the student-facing file.
4. **Internal Evidence Report:** findings, evidence excerpts and pages, proposed and edited comments, score justifications, verification status, and validation results for audit purposes.

## Human Oversight, Validation, and Security

The dashboard must let the assessor review findings by section, inspect the supporting source page, edit comments, accept or reject findings, request a targeted reassessment, adjust checklist responses and scores, and approve the final assessment. AI proposals and assessor-approved decisions must remain distinguishable. DRAS must not create a signature or certify an assessment on the assessor's behalf.

Before export, validation must confirm that all required sections and checklist items were addressed; every substantive criticism has evidence; page references are valid; comments and findings agree; scores are complete and within their maximums; totals are correct; confidential content is separated; the Literature Review rule is followed; and the populated Word document contains no truncated text. Failed sections should be retried individually rather than forcing a complete reassessment.

Because dissertations may contain unpublished, personal, patient, or otherwise confidential information, DRAS requires access control, encrypted transmission, clear disclosure of external AI processing, retention and deletion controls, safe logging, and strict output separation. Institutional authorization may be required before sensitive material is sent to an external model. Dissertation content must be treated as untrusted input, and embedded instructions must never override the review rules.

## MVP and Delivery Roadmap

The MVP covers one PDF or DOCX dissertation at a time. It must extract and organize the content, apply WAPCP criteria, conduct the internal Literature Review assessment, generate evidence-backed findings and comments, complete the checklist, propose confidential scores, validate the assessment, provide an editing and approval interface, populate the official Word template, and export separate confidential and non-confidential Word/PDF files.

Implementation proceeds through six phases:

1. Document extraction, structure detection, and page mapping.
2. Reusable `academic-dissertation-reviewer` skill and evidence-backed section review.
3. Checklist, scoring, attestation, and publishability logic.
4. Reusable DOCX templates and Word/PDF report generation.
5. Streamlit evidence-review and approval dashboard.
6. Evaluation with representative dissertations and assessor feedback.

The MVP does not require custom model training, complex multi-agent infrastructure, cloud deployment, or university-system integration. Later releases may add multi-institution rubrics, revision comparison, methodology-specific reviewers, bibliographic verification, revision tracking, analytics, and institutional workflows.

## Success Standard

The project succeeds when it consistently produces a reliable, evidence-backed draft that a professional assessor can verify, improve, and approve in substantially less time. Evaluation should measure extraction and section-detection accuracy, evidence support for criticisms, checklist and score correction rates, assessor acceptance of generated comments, confidentiality failures, report-generation errors, and the reduction in assessment time.
