"""Pure categorisation: description text in, category out. No I/O."""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

# --- CATEGORIES, RULES, VIPPS_RE moved verbatim from the original
# --- standalone import script (commit d0f2b9a, lines 58-156). Do not retune.

# (name, kind). Order here is only for readability.
CATEGORIES = [
    ("Salary", "income"), ("Employer reimbursement", "income"),
    ("Internal transfer", "transfer"), ("Credit card payment", "transfer"),
    ("Groceries", "expense"), ("Convenience & kiosk", "expense"),
    ("Cafe & bakery", "expense"), ("Restaurants & takeaway", "expense"),
    ("Bars & nightlife", "expense"), ("Public transport", "expense"),
    ("Taxi & ride-hailing", "expense"), ("Fuel & EV charging", "expense"),
    ("Clothing & shoes", "expense"), ("Sports & outdoor", "expense"),
    ("Home & furniture", "expense"), ("Flowers & plants", "expense"),
    ("Personal care", "expense"), ("Health - dental", "expense"),
    ("Health - pharmacy", "expense"), ("Health - doctor", "expense"),
    ("Utilities - electricity", "expense"), ("Insurance", "expense"),
    ("Gym & fitness", "expense"), ("Subscriptions", "expense"),
    ("Memberships", "expense"), ("Entertainment", "expense"),
    ("Accommodation", "expense"), ("Books", "expense"), ("Gifts", "expense"),
    ("Mortgage & loan", "expense"), ("Student loan", "expense"),
    ("Mortgage - interest", "expense"), ("Mortgage - fees", "expense"),
    ("Mortgage - principal", "transfer"), ("Employer loan repayment", "transfer"),
    ("Vipps P2P - unspecified", "expense"), ("Uncategorised", "expense"),
]

# (regex, category, needs_review). First match wins, so order matters:
# transfers and memo-bearing Vipps rows must be tested before generic merchants.
RULES = [
    # --- internal transfers (decision: excluded from income/spending) --------
    (r"^innbetaling$",                      "Credit card payment", 0),
    (r"til\s*:\s*99900011122",              "Credit card payment", 0),
    (r"overf.ring mellom egne konti",       "Internal transfer", 0),
    (r"ukespenger",                         "Internal transfer", 0),
    (r"mobil overf.ring",                   "Internal transfer", 0),
    # --- income --------------------------------------------------------------
    (r"^l.nn\b",                            "Salary", 0),
    (r"giro.*nordvest",                     "Employer reimbursement", 1),
    (r"nordvest as mobil betaling",         "Employer loan repayment", 0),
    # --- Vipps P2P, categorised by memo (decision: memo drives category) -----
    (r"stol fra jysk",                      "Home & furniture", 0),
    (r"\bspotify\b.*aalborg",               "Subscriptions", 0),
    (r"gave til mamma",                     "Gifts", 0),
    (r"humoretaten",                        "Entertainment", 0),
    (r"\bkino(tpp|ref|\b)",                  "Entertainment", 0),
    (r"\blading(tpp|ref|\b)",              "Fuel & EV charging", 0),
    (r"\bbok(tpp|ref)",                     "Books", 0),
    (r"\blatte(tpp|ref)",                   "Cafe & bakery", 0),
    (r"\bis(tpp|ref)",                      "Cafe & bakery", 0),
    (r"mat og snacks",                      "Groceries", 0),
    (r"\bmat(tpp|ref)",                     "Groceries", 0),
    # --- recurring bills & fixed costs ---------------------------------------
    (r"fjordkraft",                         "Utilities - electricity", 0),
    (r"gjensidige",                         "Insurance", 0),
    (r"\bsats\b",                           "Gym & fitness", 0),
    (r"baneleie|squash",                    "Sports & outdoor", 0),
    (r"spotify",                            "Subscriptions", 0),
    (r"morgenbladet",                       "Subscriptions", 0),
    (r"dnt-den norske|den norske t",        "Memberships", 0),
    (r"coop no medlem",                     "Memberships", 0),
    (r"statens l.nekasse",                  "Student loan", 0),
    (r"^l.n\b|avdrag",                      "Mortgage & loan", 1),
    # --- groceries -----------------------------------------------------------
    (r"\brema\b|rema 1000",                 "Groceries", 0),
    (r"\bmeny\b",                           "Groceries", 0),
    (r"\bkiwi\b",                           "Groceries", 0),
    (r"\bextra\b",                          "Groceries", 0),
    (r"\bspar\b",                           "Groceries", 0),
    (r"joker",                              "Groceries", 0),
    # --- eating out ----------------------------------------------------------
    (r"narvesen|7-eleven|deli de luca",     "Convenience & kiosk", 0),
    # `gr.d` here matched any "gr<any>d": it caught "Porsgr Dato" in a
    # Circle K line, booking a fuel purchase as a cafe visit -- and it
    # is tested before the `circle k` rule, so first-match-wins made the
    # fuel rule unreachable for that row. Anchored to the merchant name.
    (r"proud mary|baker no|\bkb37\b|\bgr[øo]d\b", "Cafe & bakery", 0),
    (r"dominos|burger king|bastard burger", "Restaurants & takeaway", 0),
    (r"\bmcd\b|kebab|fly chicken|sumo",     "Restaurants & takeaway", 0),
    (r"veikroa|toke brygge",                "Restaurants & takeaway", 0),
    (r"kontroll_datter|^tilt\b|\btilt\s",   "Bars & nightlife", 0),
    (r"haugen",                             "Bars & nightlife", 0),
    # --- transport -----------------------------------------------------------
    (r"bolt\.eu",                           "Taxi & ride-hailing", 0),
    (r"vygruppen|vy app|^tog ga|\btog ga",  "Public transport", 0),
    (r"uno-x|mer norway",                   "Fuel & EV charging", 0),
    (r"ladestasjon",                         "Fuel & EV charging", 0),
    (r"circle k",                           "Fuel & EV charging", 0),
    # --- health --------------------------------------------------------------
    (r"tannklinikk",                        "Health - dental", 0),
    (r"apotek",                             "Health - pharmacy", 0),
    (r"\blege\b",                           "Health - doctor", 0),
    # --- shopping ------------------------------------------------------------
    (r"\bjysk\b|hoome|\bkid\b",             "Home & furniture", 0),
    (r"euro sko|boys storo|dios house",     "Clothing & shoes", 0),
    (r"volt 285",                           "Clothing & shoes", 0),
    (r"sport outlet",                       "Sports & outdoor", 0),
    (r"plantehallen|blomsterpiken",         "Flowers & plants", 0),
    (r"normal oslo|kondomeriet",            "Personal care", 0),
    # --- trips ---------------------------------------------------------------
    (r"leirvassbu|gjendebu",                "Accommodation", 0),
    # --- merchants confirmed by the account holder ---------------------------
    (r"all in one|hasle torg",              "Groceries", 0),
    # --- still unidentified: flagged so they surface in v_needs_review -------
    (r"maulund",                            "Uncategorised", 1),
    (r"ecom capital",                       "Uncategorised", 1),
]

VIPPS_RE = re.compile(r"vipps|tpp:|overf.ring", re.I)

# Category name -> the Norwegian label the UI shows.
#
# The category names above are identifiers: they are what `RULES`,
# `corrections.py` and `TREATMENTS` key on, and renaming one would silently
# detach every rule that names it. The interface is Norwegian, so the two
# cannot be the same string. This mapping lives here, beside the names it
# translates, rather than in the client -- a client-side table drifts the
# moment a category is added on this side, and drifts silently, showing an
# English name in a Norwegian screen. `GET /api/categories` serves it, and a
# test asserts every category has one.
LABELS: dict[str, str] = {
    "Salary":                   "Lønn",
    "Employer reimbursement":   "Utleggsrefusjon",
    "Internal transfer":        "Egen overføring",
    "Credit card payment":      "Kortbetaling",
    "Groceries":                "Dagligvarer",
    "Convenience & kiosk":      "Kiosk",
    "Cafe & bakery":            "Kafé & bakeri",
    "Restaurants & takeaway":   "Restaurant & takeaway",
    "Bars & nightlife":         "Bar & uteliv",
    "Public transport":         "Kollektivtransport",
    "Taxi & ride-hailing":      "Taxi",
    "Fuel & EV charging":       "Drivstoff & lading",
    "Clothing & shoes":         "Klær & sko",
    "Sports & outdoor":         "Sport & friluft",
    "Home & furniture":         "Hjem & møbler",
    "Flowers & plants":         "Blomster & planter",
    "Personal care":            "Personlig pleie",
    "Health - dental":          "Helse – tannlege",
    "Health - pharmacy":        "Helse – apotek",
    "Health - doctor":          "Helse – lege",
    "Utilities - electricity":  "Strøm",
    "Insurance":                "Forsikring",
    "Gym & fitness":            "Trening",
    "Subscriptions":            "Abonnementer",
    "Memberships":              "Medlemskap",
    "Entertainment":            "Underholdning",
    "Accommodation":            "Overnatting",
    "Books":                    "Bøker",
    "Gifts":                    "Gaver",
    "Mortgage & loan":          "Lån & avdrag",
    "Student loan":             "Studielån",
    "Mortgage - interest":      "Boliglån – renter",
    "Mortgage - fees":          "Boliglån – gebyr",
    "Mortgage - principal":     "Boliglån – avdrag",
    "Employer loan repayment":  "Lån til arbeidsgiver",
    "Vipps P2P - unspecified":  "Vipps – uten memo",
    "Uncategorised":            "Ukategorisert",
}


# Category name -> (budget_treatment, cash_treatment), for categories that
# deviate from the schema defaults ("variable", "settlement"). Anything not
# listed here keeps those defaults. Fed to store.seed_reference_data.
TREATMENTS: dict[str, tuple[str, str]] = {
    # Recurring commitments: excluded from the weekly envelope.
    "Mortgage - interest":     ("fixed", "settlement"),
    "Mortgage - fees":         ("fixed", "settlement"),
    "Student loan":            ("fixed", "settlement"),
    "Utilities - electricity": ("fixed", "settlement"),
    "Insurance":               ("fixed", "settlement"),
    "Gym & fitness":           ("fixed", "settlement"),
    "Subscriptions":           ("fixed", "settlement"),
    # The catch-all for a loan term whose itemisation `derive` could not
    # parse. Today nothing lands here -- the one loan line splits into
    # interest/principal/fee -- but a future statement wording the split
    # differently would otherwise drop ~13 288 kr straight into one week's
    # variable envelope, on the schema default.
    "Mortgage & loan":         ("fixed", "settlement"),
    # Large one-offs: tracked separately, not against the weekly envelope.
    "Home & furniture":        ("exceptional", "settlement"),
    "Sports & outdoor":        ("exceptional", "settlement"),
    "Memberships":             ("exceptional", "settlement"),
    # Transfers. Cash genuinely leaves and is not spendable:
    "Mortgage - principal":    ("variable", "committed"),
    "Employer loan repayment": ("variable", "committed"),
    # Card payments must NOT reduce the pool -- the card's purchase lines
    # already carry that spending, so subtracting these double-counts.
    "Credit card payment":     ("variable", "settlement"),
    # Own-account movement; the explicit savings target represents saving.
    "Internal transfer":       ("variable", "savings"),
}


@dataclass(frozen=True)
class Verdict:
    category: str
    needs_review: bool


def categorise(description: str,
                learned: Mapping[str, str] | None = None) -> Verdict:
    """Map a statement description to a category.

    `learned` maps a lowercase substring to a category name and wins over the
    built-in rules, so a correction taught once keeps applying.
    """
    low = description.lower()

    for fragment, category in (learned or {}).items():
        if fragment.lower() in low:
            return Verdict(category, False)

    for pattern, category, review in RULES:
        if re.search(pattern, low):
            return Verdict(category, bool(review))

    if VIPPS_RE.search(low):
        return Verdict("Vipps P2P - unspecified", True)
    return Verdict("Uncategorised", True)


def extract_counterparty(description: str) -> str | None:
    m = re.search(r"vipps\*([A-Za-zÆØÅæøå' .-]+?)(?:,|$)", description, re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r"vipps:([A-Za-zÆØÅæøå' .-]+)", description, re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r"\d{6,}\s+([A-ZÆØÅ][A-Za-zÆØÅæøå.-]+(?:\s+[A-ZÆØÅ][A-Za-zÆØÅæøå.-]+){1,3})", description)
    if m:
        return m.group(1).strip()
    return None
