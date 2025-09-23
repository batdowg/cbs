from __future__ import annotations

from collections import defaultdict
from math import inf
from typing import Any, Dict, List

from sqlalchemy.orm import joinedload, selectinload

from ..app import db
from ..models import PreworkAssignment, PreworkTemplate, Session


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if "\n" not in normalized:
        return normalized
    parts = [part.strip() for part in normalized.split("\n") if part.strip()]
    return " ".join(parts) if parts else normalized.replace("\n", " ")


def get_session_prework_summary(
    session_id: int, *, session_language: str | None = None
) -> List[Dict[str, Any]]:
    target_language = session_language
    if not target_language:
        target_language = (
            db.session.query(Session.workshop_language)
            .filter(Session.id == session_id)
            .scalar()
        ) or "en"

    assignments = (
        db.session.query(PreworkAssignment)
        .options(
            joinedload(PreworkAssignment.participant_account),
            selectinload(PreworkAssignment.answers),
            joinedload(PreworkAssignment.template).selectinload(PreworkTemplate.questions),
        )
        .filter(PreworkAssignment.session_id == session_id)
        .all()
    )

    grouped: Dict[str, Dict[str, Any]] = {}

    for assignment in assignments:
        template_language = (
            assignment.template.language if assignment.template else None
        )
        if template_language and template_language != target_language:
            continue

        account = assignment.participant_account
        if not account:
            continue

        name = _clean_text(account.full_name or account.email or "")
        if not name:
            continue

        snapshot = (assignment.snapshot_json or {}).get("questions") or []
        index_to_text: Dict[int, str] = {}
        index_to_order: Dict[int, int] = {}

        for order, question in enumerate(snapshot):
            idx = question.get("index")
            if idx is None:
                continue
            text = _clean_text(question.get("text"))
            index_to_text[idx] = text
            index_to_order[idx] = order

        template_questions = []
        if assignment.template and assignment.template.questions:
            template_questions = sorted(
                assignment.template.questions, key=lambda q: q.position
            )
            if not index_to_text:
                for order, question in enumerate(template_questions):
                    idx = order + 1
                    index_to_text[idx] = _clean_text(question.text)
                    index_to_order.setdefault(idx, order)

        answers_by_question: Dict[int, list[tuple[int, str]]] = defaultdict(list)
        for answer in assignment.answers:
            cleaned_answer = _clean_text(answer.answer_text)
            if not cleaned_answer:
                continue
            answers_by_question[answer.question_index].append(
                (answer.item_index or 0, cleaned_answer)
            )

        if not answers_by_question:
            continue

        for question_index, parts in answers_by_question.items():
            parts.sort(key=lambda item: item[0])
            answers = [text for _, text in parts if text]
            if not answers:
                continue

            question_text = index_to_text.get(question_index, "")
            if not question_text and template_questions and 0 <= question_index - 1 < len(
                template_questions
            ):
                question_text = _clean_text(template_questions[question_index - 1].text)
            if not question_text:
                question_text = f"Question {question_index}"

            order = index_to_order.get(question_index)
            entry = grouped.setdefault(
                question_text, {"order": order, "responses": []}
            )
            if order is not None:
                existing_order = entry.get("order")
                if existing_order is None or order < existing_order:
                    entry["order"] = order

            entry["responses"].append(
                {"name": name, "answer_text": "; ".join(answers)}
            )

    ordered_results: List[Dict[str, Any]] = []
    for question_text, data in sorted(
        grouped.items(),
        key=lambda item: (
            item[1].get("order") if item[1].get("order") is not None else inf,
            item[0].lower(),
        ),
    ):
        responses = data.get("responses") or []
        if not responses:
            continue
        responses.sort(key=lambda r: (r.get("name") or "").lower())
        ordered_results.append({"question": question_text, "responses": responses})

    return ordered_results

