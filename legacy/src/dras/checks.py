from __future__ import annotations

import re

from dras.schemas import CheckStatus, DeterministicCheck, Dissertation, EvidenceReference, SectionType

CORE_SECTIONS = (
    SectionType.ABSTRACT,
    SectionType.INTRODUCTION,
    SectionType.METHODS,
    SectionType.RESULTS,
    SectionType.DISCUSSION,
    SectionType.CONCLUSION,
    SectionType.REFERENCES,
)


def evidence(dissertation: Dissertation, page: int, excerpt: str) -> EvidenceReference:
    source = dissertation.pages[page - 1]
    return EvidenceReference(page=page, excerpt=excerpt[:500], content_hash=source.content_hash)


def run_checks(dissertation: Dissertation) -> list[DeterministicCheck]:
    checks: list[DeterministicCheck] = []
    by_type = {section.section_type: section for section in dissertation.sections}
    for section_type in CORE_SECTIONS:
        section = by_type.get(section_type)
        checks.append(
            DeterministicCheck(
                code=f"required_section.{section_type.value}",
                status=CheckStatus.VERIFIED_PASS if section else CheckStatus.VERIFIED_FAIL,
                explanation=f"{section_type.value.replace('_', ' ').title()} heading was {'identified' if section else 'not identified; absence must be confirmed visually'}.",
                evidence=[evidence(dissertation, section.start_page, section.title)] if section else [],
            )
        )
    abstract = by_type.get(SectionType.ABSTRACT)
    if abstract:
        labels = {label for label in ("objectives", "methods", "results", "conclusion") if re.search(rf"\b{label}\b", abstract.text, re.I)}
        checks.append(DeterministicCheck(code="abstract.required_subheadings", status=CheckStatus.VERIFIED_PASS if len(labels) == 4 else CheckStatus.VERIFIED_FAIL, explanation=f"Recognized abstract labels: {', '.join(sorted(labels)) or 'none'}."))
    else:
        checks.append(DeterministicCheck(code="abstract.required_subheadings", status=CheckStatus.CANNOT_VERIFY, explanation="Abstract was not identified."))
    appendix_text = by_type.get(SectionType.APPENDICES)
    full_text = "\n".join(page.text for page in dissertation.pages)
    ethics_found = bool(re.search(r"ethical\s+(approval|clearance)|ethics\s+committee", appendix_text.text if appendix_text else "", re.I))
    checks.append(DeterministicCheck(code="appendix.ethics_presence", status=CheckStatus.VERIFIED_PASS if ethics_found else CheckStatus.VERIFIED_FAIL if appendix_text else CheckStatus.CANNOT_VERIFY, explanation="Ethics-related wording was found in the appendix." if ethics_found else "No ethics document wording was identified; this does not establish that approval is absent."))
    references = by_type.get(SectionType.REFERENCES)
    if references:
        entries = [line.strip() for line in references.text.splitlines() if re.match(r"^[A-Z][A-Za-z'’-]+", line.strip())]
        surnames = [re.split(r"[,\s]", line)[0].lower() for line in entries]
        status = CheckStatus.VERIFIED_PASS if surnames and surnames == sorted(surnames) else CheckStatus.VERIFIED_FAIL if surnames else CheckStatus.CANNOT_VERIFY
        checks.append(DeterministicCheck(code="references.alphabetical", status=status, explanation=f"Compared {len(surnames)} reference-leading surnames."))
    else:
        checks.append(DeterministicCheck(code="references.alphabetical", status=CheckStatus.CANNOT_VERIFY, explanation="Reference list was not identified."))
    five_chapters = len(re.findall(r"(?im)^\s*chapter\s+(?:one|two|three|four|five|[1-5])\b", full_text)) >= 5
    checks.append(DeterministicCheck(code="presentation.five_chapters", status=CheckStatus.VERIFIED_PASS if five_chapters else CheckStatus.CANNOT_VERIFY, explanation="Five numbered chapter headings were recognized." if five_chapters else "Five numbered chapter headings could not be verified from extracted text."))
    return checks

