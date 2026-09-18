from datetime import date

SYSTEM_PROMPT = """\
You extract structured meeting records for a consulting team from raw call/workshop
transcripts. Only use information present in the transcript — never invent names, dates,
or facts. If an action item has no clearly named owner, set its owner to "unassigned"
rather than guessing. Respond with the structured object only.
"""


def build_extraction_prompt(
    *,
    client_name: str,
    meeting_title: str,
    meeting_date: date | None,
    transcript_text: str,
) -> str:
    meeting_date_str = meeting_date.isoformat() if meeting_date else "unknown"
    return (
        f"Client: {client_name}\n"
        f"Meeting: {meeting_title}\n"
        f"Date: {meeting_date_str}\n\n"
        "Transcript:\n"
        "-----BEGIN TRANSCRIPT-----\n"
        f"{transcript_text}\n"
        "-----END TRANSCRIPT-----\n\n"
        "Extract the executive summary, key decisions, action items (with owner and, if "
        "mentioned, a due date), and risks/open issues from this transcript."
    )
