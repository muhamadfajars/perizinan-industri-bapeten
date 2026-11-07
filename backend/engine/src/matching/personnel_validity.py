def expiry_result(
    parsed_document,
):
    expiry = parsed_document.get(
        "expiry",
        {},
    )

    state = expiry.get("status")

    if state == "ACTIVE":
        status = "MATCH"

    elif state == "EXPIRED":
        status = "MISMATCH"

    else:
        status = "REVIEW"

    return {
        "status": status,
        "expiry_status": state,
        "expiry_date": expiry.get("expiry_date"),
        "evidence": expiry.get("evidence"),
        "reason": expiry.get("reason"),
    }


def aggregate_status(
    statuses,
):
    if "MISMATCH" in statuses:
        return "MISMATCH"

    if "REVIEW" in statuses:
        return "REVIEW"

    if "MISSING" in statuses:
        return "INCOMPLETE"

    return "VALID"
