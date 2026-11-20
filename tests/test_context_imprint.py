"""Offline tests for context.imprint (fixtures recorded from public imprint pages, 2026-11-20)."""
from pathlib import Path

import pytest

from context.cache import NoCache
from context.imprint import GENERIC_MAILBOXES, MAX_REQUESTS, imprint_lookup, parse_imprint
from context.web import CompanyPage

FIXTURES = Path(__file__).parent / "fixtures" / "context"
SITE = "https://www.example.org/"


def page_from_html(html: str) -> CompanyPage:
    page = CompanyPage()
    page.feed(html)
    page.close()
    page.flush()
    return page


def page_from_text(*lines: str) -> CompanyPage:
    return page_from_html("".join(f"<p>{line}</p>" for line in lines))


def fixture(name: str) -> CompanyPage:
    return page_from_html((FIXTURES / name).read_text("utf-8"))


class FakeFetch:
    """fetch(url, site) replacement: a URL map of pages or exceptions, recording every call."""

    def __init__(self, pages: dict, redirects: dict | None = None):
        self.pages, self.redirects, self.calls = pages, redirects or {}, []

    def __call__(self, url, site):
        self.calls.append(url)
        assert site == "example.org"
        final = self.redirects.get(url, url)
        page = self.pages.get(final)
        if page is None:
            raise ValueError("Keine HTML-Seite (HTTP 404)")
        if isinstance(page, Exception):
            raise page
        return final, page


def lookup(pages, redirects=None, website=SITE):
    fetch = FakeFetch(pages, redirects)
    return imprint_lookup(website, cache=NoCache(), fetch=fetch), fetch


def fields_of(*lines):
    return {name: value for name, (value, _) in parse_imprint("\n".join(lines)).items()}


# --- discovery -------------------------------------------------------------------------------------
def test_footer_link_is_followed_first():
    result, fetch = lookup({
        SITE: fixture("imprint_home_footer.html"),
        "https://www.example.org/de/impressum.php?lang=de": fixture("imprint_emqopter_impressum.html"),
    })
    assert fetch.calls == [SITE, "https://www.example.org/de/impressum.php?lang=de"]  # fragment stripped
    assert result.errors == []
    assert result.fields["imprint_url"] == "https://www.example.org/de/impressum.php?lang=de"
    assert result.fields["legal_form"] == "GmbH"
    assert result.fields["company_name"] == "Emqopter GmbH"
    assert result.fields["register_id"] == "HRB 13237, Amtsgericht Würzburg"
    assert result.fields["in_formation"] is False
    assert result.fields["managing_directors"] == ["Marvin Bihl", "Nils Gageik"]
    assert result.fields["contact_email"] == "info@emqopter.de"
    assert result.fields["address_city"] == "Würzburg"
    # One Evidence per field, pointing at the imprint URL and quoting the matched line.
    by_field = {item.field: item for item in result.evidence}
    assert set(by_field) == set(result.fields)
    assert all(str(item.url) == result.fields["imprint_url"] and item.source == "Impressum" for item in result.evidence)
    assert "Marvin Bihl, Dr. Nils Gageik" in by_field["managing_directors"].finding
    assert "HRB 13237" in by_field["register_id"].finding
    assert [(s.source, s.type, str(s.url)) for s in result.signals] == [("Impressum", "impressum", result.fields["imprint_url"])]
    assert "Emqopter GmbH" in result.signals[0].evidence and len(result.signals[0].evidence) <= 8000


def test_common_paths_are_tried_when_the_homepage_has_no_imprint_link():
    home = page_from_text("Welcome to our product page", "Features", "Pricing")
    result, fetch = lookup({SITE: home, "https://www.example.org/imprint": fixture("imprint_kiutra_legal_notice.html")})
    assert fetch.calls == [SITE, "https://www.example.org/impressum", "https://www.example.org/impressum/",
                           "https://www.example.org/imprint"]
    assert result.fields["imprint_url"] == "https://www.example.org/imprint"
    assert result.fields["company_name"] == "kiutra GmbH"


def test_no_imprint_found_reports_error_and_respects_request_budget():
    home = page_from_text("Welcome")
    result, fetch = lookup({SITE: home})
    assert result.fields == {} and result.evidence == [] and result.signals == []
    assert result.errors == ["impressum: nicht gefunden"]
    assert len(fetch.calls) == MAX_REQUESTS


def test_js_only_homepage_falls_back_to_paths_and_redirects_are_kept():
    empty = page_from_html("<html><body><div id='root'></div></body></html>")
    result, fetch = lookup(
        {SITE: empty, "https://www.example.org/legal/imprint/": fixture("imprint_semodia_impressum.html")},
        redirects={"https://www.example.org/imprint": "https://www.example.org/legal/imprint/"},
    )
    assert result.fields["imprint_url"] == "https://www.example.org/legal/imprint/"
    assert result.fields["managing_directors"] == ["Stephan Hensel", "Anna Menschner"]
    assert result.fields["register_id"] == "HRB 38932, Amtsgericht Dresden"
    assert result.fields["address_city"] == "Radebeul"
    assert len(fetch.calls) <= MAX_REQUESTS


def test_homepage_link_text_only_pages_are_not_mistaken_for_the_imprint():
    # A footer saying "Impressum" and "© Muster GmbH" is not an imprint; the linked page is.
    home = page_from_html("<p>© 2026 Muster GmbH</p><footer><a href='/impressum'>Impressum</a></footer>")
    imprint = page_from_text("Impressum", "Angaben gemäß § 5 TMG", "Muster GmbH", "Geschäftsführer: Kim Muster")
    result, fetch = lookup({SITE: home, "https://www.example.org/impressum": imprint})
    assert result.fields["imprint_url"] == "https://www.example.org/impressum"
    assert result.fields["managing_directors"] == ["Kim Muster"]


def test_fetch_errors_never_raise():
    boom = FakeFetch({SITE: RuntimeError("socket exploded")})
    result = imprint_lookup(SITE, cache=NoCache(), fetch=boom)
    assert result.errors == ["impressum: RuntimeError"] and result.fields == {}

    def unreachable(url, site):
        raise OSError("connection refused")
    result = imprint_lookup(SITE, cache=NoCache(), fetch=unreachable)
    assert result.errors == ["impressum: nicht gefunden"] and result.fields == {}
    assert imprint_lookup("", cache=NoCache(), fetch=unreachable).errors == ["impressum: ungültige Website"]


def test_second_call_is_served_from_cache(tmp_path):
    from context.cache import Cache
    cache = Cache(tmp_path / "c.db")
    pages = {SITE: fixture("imprint_home_footer.html"),
             "https://www.example.org/de/impressum.php?lang=de": fixture("imprint_emqopter_impressum.html")}
    first, fetch = FakeFetch(pages), None
    a = imprint_lookup(SITE, cache=cache, fetch=first)
    second = FakeFetch(pages)
    b = imprint_lookup(SITE, cache=cache, fetch=second)
    assert second.calls == [] and a.fields == b.fields and len(b.signals) == 1


# --- legal forms -----------------------------------------------------------------------------------
@pytest.mark.parametrize("line, form", [
    ("Muster Technologies GmbH", "GmbH"),
    ("Muster Bildung gGmbH", "gGmbH"),
    ("Muster Robotics UG (haftungsbeschränkt)", "UG (haftungsbeschränkt)"),
    ("Muster Unternehmergesellschaft (haftungsbeschränkt)", "UG (haftungsbeschränkt)"),
    ("Muster Energy AG", "AG"),
    ("Muster Aerospace SE", "SE"),
    ("Muster & Partner GbR", "GbR"),
    ("Förderverein Muster e.V.", "e.V."),
    ("Muster Handel KG", "KG"),
    ("Muster Technik GmbH & Co. KG", "GmbH & Co. KG"),
    ("Muster Technik UG (haftungsbeschränkt) & Co. KG", "GmbH & Co. KG"),
    ("Kim Muster e.K.", "Einzelunternehmen"),
    ("Kim Muster, Einzelunternehmen", "Einzelunternehmen"),
])
def test_legal_form_variants(line, form):
    found = fields_of("Impressum", line, "Musterweg 1", "10115 Berlin")
    assert found["legal_form"] == form
    assert found["company_name"].endswith(line.split(", ")[-1]) or form == "Einzelunternehmen"
    assert "in_formation" not in found  # neither i.G. nor a register number


def test_keine_only_for_an_explicit_private_person():
    private = fields_of("Impressum", "Angaben gemäß § 5 TMG", "Kim Muster", "Dies ist eine private Website ohne gewerblichen Zweck.")
    assert private["legal_form"] == "keine" and "company_name" not in private
    assert "legal_form" not in fields_of("Impressum", "Kim Muster", "Musterweg 1, 10115 Berlin")


def test_ag_is_not_taken_from_amtsgericht_abbreviation():
    found = fields_of("Impressum", "Muster Robotics GmbH", "Registergericht: AG Charlottenburg HRB 12345 B")
    assert found["legal_form"] == "GmbH"
    assert found["register_id"] == "HRB 12345 B, Amtsgericht Charlottenburg"
    only_register = fields_of("Impressum", "AG Charlottenburg HRB 12345 B")
    assert "legal_form" not in only_register


def test_prose_mention_of_another_company_does_not_win():
    found = fields_of("Impressum erstellt mit dem Generator der Deutschen Anwaltshotline AG", "Emqopter GmbH")
    assert found["legal_form"] == "GmbH" and found["company_name"] == "Emqopter GmbH"


# --- in formation ----------------------------------------------------------------------------------
@pytest.mark.parametrize("line", ["Muster Robotics UG (haftungsbeschränkt) i.G.", "Muster Robotics UG i.G.",
                                  "Muster Robotics GmbH i. Gr.", "Muster Robotics GmbH (in Gründung)"])
def test_in_formation_true(line):
    found = fields_of("Impressum", line, "Vertreten durch: Kim Muster")
    assert found["in_formation"] is True
    assert found["legal_form"] in {"UG (haftungsbeschränkt)", "GmbH"}
    assert found["company_name"].startswith("Muster Robotics")


def test_in_formation_false_with_register_and_none_without():
    with_register = fields_of("Muster GmbH", "Amtsgericht München HRB 123456")
    assert with_register["in_formation"] is False
    assert "in_formation" not in fields_of("Muster GmbH", "Musterweg 1")


# --- managing directors ----------------------------------------------------------------------------
def test_director_names_are_split_and_titles_stripped():
    found = fields_of("Muster GmbH", "Geschäftsführer: Dr. Max Mustermann, Prof. Dr.-Ing. Erika Musterfrau und Dipl.-Inf. Hans von Beispiel & Jana Klein (CEO)")
    assert found["managing_directors"] == ["Max Mustermann", "Erika Musterfrau", "Hans von Beispiel", "Jana Klein"]


def test_director_variants():
    assert fields_of("Vertreten durch die Geschäftsführerin Dr. med. Anna Arzt")["managing_directors"] == ["Anna Arzt"]
    assert fields_of("Geschäftsführung:", "Dipl.-Ing. Lisa Müller", "Tom Meier", "Registergericht: Amtsgericht Köln")["managing_directors"] == ["Lisa Müller", "Tom Meier"]
    assert fields_of("Vorstand: Dr. Peter Pan (Vorsitzender), Wendy Darling")["managing_directors"] == ["Peter Pan", "Wendy Darling"]
    assert fields_of("Managing Director authorized to represent the company: Dr. Alexander Regnat")["managing_directors"] == ["Alexander Regnat"]
    assert fields_of("Represented by", "The Managing Directors are Dr. Pedro Gomez, Dr. Maria Laparidou, and Dr. Miguel Molina.")["managing_directors"] == ["Pedro Gomez", "Maria Laparidou", "Miguel Molina"]
    assert fields_of("CEO: Jane Roe")["managing_directors"] == ["Jane Roe"]
    assert "managing_directors" not in fields_of("Unser Art Director gestaltet die Seite.", "Verantwortlich: Kim Muster")
    assert "managing_directors" not in fields_of("Geschäftsführer: siehe Handelsregister")


def test_director_name_is_cut_before_an_address_on_the_same_line():
    line = "Emqopter GmbH Gesellschafter-Geschäftsführer: Marvin Bihl, Dr. Nils Gageik (Vorsitz) Otto-Hahn-Straße 7 97080 Würzburg Telefonnummer: +49 931 1"
    assert fields_of(line)["managing_directors"] == ["Marvin Bihl", "Nils Gageik"]


# --- register --------------------------------------------------------------------------------------
@pytest.mark.parametrize("lines, expected", [
    (["Handelsregister: Amtsgericht Berlin (Charlottenburg) HRB 98765 B"], "HRB 98765 B, Amtsgericht Berlin (Charlottenburg)"),
    (["Registergericht: Amtsgericht München", "Registernummer: HRA 123456"], "HRA 123456, Amtsgericht München"),
    (["Amtsgericht Frankfurt am Main, HRB 4711"], "HRB 4711, Amtsgericht Frankfurt am Main"),
    (["Register court: Amtsgericht München (Munich Local Court)", "Register number: HRB 242819"], "HRB 242819, Amtsgericht München (Munich Local Court)"),
    (["Commercial Register: District Court of Munich, HRB 234567"], "HRB 234567, Amtsgericht Munich"),
    (["Registrierungs- und Steuerangaben:Amtsgericht WürzburgHandelsregister HRB 13237UST-ID: DE306821600"], "HRB 13237, Amtsgericht Würzburg"),
    (["Eingetragen im Handelsregister.", "Registernummer: HRB 252715"], "HRB 252715"),
    (["Commercial register Munich", "Commercial register number 249942"], "HRB 249942, Amtsgericht Munich"),
    (["Vereinsregister: VR 1234, Amtsgericht Hamburg"], "VR 1234, Amtsgericht Hamburg"),
])
def test_register_id(lines, expected):
    assert fields_of("Muster GmbH", *lines)["register_id"] == expected


def test_register_number_without_prefix_uses_the_legal_form():
    assert fields_of("Muster GmbH & Co. KG", "Registernummer: 4711")["register_id"] == "HRA 4711"
    assert "register_id" not in fields_of("Muster GmbH", "Telefon: 4711")


# --- e-mail / city -------------------------------------------------------------------------------
def test_only_generic_mailboxes_are_returned():
    assert fields_of("E-Mail: max.mustermann@muster.de", "Kontakt: info@muster.de")["contact_email"] == "info@muster.de"
    assert "contact_email" not in fields_of("E-Mail: max.mustermann@muster.de", "Tel: 030 1234")
    assert fields_of("Mail: presse (at) muster-firma (dot) de")["contact_email"] == "presse@muster-firma.de"
    assert fields_of("hello[at]muster.io")["contact_email"] == "hello@muster.io"
    assert {"info", "kontakt", "contact", "hello", "hallo", "team", "office", "mail", "post", "press", "presse",
            "invest", "founders"} <= GENERIC_MAILBOXES


def test_city_is_parsed_from_the_postal_code_line():
    assert fields_of("Musterstraße 1", "60311 Frankfurt am Main", "Deutschland")["address_city"] == "Frankfurt am Main"
    assert fields_of("Am Klopferspitz 19 a", "82152 Planegg-Martinsried")["address_city"] == "Planegg-Martinsried"
    assert fields_of("D-10115 Berlin, Germany")["address_city"] == "Berlin"
    assert "address_city" not in fields_of("Tel. 030 12345 Telefon")


# --- English imprint (fixture) -------------------------------------------------------------------
def test_english_imprint_fixture():
    result, _ = lookup({SITE: page_from_html("<footer><a href='/legal-notice'>Legal notice</a></footer>"),
                        "https://www.example.org/legal-notice": fixture("imprint_kiutra_legal_notice.html")})
    assert result.fields["legal_form"] == "GmbH"
    assert result.fields["company_name"] == "kiutra GmbH"
    assert result.fields["managing_directors"] == ["Alexander Regnat"]
    assert result.fields["register_id"] == "HRB 242819, Amtsgericht München (Munich Local Court)"
    assert result.fields["contact_email"] == "info@kiutra.com"
    assert result.fields["address_city"] == "Munich"
    assert result.fields["in_formation"] is False


def test_signal_text_is_capped():
    long_page = page_from_text("Impressum", "Muster GmbH", *["Fülltext " * 50] * 100)
    result, _ = lookup({SITE: page_from_text("Start"), "https://www.example.org/impressum": long_page})
    assert len(result.signals[0].evidence) == 8000


def test_missing_imprint_is_memoised_as_a_miss(tmp_path):
    from context.cache import Cache
    cache = Cache(tmp_path / "c.db")
    first = FakeFetch({SITE: page_from_text("Welcome")})
    a = imprint_lookup(SITE, cache=cache, fetch=first)
    assert a.errors == ["impressum: nicht gefunden"] and len(first.calls) == MAX_REQUESTS
    second = FakeFetch({SITE: page_from_text("Welcome"), "https://www.example.org/impressum": fixture("imprint_emqopter_impressum.html")})
    b = imprint_lookup(SITE, cache=cache, fetch=second)
    assert second.calls == [] and b.errors == ["impressum: nicht gefunden"] and b.fields == {}


def test_default_fetch_passes_the_cache_to_context_web(monkeypatch):
    from context import imprint as imprint_module
    seen = []

    def fake_web_fetch(url, site, cache=None):
        seen.append((url, site, cache))
        raise ValueError("Keine HTML-Seite (HTTP 404)")

    monkeypatch.setattr(imprint_module, "_web_fetch", fake_web_fetch)
    marker = NoCache()
    result = imprint_lookup(SITE, cache=marker)
    assert result.errors == ["impressum: nicht gefunden"]
    assert seen and all(cache is marker and site == "example.org" for _, site, cache in seen)
