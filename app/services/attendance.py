from __future__ import annotations

from ..app import db
from ..models import ParticipantAttendance, Session, SessionParticipant


class AttendanceValidationError(ValueError):
    """Raised when attendance parameters fail validation."""


class AttendanceForbiddenError(PermissionError):
    """Raised when attendance changes are not allowed for the session."""


def _ensure_session_allows_attendance(session: Session) -> None:
    if session.delivery_type == "Material only":
        raise AttendanceForbiddenError(
            "Material only sessions do not track attendance."
        )


def _validate_day_index(session: Session, day_index: int) -> None:
    days = session.number_of_class_days or 0
    if day_index < 1 or day_index > days:
        raise AttendanceValidationError(
            "day_index must be between 1 and number_of_class_days."
        )


def _ensure_participant(session: Session, participant_id: int) -> None:
    exists = (
        db.session.query(SessionParticipant.id)
        .filter(
            SessionParticipant.session_id == session.id,
            SessionParticipant.participant_id == participant_id,
        )
        .scalar()
    )
    if not exists:
        raise AttendanceValidationError("Participant is not part of this session.")


def upsert_attendance(
    session: Session, participant_id: int, day_index: int, attended: bool
) -> ParticipantAttendance:
    """Create or update a single attendance record for the given participant."""

    _ensure_session_allows_attendance(session)
    _validate_day_index(session, day_index)
    _ensure_participant(session, participant_id)

    attended_value = bool(attended)
    record = (
        ParticipantAttendance.query.filter_by(
            session_id=session.id,
            participant_id=participant_id,
            day_index=day_index,
        )
        .one_or_none()
    )
    if record:
        record.attended = attended_value
    else:
        record = ParticipantAttendance(
            session_id=session.id,
            participant_id=participant_id,
            day_index=day_index,
            attended=attended_value,
        )
        db.session.add(record)
    return record


def mark_all_attended(session: Session) -> int:
    """Mark every participant/day combination in the session as attended."""

    _ensure_session_allows_attendance(session)
    days = session.number_of_class_days or 0
    if days <= 0:
        return 0

    participant_ids = [
        row.participant_id
        for row in SessionParticipant.query.with_entities(
            SessionParticipant.participant_id
        ).filter_by(session_id=session.id)
    ]
    if not participant_ids:
        return 0

    existing_records = (
        ParticipantAttendance.query.filter(
            ParticipantAttendance.session_id == session.id,
            ParticipantAttendance.participant_id.in_(participant_ids),
        ).all()
    )
    existing_map = {
        (record.participant_id, record.day_index): record
        for record in existing_records
    }

    total_rows = len(participant_ids) * days
    for participant_id in participant_ids:
        for day_index in range(1, days + 1):
            record = existing_map.get((participant_id, day_index))
            if record:
                record.attended = True
            else:
                record = ParticipantAttendance(
                    session_id=session.id,
                    participant_id=participant_id,
                    day_index=day_index,
                    attended=True,
                )
                db.session.add(record)
                existing_map[(participant_id, day_index)] = record
    return total_rows
