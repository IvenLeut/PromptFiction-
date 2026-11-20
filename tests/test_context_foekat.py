"""Offline tests for context.foekat (fixtures recorded live on 2026-11-20, trimmed to the result table / detail blocks)."""
import re
import urllib.parse
from datetime import date
from pathlib import Path

import pytest

from context.cache import Cache, NoCache
from context.foekat import (
    SEARCH_URL, START_URL, FoekatError, Session, clean_name, detail_url, encode_form, first_word, grant_lookup,
    match_confidence, parse_amount, parse_count, parse_detail, parse_rows, programme_for,
)

FIXTURES = Path(__file__).parent / "fixtures" / "context"


def load(key):
    return (FIXTURES / f"foekat_{key}.html").read_text(encoding="utf-8")


def form_of(data):
    return dict(urllib.parse.parse_qsl(data.decode("ascii"), encoding="iso-8859-15"))


def fixture_fetch(search=None, detail=None, narrowed=None, pages=None):
    """Answer quick searches with `search`, narrowed searches with `narrowed`, detail GETs with `detail` (FKZ substituted)."""
    calls = []

    def fetch(method, url, data=None):
        calls.append((method, url, data))
        if method == "GET":
            if detail is None:
                raise FoekatError("HTTP 404")
            fkz = urllib.parse.unquote(url.rsplit("fkz=", 1)[1])
            return detail.replace("03EFBW0275", fkz)
        fields = form_of(data)
        if fields.get("suche.detailSuche") == "true":
            return narrowed
        if pages is not None:
            return pages[int(fields.get("suche.listrowfrom", "1"))]
        return search
    fetch.calls = calls
    return fetch


ROW = """<tr><td scope="row" class="table_cell"><a href="SucheAction.do?actionMode=view&amp;fkz={fkz}">{fkz}&nbsp;</a></td>
<td class="table_cell"><div>BMWE</div>PT-J</td><td class="table_cell">{recipient}&nbsp;</td><td class="table_cell">{executing}&nbsp;</td>
<td class="table_cell">{thema}&nbsp;</td><td class="table_cell">01.02.2024&nbsp;<br />31.01.2026&nbsp;</td>
<td class="table_cell">{amount}&nbsp;</td><td class="table_cell">N&nbsp;</td></tr>"""


def synthetic_page(count, rows):
    body = "".join(ROW.format(**r) for r in rows)
    return ('<h1 aria-label="Suchergebnis. %d Treffer insgesamt. Angezeigt 1 bis %d">Suchergebnis</h1>'
            '<table aria-label="Suchergebnis"><thead><tr><th>FKZ</th></tr></thead><tbody>%s</tbody></table>' % (count, len(rows), body))


def row(fkz, thema, recipient="Universit&auml;t Testhausen", executing="Universit&auml;t Testhausen - Institut X", amount="1.234.567,89 &euro;"):
    return {"fkz": fkz, "thema": thema, "recipient": recipient, "executing": executing, "amount": amount}


# --- parsing ---------------------------------------------------------------------------------------

def test_parse_rows_live_spinmagic():
    rows = parse_rows(load("search_spinmagic"))
    assert len(rows) == 1
    r = rows[0]
    assert r["fkz"] == "03EFBW0275"
    assert r["ressort"] == "BMWE PT-J"
    assert r["recipient"] == "Universität Stuttgart"
    assert r["executing"].startswith("Universität Stuttgart - Fakultät 5 Informatik") and "für" in r["executing"]
    assert r["thema"] == "SpinMagIC"
    assert (r["start"], r["end"]) == (date(2024, 9, 1), date(2026, 9, 30))
    assert r["amount"] == 972638
    assert r["project"] == "N"


def test_parse_rows_synthetic_umlauts_and_amount():
    rows = parse_rows(synthetic_page(1, [row("03EGSBW999", "Gr&uuml;n-Tech")]))
    assert rows[0]["thema"] == "Grün-Tech"
    assert rows[0]["recipient"] == "Universität Testhausen"
    assert rows[0]["amount"] == 1234567
    assert (rows[0]["start"], rows[0]["end"]) == (date(2024, 2, 1), date(2026, 1, 31))


def test_parse_rows_takes_fkz_from_link_when_cell_has_suffix():
    rows = parse_rows(load("search_enviconnect"))
    assert rows[0]["fkz"] == "03EGSBW750"
    assert rows[0]["thema"] == "enviConnect"


def test_parse_count():
    assert parse_count(load("search_spinmagic")) == 1
    assert parse_count(load("search_none")) == 0
    assert parse_count(load("search_03eg_page1")) == 717
    assert parse_count("<html>nothing</html>") == 0


@pytest.mark.parametrize("text,expected", [
    ("972.638,00 €", 972638), ("1.234.567,89 €", 1234567), ("148.800,00 &euro;", 148800), ("500 €", 500), ("", None), ("k. A.", None),
])
def test_parse_amount(text, expected):
    assert parse_amount(text) == expected


def test_parse_detail_live_spinmagic():
    d = parse_detail(load("detail_spinmagic"))
    assert d["fkz"] == "03EFBW0275"
    assert d["thema"] == "SpinMagIC"
    assert d["amount"] == 972638
    assert (d["start"], d["end"]) == (date(2024, 9, 1), date(2026, 9, 30))
    assert "EXIST" in d["leistungsplan"]
    assert d["foerderart"] == "Direkte Projektförderung"
    assert d["recipient"] == "Universität Stuttgart"
    assert d["recipient_ort"] == "Stuttgart"
    assert d["recipient_land"].startswith("Baden-Württemberg")
    assert d["executing"].endswith("Theoretische Elektrotechnik (IIS)")


@pytest.mark.parametrize("key,fkz,amount,recipient", [
    ("hochquant", "03EFBB0063", 876964, "Brandenburgische Technische Universität Cottbus-Senftenberg"),
    ("siderogain", "03EFSN0258", 774408, "Helmholtz-Zentrum Dresden - Rossendorf e. V."),
    ("enviconnect", "03EGSBW750", 148800, "Universität Stuttgart"),
])
def test_parse_detail_other_live_pages(key, fkz, amount, recipient):
    d = parse_detail(load("detail_" + key))
    assert (d["fkz"], d["amount"], d["recipient"]) == (fkz, amount, recipient)
    assert d["start"] < d["end"]


def test_parse_detail_without_blocks():
    assert parse_detail("<html><body>Sitzung abgelaufen</body></html>")["fkz"] == ""


def test_programme_mapping():
    assert programme_for("03EFBW0275") == "EXIST-Forschungstransfer"
    assert programme_for("03EGSBW750", "irrelevant") == "EXIST-Gründungsstipendium"
    assert programme_for("01MQ22007B", "Forschung, Entwicklung und Innovation zu Digitale Technologien") == \
        "Forschung, Entwicklung und Innovation zu Digitale Technologien"
    assert programme_for("01N121134P", "Quantentechnologien: Quantencomputing und -simulation") == "Quantentechnologien: Quantencomputing und -simulation"
    assert programme_for("16KN123", "Technologietransfer; EXIST") == "EXIST"
    assert programme_for("16KN123") == "Bundesförderung"


# --- names ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("name,expected", [
    ("HoCHQuant GmbH i.G.", "HoCHQuant"), ("SpinMagIC GmbH", "SpinMagIC"), ("Grün-Tech UG (haftungsbeschränkt)", "Grün-Tech"),
    ("Semodia GmbH i. G.", "Semodia"), ("Helmholtz-Zentrum e. V.", "Helmholtz-Zentrum"), ("Müller & Co. KG", "Müller"), ("Agile Robots SE", "Agile Robots"),
])
def test_clean_name(name, expected):
    assert clean_name(name) == expected


def test_first_word():
    assert first_word("Quantum Brilliance GmbH") == "Quantum"
    assert first_word("The Grüntech UG") == "Grüntech"
    assert first_word("AI UG") is None


def test_match_confidence_levels():
    assert match_confidence("Gruentech GmbH", "GRÜN-TECH") == 0.9
    assert match_confidence("SpinMagIC GmbH i.G.", "SpinMagIC") == 0.9
    assert match_confidence("HoCHQuant", "Verbundprojekt HoCHQuant - Teilvorhaben A") == 0.7
    assert match_confidence("Semodia GmbH", "Irgendwas", recipient="Semodia GmbH") == 0.7
    assert match_confidence("Quantum Brilliance", "Quantum Computing Demonstrator") == 0.5
    assert match_confidence("Xyzzy Robotics", "Solarzellen", recipient="TU Berlin") == 0.0
    assert match_confidence("", "SpinMagIC") == 0.0


# --- lookup with live fixtures ----------------------------------------------------------------------

def test_live_spinmagic_by_name():
    fetch = fixture_fetch(search=load("search_spinmagic"), detail=load("detail_spinmagic"))
    grants, lookup = grant_lookup("SpinMagIC", institution="Universität Stuttgart", reference=None, cache=NoCache(), fetch=fetch)
    assert lookup.errors == []
    assert len(grants) == 1
    g = grants[0]
    assert g.programme == "EXIST-Forschungstransfer"
    assert g.reference == "03EFBW0275"
    assert g.recipient.startswith("Universität Stuttgart - Fakultät 5")  # recipient not repeated
    assert g.amount_eur == 972638
    assert (g.start, g.end) == (date(2024, 9, 1), date(2026, 9, 30))
    assert str(g.url) == SEARCH_URL + "?actionMode=view&fkz=03EFBW0275"
    assert lookup.fields["match_confidence"] == 0.9
    assert lookup.fields["institution"].startswith("Universität Stuttgart - Fakultät 5")
    assert [s.type for s in lookup.signals] == ["exist_projekt"]
    assert lookup.signals[0].date == date(2024, 9, 1)
    assert "Thema: SpinMagIC; Förderempfänger: Universität Stuttgart; Ausführende Stelle: Universität Stuttgart" in lookup.signals[0].evidence
    assert "Laufzeit: 01.09.2024 bis 30.09.2026; Summe: 972.638 €" in lookup.signals[0].evidence
    assert [e.field for e in lookup.evidence] == ["grants", "institution", "match_confidence"]
    # requests: one quick search, one detail page
    assert [(m, u.split("?")[0]) for m, u, _ in fetch.calls] == [("POST", SEARCH_URL), ("GET", SEARCH_URL)]
    fields = form_of(fetch.calls[0][2])
    assert fields == {"actionMode": "searchlist", "suche.detailSuche": "false", "suche.schnellSuche": "%SpinMagIC%",
                      "suche.lfdVhb": "N", "suche.listrowpersite": "100"}


def test_live_hochquant_legal_form_stripped():
    fetch = fixture_fetch(search=load("search_hochquant"), detail=load("detail_hochquant"))
    grants, lookup = grant_lookup("HoCHQuant GmbH i.G.", institution=None, reference=None, cache=NoCache(), fetch=fetch)
    assert form_of(fetch.calls[0][2])["suche.schnellSuche"] == "%HoCHQuant%"
    assert len(fetch.calls) == 2
    assert grants[0].reference == "03EFBB0063" and grants[0].amount_eur == 876964
    assert grants[0].recipient == "Brandenburgische Technische Universität Cottbus-Senftenberg"  # executing unit identical -> not repeated
    assert lookup.fields["match_confidence"] == 0.9


def test_live_siderogain():
    fetch = fixture_fetch(search=load("search_siderogain"), detail=load("detail_siderogain"))
    grants, lookup = grant_lookup("SideroGaIn", institution="HZDR", reference=None, cache=NoCache(), fetch=fetch)
    assert grants[0].reference == "03EFSN0258" and grants[0].amount_eur == 774408
    assert grants[0].recipient.startswith("Helmholtz-Zentrum Dresden - Rossendorf e. V. - Helmholtz-Institut Freiberg")
    assert lookup.fields["institution"].endswith("(HIF)")


def test_live_enviconnect_gruendungsstipendium():
    fetch = fixture_fetch(search=load("search_enviconnect"), detail=load("detail_enviconnect"))
    grants, lookup = grant_lookup("enviConnect", institution=None, reference=None, cache=NoCache(), fetch=fetch)
    assert grants[0].programme == "EXIST-Gründungsstipendium"
    assert grants[0].reference == "03EGSBW750" and grants[0].amount_eur == 148800
    assert (grants[0].start, grants[0].end) == (date(2023, 3, 1), date(2024, 2, 29))
    assert lookup.signals[0].type == "exist_projekt"


def test_live_no_hits_tries_first_word_then_gives_up():
    fetch = fixture_fetch(search=load("search_none"))
    grants, lookup = grant_lookup("Xyzzyqwv Robotics GmbH", institution="TU Berlin", reference=None, cache=NoCache(), fetch=fetch)
    assert grants == [] and lookup.fields == {} and lookup.signals == []
    assert lookup.errors == ["foekat: keine Treffer"]
    assert [form_of(d)["suche.schnellSuche"] for _, _, d in fetch.calls] == ["%Xyzzyqwv Robotics%", "%Xyzzyqwv%"]


def test_reference_path_fetches_detail_only():
    fetch = fixture_fetch(detail=load("detail_spinmagic"))
    grants, lookup = grant_lookup("Irgendein Name", institution=None, reference="03EFBW0275", cache=NoCache(), fetch=fetch)
    assert [m for m, _, _ in fetch.calls] == ["GET"]
    assert fetch.calls[0][1] == detail_url("03EFBW0275")
    assert grants[0].reference == "03EFBW0275"
    assert lookup.fields["match_confidence"] == 1.0
    assert lookup.errors == []


def test_unknown_reference_falls_back_to_name_search():
    fetch = fixture_fetch(search=load("search_spinmagic"), detail=load("detail_spinmagic"))
    original = fetch

    def fetch2(method, url, data=None):
        if method == "GET" and "fkz=03EFXX9999" in url:
            fetch.calls.append((method, url, data))
            return "<html>kein Vorhaben</html>"
        return original(method, url, data)
    grants, lookup = grant_lookup("SpinMagIC", institution=None, reference="03EFXX9999", cache=NoCache(), fetch=fetch2)
    assert "foekat: FKZ 03EFXX9999 nicht gefunden" in lookup.errors
    assert grants[0].reference == "03EFBW0275" and lookup.fields["match_confidence"] == 0.9


def test_ambiguous_narrowed_with_institution():
    narrowed = load("search_quantum_narrowed")  # 19 Treffer, trimmed to 5 rows
    fetch = fixture_fetch(search=synthetic_page(2529, [row("01XX%03d" % i, "Quantum thing %d" % i) for i in range(100)]),
                          narrowed=narrowed, detail=load("detail_spinmagic"))
    grants, lookup = grant_lookup("Quantum", institution="Stuttgart", reference=None, cache=NoCache(), fetch=fetch)
    posts = [form_of(d) for m, _, d in fetch.calls if m == "POST"]
    assert posts[0]["suche.detailSuche"] == "false"
    assert posts[1]["suche.detailSuche"] == "true"
    assert posts[1]["suche.themaSuche[0]"] == "%Quantum%" and posts[1]["suche.nameZeStSuche"] == "%Stuttgart%" and posts[1]["suche.ZeSt"] == "ST"
    assert len(posts) == 2  # the broad search is not paginated once it is narrowed
    assert len(grants) == 3
    assert {g.reference for g in grants} <= {"01MQ22007B", "01N121134P", "01N122033B", "01N122033B", "01NC2014D", "01NC2041A"}
    assert lookup.errors == ["foekat: mehrdeutig (19 Treffer)"]
    assert lookup.fields["match_confidence"] == 0.7
    assert sum(1 for m, _, _ in fetch.calls if m == "GET") == 3


def test_non_exist_grant_gets_foerderprojekt_signal():
    rows = [row("01MQ22007B", "Verbundprojekt: EniQmA - Quantum-Anwendungen", recipient="Universit&auml;t Stuttgart", executing="Universit&auml;t Stuttgart - IAAS")]
    fetch = fixture_fetch(search=synthetic_page(1, rows))  # no detail page -> row data only
    grants, lookup = grant_lookup("EniQmA", institution=None, reference=None, cache=NoCache(), fetch=fetch)
    assert grants[0].programme == "Bundesförderung" and grants[0].reference == "01MQ22007B"
    assert grants[0].recipient == "Universität Stuttgart - IAAS"
    assert lookup.signals[0].type == "foerderprojekt"
    assert lookup.fields["match_confidence"] == 0.7
    assert lookup.errors == ["foekat: HTTP 404"]


def test_ambiguous_without_institution_filters_by_name():
    rows = [row("01XX%03d" % i, "Something else %d" % i) for i in range(11)] + [row("03EGSBW001", "Grün-Tech")]
    fetch = fixture_fetch(search=synthetic_page(12, rows), detail=load("detail_spinmagic"))
    grants, lookup = grant_lookup("Gruentech UG", institution=None, reference=None, cache=NoCache(), fetch=fetch)
    assert [g.reference for g in grants] == ["03EGSBW001"]
    assert grants[0].programme == "EXIST-Gründungsstipendium"
    assert lookup.fields["match_confidence"] == 0.9
    assert lookup.errors == []


def test_no_name_match_in_hits_returns_empty():
    fetch = fixture_fetch(search=synthetic_page(2, [row("01XX001", "Solarzellen"), row("01XX002", "Windkraft")]))
    grants, lookup = grant_lookup("Xyzzy Robotics", institution=None, reference=None, cache=NoCache(), fetch=fetch)
    assert grants == []
    assert lookup.errors == ["foekat: keine Treffer"]
    assert not any(m == "GET" for m, _, _ in fetch.calls)


def test_pagination_when_count_exceeds_page_size():
    page1 = synthetic_page(150, [row("01XX%03d" % i, "Filler %d" % i) for i in range(100)])
    page2 = synthetic_page(150, [row("01XX%03d" % i, "Filler %d" % i) for i in range(100, 149)] + [row("03EFBY0001", "Deepsensor")])
    fetch = fixture_fetch(pages={1: page1, 101: page2}, detail=load("detail_spinmagic"))
    grants, lookup = grant_lookup("Deepsensor GmbH", institution=None, reference=None, cache=NoCache(), fetch=fetch)
    posts = [form_of(d) for m, _, d in fetch.calls if m == "POST"]
    assert [p.get("suche.listrowfrom") for p in posts] == [None, "101"]
    assert posts[1]["suche.schnellSuche"] == "%Deepsensor%"
    assert [g.reference for g in grants] == ["03EFBY0001"]
    assert lookup.fields["match_confidence"] == 0.9


def test_detail_failure_falls_back_to_row_data():
    fetch = fixture_fetch(search=load("search_spinmagic"))  # detail=None -> FoekatError("HTTP 404")
    grants, lookup = grant_lookup("SpinMagIC", institution=None, reference=None, cache=NoCache(), fetch=fetch)
    assert grants[0].reference == "03EFBW0275" and grants[0].amount_eur == 972638
    assert grants[0].start == date(2024, 9, 1)
    assert lookup.errors == ["foekat: HTTP 404"]
    assert lookup.fields["match_confidence"] == 0.9


def test_http_error_is_reported_not_raised():
    def fetch(method, url, data=None):
        raise FoekatError("HTTP 503")
    grants, lookup = grant_lookup("SpinMagIC", institution=None, reference=None, cache=NoCache(), fetch=fetch)
    assert grants == [] and lookup.errors == ["foekat: HTTP 503"]

    def boom(method, url, data=None):
        raise ValueError("kaputt")
    grants, lookup = grant_lookup("SpinMagIC", institution=None, reference="03EFBW0275", cache=NoCache(), fetch=boom)
    assert grants == [] and lookup.errors == ["foekat: ValueError"]


def test_empty_name_without_reference():
    grants, lookup = grant_lookup("", institution=None, reference=None, cache=NoCache(), fetch=fixture_fetch())
    assert grants == [] and lookup.errors == [] and lookup.fields == {}


# --- encoding, cache, session -----------------------------------------------------------------------

def test_post_body_is_iso_8859_15():
    body = encode_form({"suche.schnellSuche": "%Grüntech%", "suche.nameZeStSuche": "%Universität Straße€%"})
    assert body == b"suche.schnellSuche=%25Gr%FCntech%25&suche.nameZeStSuche=%25Universit%E4t+Stra%DFe%A4%25"
    assert b"%C3%BC" not in body  # not UTF-8


def test_umlaut_name_reaches_fetch_encoded():
    fetch = fixture_fetch(search=load("search_none"))
    grant_lookup("Grüntech GmbH", institution=None, reference=None, cache=NoCache(), fetch=fetch)
    assert b"suche.schnellSuche=%25Gr%FCntech%25" in fetch.calls[0][2]
    assert form_of(fetch.calls[0][2])["suche.schnellSuche"] == "%Grüntech%"


def test_cache_prevents_second_fetch(tmp_path):
    cache = Cache(tmp_path / "c.db")
    fetch = fixture_fetch(search=load("search_spinmagic"), detail=load("detail_spinmagic"))
    first, _ = grant_lookup("SpinMagIC", institution=None, reference=None, cache=cache, fetch=fetch)
    assert len(fetch.calls) == 2
    second, lookup = grant_lookup("SpinMagIC", institution=None, reference=None, cache=cache, fetch=fetch)
    assert len(fetch.calls) == 2
    assert second == first and lookup.errors == []


def test_session_starts_before_first_request(monkeypatch):
    opened = []

    def fake_open(self, method, url, data):
        opened.append((method, url, data))
        return "<html/>"
    monkeypatch.setattr(Session, "_open", fake_open)
    session = Session()
    session.fetch("POST", SEARCH_URL, b"a=b")
    session.fetch("GET", detail_url("03EFBW0275"))
    assert opened == [("GET", START_URL, None), ("POST", SEARCH_URL, b"a=b"), ("GET", detail_url("03EFBW0275"), None)]


def test_session_retries_on_5xx(monkeypatch):
    import context.foekat as mod
    from urllib.error import HTTPError
    attempts = []

    class Opener:
        def open(self, req, timeout):
            attempts.append(req.full_url)
            raise HTTPError(req.full_url, 503, "Service Unavailable", {}, None)
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    session = Session(retries=1)
    session.opener = Opener()
    with pytest.raises(FoekatError, match="HTTP 503"):
        session.fetch("GET", detail_url("03EFBW0275"))
    assert len(attempts) == 2  # session start fails first: one try + one retry


def test_detail_url_quotes_fkz():
    assert detail_url("03EGSBW750 TIB") == SEARCH_URL + "?actionMode=view&fkz=03EGSBW750%20TIB"
    assert re.fullmatch(r"https://foerderportal\.bund\.de/foekat/jsp/SucheAction\.do\?actionMode=view&fkz=[A-Z0-9%]+", detail_url("03EFBW0275"))


# --- person names in the executing unit ------------------------------------------------------------
# Real catalogue units (fixture foekat_detail_spinmagic.html and FKZ 03EFBE0166 from examples/sourcing/shortlist.json),
# with the head of the chair pseudonymised.
SPINMAGIC_UNIT = ("Universität Stuttgart - Fakultät 5 Informatik, Elektrotechnik und Informationstechnik - "
                  "Institut für Intelligente Sensorik und Theoretische Elektrotechnik (IIS)")


@pytest.mark.parametrize("suffix", [", Prof. Dr.-Ing. Erika Musterfrau", " Prof. Dr. Max Muster", " AG Erika Musterfrau"])
def test_person_names_never_reach_grant_or_evidence(suffix):
    detail = load("detail_spinmagic").replace("(IIS)</div>", "(IIS)%s</div>" % suffix, 1)
    fetch = fixture_fetch(search=load("search_spinmagic"), detail=detail)
    grants, lookup = grant_lookup("SpinMagIC", institution=None, reference=None, cache=NoCache(), fetch=fetch)
    assert grants[0].recipient == SPINMAGIC_UNIT and lookup.fields["institution"] == SPINMAGIC_UNIT
    texts = [s.evidence for s in lookup.signals] + [e.finding for e in lookup.evidence]
    assert not any("Muster" in text for text in texts)
    assert "Ausführende Stelle: " + SPINMAGIC_UNIT + "; Laufzeit" in lookup.signals[0].evidence


def test_untitled_working_group_head_removed_subject_groups_kept():
    from context.foekat import _grant_from
    unit = ("Charité - Universitätsmedizin Berlin, Berliner Institut für Gesundheitsforschung in der Charité "
            "AG Sophie van Linthout")
    grant, facts = _grant_from({"fkz": "03EFBE0166", "recipient": "Charité - Universitätsmedizin Berlin", "executing": unit}, None)
    assert grant.recipient == facts["executing"] == unit.removesuffix(" AG Sophie van Linthout")
    subject = "Freie Universität Berlin - Institut für Informatik - AG Künstliche Intelligenz"
    assert _grant_from({"fkz": "03EFBE0001", "recipient": "Freie Universität Berlin", "executing": subject}, None)[0].recipient == subject


def test_unit_that_is_only_a_person_becomes_empty():
    from context.foekat import _grant_from
    grant, facts = _grant_from({"fkz": "03EFBE0002", "recipient": "Universität X", "executing": "Prof. Dr. Erika Musterfrau"}, None)
    assert grant.recipient == "Universität X" and facts["executing"] == ""
