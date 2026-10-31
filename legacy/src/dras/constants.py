from dras.schemas import ChecklistResponse, Score

CHECKLIST_QUESTIONS = (
    "Does the Topic correctly describe the project as carried out?",
    "Was the Table of Content adequate?",
    "Was the Certification Page signed by supervisor?",
    "Is the Abstract a true summary of the work and is it structured?",
    "Did you carefully read the Introduction?",
    "Did you carefully read the the Methods?",
    "Do you consider the Results presented in the study as credible?",
    "Were Results repeated under Discussion?",
    "Was the Conclusion based on the study objectives?",
    "Was the Harvard referencing style adopted?",
    "Was evidence of Ethical approval attached?",
    "Do you consider the work as original?",
    "Do you consider this Dissertation as adequate for the award of FPCPharm?",
)

ATTESTATION_ITEMS = {3, 5, 6, 12, 13}

SCORE_MAXIMA = {
    "Literature Review": 10,
    "Study Objectives": 5,
    "Methods": 10,
    "Results": 10,
    "Discussion": 10,
    "Conclusion": 5,
    "References": 5,
    "Originality": 5,
}


def initial_checklist() -> list[ChecklistResponse]:
    return [
        ChecklistResponse(
            number=index,
            question=question,
            human_attestation_required=index in ATTESTATION_ITEMS,
        )
        for index, question in enumerate(CHECKLIST_QUESTIONS, start=1)
    ]


def initial_scores() -> list[Score]:
    return [Score(criterion=name, maximum=maximum) for name, maximum in SCORE_MAXIMA.items()]
