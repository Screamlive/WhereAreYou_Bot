"""Use-cases for absence moderation flows (approve/decline/delete/edit)."""

from dataclasses import dataclass

from utils import format_date_display


@dataclass(frozen=True)
class AbsenceDecision:
    new_status: str
    admin_text: str
    user_text: str


@dataclass(frozen=True)
class DeleteDecision:
    should_delete: bool
    admin_text: str
    user_text: str
    log_text: str


def build_absence_decision(
    action: str,
    absence_id: int,
    category: str,
    start_date: str,
    end_date: str,
) -> AbsenceDecision:
    start_disp = format_date_display(start_date)
    end_disp = format_date_display(end_date)
    if action == "approve_abs":
        return AbsenceDecision(
            new_status="approved",
            admin_text=f"Заявка #{absence_id} одобрена.",
            user_text=f"Ваша заявка #{absence_id} ({category} {start_disp}–{end_disp}) одобрена!",
        )
    if action == "decline_abs":
        return AbsenceDecision(
            new_status="declined",
            admin_text=f"Заявка #{absence_id} отклонена.",
            user_text=f"Ваша заявка #{absence_id} ({category} {start_disp}–{end_disp}) отклонена.",
        )
    raise ValueError(f"Unsupported absence action: {action}")


def build_delete_decision(
    action: str,
    absence_id: int,
    category: str,
    start_date: str,
    end_date: str,
) -> DeleteDecision:
    start_disp = format_date_display(start_date)
    end_disp = format_date_display(end_date)
    if action == "approve_del":
        return DeleteDecision(
            should_delete=True,
            admin_text=f"Удаление #{absence_id} одобрено. Запись удалена.",
            user_text=f"Админ удалил вашу заявку #{absence_id}.",
            log_text=f"approve_del absence {absence_id}",
        )
    if action == "decline_del":
        return DeleteDecision(
            should_delete=False,
            admin_text=f"Удаление #{absence_id} отклонено.",
            user_text=f"Админ отклонил удаление вашей заявки #{absence_id}.",
            log_text=f"decline_del absence {absence_id}",
        )
    raise ValueError(f"Unsupported delete action: {action}")


def build_edit_request_admin_text(
    requester_fullname: str,
    absence_id: int,
    old_category: str,
    old_start_date: str,
    old_end_date: str,
    old_comment: str,
    new_category: str,
    new_start_date: str,
    new_end_date: str,
    new_comment: str,
) -> str:
    old_start_disp = format_date_display(old_start_date)
    old_end_disp = format_date_display(old_end_date)
    new_start_disp = format_date_display(new_start_date)
    new_end_disp = format_date_display(new_end_date)
    old_part = (
        "Старое:\n"
        f"Категория: {old_category}\n"
        f"Даты: {old_start_disp}–{old_end_disp}\n"
        f"Комментарий: {old_comment or '—'}\n\n"
    )
    new_part = (
        "Новое:\n"
        f"Категория: {new_category}\n"
        f"Даты: {new_start_disp}–{new_end_disp}\n"
        f"Комментарий: {new_comment or '—'}\n\n"
        "(pending)"
    )
    return (
        f"Пользователь {requester_fullname} хочет изменить заявку #{absence_id}.\n\n"
        f"{old_part}{new_part}"
    )


def build_edit_approve_admin_text(
    absence_id: int,
    old_category: str,
    old_start_date: str,
    old_end_date: str,
    old_comment: str,
    new_category: str,
    new_start_date: str,
    new_end_date: str,
    new_comment: str,
) -> str:
    old_start_disp = format_date_display(old_start_date)
    old_end_disp = format_date_display(old_end_date)
    new_start_disp = format_date_display(new_start_date)
    new_end_disp = format_date_display(new_end_date)
    old_text = (
        f"Старое:\nКатегория: {old_category}\n"
        f"Даты: {old_start_disp}–{old_end_disp}\n"
        f"Комментарий: {old_comment or '—'}"
    )
    new_text = (
        f"Новое:\nКатегория: {new_category}\n"
        f"Даты: {new_start_disp}–{new_end_disp}\n"
        f"Комментарий: {new_comment or '—'}"
    )
    return f"Изменение заявки #{absence_id} одобрено.\n\n{old_text}\n\n→ {new_text}"


def build_edit_approve_user_text(
    absence_id: int,
    new_category: str,
    new_start_date: str,
    new_end_date: str,
    new_comment: str,
) -> str:
    start_disp = format_date_display(new_start_date)
    end_disp = format_date_display(new_end_date)
    return (
        f"Ваше изменение заявки #{absence_id} одобрено!\n"
        f"Теперь: {new_category}, {start_disp}–{end_disp}, {new_comment or '—'}"
    )

