from __future__ import annotations

from collections import defaultdict
from math import inf
from typing import Any, Dict, List
import re

from markupsafe import Markup
from sqlalchemy.orm import joinedload, selectinload

from ..app import db
from ..models import PreworkAssignment, PreworkTemplate, Session
from ..shared.html import sanitize_html


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if "\n" not in normalized:
        return normalized
    parts = [part.strip() for part in normalized.split("\n") if part.strip()]
    return " ".join(parts) if parts else normalized.replace("\n", " ")


def _sanitize_question_text(value: str | None) -> str:
    if not value:
        return ""
    return sanitize_html(value).strip()


def _first_line_from_html(value: str | None) -> str:
    if not value:
        return ""

    normalized = str(value)
    marker = "__CBS_BREAK__"
    normalized = re.sub(r"(?i)<br\s*/?>", marker, normalized)
    normalized = re.sub(r"(?i)</(p|li|h3|h4|blockquote)>", marker, normalized)

    text = Markup(normalized).striptags()
    if not text:
        return ""

    text = text.replace(marker, "\n")
    text = text.replace("\xa0", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    for part in text.split("\n"):
        cleaned = part.strip()
        if cleaned:
            return cleaned
    return ""


def _derive_question_headline(
    headline_value: str | None, question_html: str | None
) -> str:
    headline = _first_line_from_html(headline_value)
    if headline:
        return headline

    headline = _first_line_from_html(question_html)
    if headline:
        return headline

    return ""


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
        index_to_headline: Dict[int, str] = {}

        for order, question in enumerate(snapshot):
            idx = question.get("index")
            if idx is None:
                continue
            text = _sanitize_question_text(question.get("text"))
            index_to_text[idx] = text
            index_to_order[idx] = order
            headline_value = question.get("headline") or question.get("title")
            index_to_headline[idx] = _derive_question_headline(headline_value, text)

        template_questions = []
        if assignment.template and assignment.template.questions:
            template_questions = sorted(
                assignment.template.questions, key=lambda q: q.position
            )
            if not index_to_text:
                for order, question in enumerate(template_questions):
                    idx = order + 1
                    text = _sanitize_question_text(question.text)
                    index_to_text[idx] = text
                    index_to_order.setdefault(idx, order)
                    headline_attr = getattr(question, "headline", None) or getattr(
                        question, "title", None
                    )
                    index_to_headline[idx] = _derive_question_headline(
                        headline_attr, text
                    )

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

            question_html = index_to_text.get(question_index, "")
            if not question_html and template_questions and 0 <= question_index - 1 < len(
                template_questions
            ):
                question_html = _sanitize_question_text(
                    template_questions[question_index - 1].text
                )

            question_headline = index_to_headline.get(question_index) or _derive_question_headline(
                None, question_html
            )
            if not question_headline:
                question_headline = "(Untitled question)"

            question_text = question_html or f"Question {question_index}"

            order = index_to_order.get(question_index)
            entry = grouped.setdefault(
                question_text,
                {
                    "order": order,
                    "responses": [],
                    "headline": question_headline,
                },
            )
            if order is not None:
                existing_order = entry.get("order")
                if existing_order is None or order < existing_order:
                    entry["order"] = order

            if not entry.get("headline") and question_headline:
                entry["headline"] = question_headline

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
        ordered_results.append(
            {
                "question": Markup(question_text),
                "question_headline": grouped[question_text].get("headline")
                or "(Untitled question)",
                "responses": responses,
            }
        )

    return ordered_results

