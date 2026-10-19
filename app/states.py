from fastapi import HTTPException

RFQ_TRANSITIONS = {
    "open": {"quoted", "closed"},
    "quoted": {"awarded", "closed"},
    "awarded": set(),
    "closed": set(),
}
QUOTE_TRANSITIONS = {
    "submitted": {"accepted", "rejected"},
    "accepted": set(),
    "rejected": set(),
}


def transition(kind: str, table: dict[str, set[str]], current: str, target: str) -> str:
    """Return target if current -> target is allowed, else raise HTTP 409."""
    if target not in table.get(current, set()):
        raise HTTPException(409, f"invalid {kind} transition: {current} -> {target}")
    return target
