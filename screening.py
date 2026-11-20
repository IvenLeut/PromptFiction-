"""Decision labels from explicit evidence; never infer unfunded from missing data."""


def screening_status(lead):
    if lead.hard_exclusions or lead.eligibility_status == "Excluded":
        return "Ausgeschlossen"
    if lead.eligibility_status == "Unknown":
        return "Fondskriterien prüfen"
    if lead.funding_status == "Unknown":
        return "Funding prüfen"
    if lead.funding_status in {"Pre-Seed", "Seed", "Later"}:
        return "Finanzierung bekannt"
    return "Kontakt prüfen"


def source_label(lead):
    return lead.discovery_source or lead.source_name or "Unknown"


def quality_score(lead):
    """Overall quality retains the existing overall-score contract."""
    return lead.overall_score


def review_status(lead, decisions):
    saved = decisions.get(lead.id)
    if lead.hard_exclusions or lead.eligibility_status == "Excluded":
        return "Excluded"
    return saved["decision"] if saved else "Pending Review"


def high_priority(lead, decisions):
    """Presentation threshold, not a new engine score or automatic decision."""
    if review_status(lead, decisions) in {"Excluded", "Reject"}:
        return False
    return (lead.eligibility_status == "Eligible"
            and lead.overall_score is not None and lead.overall_score >= 75
            and lead.fund_fit_score is not None and lead.fund_fit_score >= 70
            and lead.earliness_score is not None and lead.earliness_score >= 70)


def filter_leads(leads, decisions, *, search="", locations=(), industries=(), stages=(),
                 fit="Alle", statuses=(), sort_by="Priorität"):
    selected = []
    for lead in leads:
        text = f"{lead.name} {lead.industry.value}".casefold()
        if search.strip().casefold() not in text:
            continue
        if locations and (lead.location or "Unknown") not in locations:
            continue
        if industries and lead.industry.value not in industries:
            continue
        if stages and lead.stage_classification not in stages:
            continue
        if statuses and review_status(lead, decisions) not in statuses:
            continue
        if fit == "Passend" and (lead.eligibility_status != "Eligible" or lead.hard_exclusions):
            continue
        if fit == "Ausgeschlossen" and not (lead.hard_exclusions or lead.eligibility_status == "Excluded"):
            continue
        if fit == "Ungeklärt" and (lead.eligibility_status != "Unknown" or lead.hard_exclusions):
            continue
        selected.append(lead)
    fields = {"Quality Score": "overall_score", "Fund Fit": "fund_fit_score",
              "Earliness": "earliness_score", "Entdeckungsdatum": "discovered_at"}
    def key(lead):
        field = fields.get(sort_by)
        if field:
            value = getattr(lead, field)
            numeric = value.timestamp() if field == "discovered_at" and value else value
            return (value is None, -(numeric or 0), lead.id)
        return (review_status(lead, decisions) in {"Excluded", "Reject"},
                not high_priority(lead, decisions), lead.overall_score is None,
                -(lead.overall_score or 0), lead.id)
    return sorted(selected, key=key)
