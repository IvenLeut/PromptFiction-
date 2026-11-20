"""Field definitions for structured company research."""
COMPANY_FIELDS = {
    "founding_date": r"Gründungsdatum|Founding date",
    "headquarters": r"Hauptsitz|Headquarters",
    "company_status": r"Unternehmensstatus|Gründungsstatus|Company status",
}
PRODUCT_FIELDS = {
    "economic_buyer": r"Wirtschaftlicher Käufer|Economic buyer",
    "business_model": r"Geschäftsmodell|Business model",
    "advantage": r"Wettbewerbsvorteil|Competitive advantage",
    "ip": r"Patente?|Patentstatus|Schutzrechte|Intellectual property|Patent status",
    "development_status": r"Entwicklungsstand|Development status",
    "next_milestone": r"Nächster Produktmeilenstein|Next product milestone",
}
TRACTION_EVENTS = {
    "paid_customers": r"Zahlende Kunden|Paying customers",
    "customers_payment_unknown": r"Kundenreferenz|Customer reference|Bestehende Kunden",
    "paid_pilots": r"Bezahlte Pilotprojekte?|Paid pilots?",
    "unpaid_pilots": r"Unbezahlte Pilotprojekte?|Unpaid pilots?",
    "pilots_payment_unknown": r"Pilotprojekte?|Pilot projects?",
    "lois": r"Absichtserklärungen?|LOIs?|Letters? of intent",
    "commercial_partners": r"Kommerzielle Partnerschaft|Commercial partnership",
    "research_partners": r"Forschungskooperation|Forschungspartner|Research partners?",
}
TRACTION_METRICS = {
    "usage": r"Produktnutzung|Product usage",
    "revenue": r"Jahresumsatz|Annual revenue|Reported revenue",
    "growth": r"Umsatzwachstum|Revenue growth",
}
FUNDING_EVENTS = {
    "rounds": r"Frühere Finanzierungsrunde|Previous funding round",
    "investors": r"Investoren|Investors",
    "public_grants": r"Öffentliche Förderung|Fördermittel|Public grants?",
}
FUNDING_FIELDS = {
    "fundraising_status": r"Fundraising[- ]Status|Fundraising status",
    "planned_round": r"Geplante Finanzierungsrunde|Planned funding round",
    "use_of_funds": r"Mittelverwendung|Use of funds",
    "next_milestone": r"Nächster Finanzierungsmeilenstein|Next funding milestone",
    "time_to_milestone": r"Zeitraum bis zum Meilenstein|Time to milestone",
    "burn_rate": r"Burn Rate|Kapitalverbrauch",
    "cash_runway": r"Cash Runway|Liquiditätsreichweite",
}
FOUNDER_FIELDS = {
    "role": r"Rolle|Role",
    "qualifications": r"Qualifikation|Hintergrund|Background|Experience",
    "previous_companies": r"Frühere Unternehmen|Previous companies",
    "founding_experience": r"Gründungserfahrung|Founding experience",
    "customer_problem_experience": r"Erfahrung mit dem Kundenproblem|Experience with the customer problem",
}

RESEARCH_LABELS = {
    **{f"company.{key}": label for key, label in COMPANY_FIELDS.items()},
    **{f"product.{key}": label for key, label in PRODUCT_FIELDS.items()},
    **{f"traction.{key}": label for key, label in (TRACTION_EVENTS | TRACTION_METRICS).items()},
    **{f"funding.{key}": label for key, label in (FUNDING_EVENTS | FUNDING_FIELDS).items()},
}
