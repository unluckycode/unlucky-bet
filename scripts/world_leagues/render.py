"""Render analyze.py output into a Polish Markdown report and an integration JSON.

Usage: python3 scripts/world_leagues/render.py results.json ligi-swiat.md ligi-swiat.json
"""
import json
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

WAW = ZoneInfo("Europe/Warsaw")
FIT, PARTIAL = 0.10, 0.20
GEN = None

COUNTRY_PL = {
    "ALB": "Albania", "ALG": "Algieria", "ARG": "Argentyna", "ARM": "Armenia", "AUS": "Australia",
    "AUT": "Austria", "AZE": "Azerbejdżan", "BAN": "Bangladesz", "BLR": "Białoruś", "BEL": "Belgia",
    "BOL": "Boliwia", "BIH": "Bośnia i Hercegowina", "BRA": "Brazylia", "BUL": "Bułgaria",
    "CAN": "Kanada", "CHI": "Chile", "CHN": "Chiny", "COL": "Kolumbia", "CRC": "Kostaryka",
    "CRO": "Chorwacja", "CYP": "Cypr", "CZE": "Czechy", "DEN": "Dania", "ECU": "Ekwador",
    "EGY": "Egipt", "SLV": "Salwador", "ENG": "Anglia", "EST": "Estonia", "FRO": "Wyspy Owcze",
    "FIN": "Finlandia", "FRA": "Francja", "GEO": "Gruzja", "GER": "Niemcy", "GHA": "Ghana",
    "GRE": "Grecja", "GUA": "Gwatemala", "HON": "Honduras", "HUN": "Węgry", "ISL": "Islandia",
    "IND": "Indie", "IDN": "Indonezja", "IRN": "Iran", "IRQ": "Irak", "IRL": "Irlandia",
    "ISR": "Izrael", "ITA": "Włochy", "JPN": "Japonia", "KAZ": "Kazachstan", "KUW": "Kuwejt",
    "LVA": "Łotwa", "LTU": "Litwa", "LUX": "Luksemburg", "MKD": "Macedonia Płn.", "MAS": "Malezja",
    "MEX": "Meksyk", "MDA": "Mołdawia", "MNE": "Czarnogóra", "MAR": "Maroko", "NED": "Holandia",
    "NZL": "Nowa Zelandia", "NGA": "Nigeria", "NIR": "Irlandia Płn.", "NOR": "Norwegia",
    "PAN": "Panama", "PAR": "Paragwaj", "PER": "Peru", "POL": "Polska", "POR": "Portugalia",
    "QAT": "Katar", "ROU": "Rumunia", "RUS": "Rosja", "KSA": "Arabia Saudyjska", "SCO": "Szkocja",
    "SRB": "Serbia", "SIN": "Singapur", "SVK": "Słowacja", "SVN": "Słowenia", "RSA": "RPA",
    "KOR": "Korea Płd.", "ESP": "Hiszpania", "SWE": "Szwecja", "SUI": "Szwajcaria",
    "TAN": "Tanzania", "THA": "Tajlandia", "TUN": "Tunezja", "TUR": "Turcja", "UKR": "Ukraina",
    "UAE": "ZEA", "USA": "USA", "URU": "Urugwaj", "UZB": "Uzbekistan", "VEN": "Wenezuela",
    "VIE": "Wietnam", "WAL": "Walia",
}
CONTINENT = {
    **dict.fromkeys("ALB ARM AUT AZE BLR BEL BIH BUL CRO CYP CZE DEN ENG EST FRO FIN FRA GEO GER GRE HUN "
                    "ISL IRL ISR ITA KAZ LVA LTU LUX MKD MDA MNE NED NIR NOR POL POR ROU RUS SCO SRB SVK "
                    "SVN ESP SWE SUI TUR UKR WAL".split(), "Europa"),
    **dict.fromkeys("ARG BOL BRA CHI COL ECU PAR PER URU VEN".split(), "Ameryka Płd."),
    **dict.fromkeys("CAN CRC SLV GUA HON MEX PAN USA".split(), "Ameryka Płn./Śr."),
    **dict.fromkeys("BAN CHN IND IDN IRN IRQ JPN KUW MAS QAT KSA SIN KOR THA UAE UZB VIE".split(), "Azja"),
    **dict.fromkeys("ALG EGY GHA MAR NGA RSA TAN TUN".split(), "Afryka"),
    **dict.fromkeys("AUS NZL".split(), "Oceania"),
}


def pct(x):
    return "–" if x is None else f"{round(x * 100)}%"


def dec(x):
    return f"{x * 100:.1f}%".replace(".", ",")


def waw(iso, fmt="%d.%m %H:%M"):
    return datetime.fromisoformat(iso).astimezone(WAW).strftime(fmt)


def status(r):
    if r["active"]:
        return "trwa"
    if r["next_match"]:
        return "przerwa (wznowienie " + waw(r["next_match"]["utc"], "%d.%m") + ")"
    return "koniec sezonu / brak terminarza"


def label(r):
    return f"{COUNTRY_PL.get(r['ccode'], r['country'])} – {r['name']}"


def next_str(r):
    n = r["next_match"]
    if not n:
        return "–"
    live = " (w trakcie)" if datetime.fromisoformat(n["utc"]) <= GEN else ""
    return f"{waw(n['utc'])} {n['home']} – {n['away']}{live}"


def main(src, md_out, json_out):
    d = json.load(open(src))
    global GEN
    GEN = datetime.fromisoformat(d["generated_utc"])
    gen = GEN.astimezone(WAW)
    L = d["leagues"]
    for r in L:
        r["fit"] = ("pasuje" if r["overlap"] <= FIT else "częściowo" if r["overlap"] <= PARTIAL else "nie")
    order = {"pasuje": 0, "częściowo": 1, "nie": 2}
    L.sort(key=lambda r: (order[r["fit"]], not r["active"], r["overlap"], -r["streak_now"]))

    fit = [r for r in L if r["fit"] == "pasuje"]
    part = [r for r in L if r["fit"] == "częściowo"]
    rest = [r for r in L if r["fit"] == "nie"]
    conts = {}
    for r in L:
        conts.setdefault(CONTINENT.get(r["ccode"], "inne"), set()).add(r["ccode"])

    o = []
    o.append("# Ligi świata – seria meczów bez remisu (cała liga, po kolei)\n")
    o.append(f"**Stan danych:** {gen:%d.%m.%Y, %H:%M} (czas polski), źródło: FotMob (publiczne JSON-y strony "
             f"fotmob.com, bez klucza). Wyniki aktualizowane na żywo – mecze z 18.10 wieczorem w Ameryce "
             f"mogły się jeszcze nie skończyć.\n")
    o.append(f"**Przeanalizowano {len(L)} lig z {sum(len(v) for v in conts.values())} krajów** "
             f"({', '.join(f'{k}: {len(v)}' for k, v in sorted(conts.items()))}). "
             f"To całe pokrycie FotMob dla lig krajowych mężczyzn (1.–3. poziom, bez pucharów, rezerw, juniorów i kobiet).\n")
    o.append("## Jak liczone\n")
    o.append("- **Okno:** bieżący sezon + poprzedni pełny sezon (dla lig Apertura/Clausura – ostatnie 3–4 rundy półroczne, ok. 2 lat).")
    o.append("- **Ta sama godzina:** odsetek rozegranych meczów, które zaczęły się dokładnie o tej samej godzinie (UTC) co inny mecz tej ligi; "
             "ostatnia kolejka zakończonych sezonów pominięta. Pierwsza wartość – oba sezony, w nawiasie – bieżący sezon.")
    o.append(f"- **Pasuje:** ≤ {round(FIT * 100)}%, **częściowo:** {round(FIT * 100)}–{round(PARTIAL * 100)}%.")
    o.append("- **Seria teraz:** liczba kolejnych meczów całej ligi (po dacie i godzinie) bez remisu od ostatniego remisu do dziś; liczona też przez przerwę między sezonami.")
    o.append("- **Rekord:** najdłuższa seria bez remisu w oknie (2 sezony). **Remisy:** odsetek remisów w oknie.")
    o.append("- **Status:** „trwa” = najbliższy mecz w ciągu 21 dni. Godziny meczów w czasie polskim.\n")

    def table(rows, full=True):
        if full:
            o.append("| # | Liga | Ta sama godzina | Seria teraz | Remisy | Rekord | Ostatni remis | Następny mecz | Pozostało meczów | Status |")
            o.append("|---:|---|---:|---:|---:|---:|---|---|---:|---|")
            for i, r in enumerate(rows, 1):
                ld = waw(r["last_draw_utc"], "%d.%m.%Y") if r["last_draw_utc"] else "–"
                o.append(f"| {i} | **{label(r)}** | {pct(r['overlap'])} ({pct(r['overlap_current'])}) | **{r['streak_now']}** | "
                         f"{dec(r['draw_rate'])} | {r['streak_record']} | {ld} | {next_str(r)} | {r['remaining_in_season']} | {status(r)} |")
        else:
            o.append("| Liga | Ta sama godzina | Seria teraz | Remisy | Rekord | Status |")
            o.append("|---|---:|---:|---:|---:|---|")
            for r in rows:
                o.append(f"| {label(r)} | {pct(r['overlap'])} ({pct(r['overlap_current'])}) | {r['streak_now']} | "
                         f"{dec(r['draw_rate'])} | {r['streak_record']} | {status(r)} |")
        o.append("")

    o.append(f"## Pasują – mecze po kolei (≤ {round(FIT * 100)}% o tej samej godzinie) – {len(fit)} lig\n")
    table(fit)
    o.append(f"## Częściowo ({round(FIT * 100)}–{round(PARTIAL * 100)}%) – {len(part)} lig\n")
    table(part)
    o.append(f"## Nie pasują (> {round(PARTIAL * 100)}%, wiele meczów równolegle) – {len(rest)} lig\n")
    table(rest, full=False)

    o.append("## Źródła danych – porównanie\n")
    o.append("| Źródło | Klucz | Pokrycie | Opóźnienie | Uwagi |")
    o.append("|---|---|---|---|---|")
    o.append("| **FotMob** (`fotmob.com/api/data/...`) – **wybrane** | nie | ~430 rozgrywek, 94 kraje; ~170 lig krajowych mężczyzn | na żywo (minuty) | Pełny terminarz sezonu z godzinami UTC jednym zapytaniem (`leagues?id=&season=`), archiwum sezonów, mecze dnia ze wszystkich lig (`matches?date=`). Nieoficjalne API strony – regulamin FotMob nie zezwala na komercyjny scraping; bez gwarancji stabilności. Używać z cache i umiarkowaną częstotliwością (cały skan ~400 zapytań, ~30 s). |")
    o.append("| ESPN (`site.api.espn.com/apis/site/v2/sports/soccer/<slug>/scoreboard`) | nie | ~200 rozgrywek, mniej niższych lig | na żywo | Dobry zapasowy/kontrolny; część slugów zwraca błędy (np. `pol.1` – 400). Nieoficjalne. |")
    o.append("| Sofascore (`api.sofascore.com`) | nie | największe | na żywo | Z serwera zwraca 403 (ochrona Cloudflare) – nieprzydatne bez przeglądarki. |")
    o.append("| Flashscore | nie | bardzo duże | na żywo | Zaszyfrowany/własny format, aktywnie blokuje scraping. |")
    o.append("| API-Football (api-sports.io) | tak (free 100 zapytań/dzień) | ~1000 lig | na żywo | Darmowy plan ma ograniczony dostęp do bieżących sezonów i limit dzienny – za mało na skan 170 lig codziennie. |")
    o.append("| openfootball (GitHub) | nie | ~kilkadziesiąt lig | dni–tygodnie | Ręcznie aktualizowane, brak godzin dla wielu lig. |")
    o.append("| football-data.co.uk (obecny portal) | nie | 38 lig | kilka dni | Wyniki publikowane z opóźnieniem; w portalu nadal przydatne jako archiwum kursów. |")
    o.append("")
    o.append("Dane maszynowe (ID lig FotMob, statystyki): `internal/ligi-swiat.json`. Skrypty: `scripts/world_leagues/` w repo `unluckycode/unlucky-bet` (gałąź `cursor/world-leagues-research-8afe`).")
    open(md_out, "w").write("\n".join(o) + "\n")

    out = {
        "generated_utc": d["generated_utc"],
        "source": "fotmob",
        "source_endpoints": {
            "league_fixtures": "https://www.fotmob.com/api/data/leagues?id={fotmob_id}&season={season}",
            "day_matches": "https://www.fotmob.com/api/data/matches?date={YYYYMMDD}",
            "all_leagues": "https://www.fotmob.com/api/data/allLeagues",
        },
        "criteria": {"overlap_fit_max": FIT, "overlap_partial_max": PARTIAL, "active_next_match_within_days": 21},
        "leagues": [{
            "key": f"fotmob-{r['id']}",
            "name": r["name"],
            "name_pl": label(r),
            "country": r["country"],
            "country_pl": COUNTRY_PL.get(r["ccode"], r["country"]),
            "ccode": r["ccode"],
            "continent_pl": CONTINENT.get(r["ccode"]),
            "tier_order": r["order"],
            "source_ids": {"fotmob_league_id": r["id"]},
            "current_season": r["current_season"],
            "seasons_analysed": [s["season"] for s in r["seasons"]],
            "fit": r["fit"],
            "overlap": r["overlap"],
            "overlap_current": r["overlap_current"],
            "streak_now": r["streak_now"],
            "streak_record": r["streak_record"],
            "draw_rate": r["draw_rate"],
            "matches_finished": r["matches_finished"],
            "last_match": r["last_match"],
            "last_draw_utc": r["last_draw_utc"],
            "next_match": r["next_match"],
            "remaining_in_season": r["remaining_in_season"],
            "active": r["active"],
        } for r in L],
    }
    json.dump(out, open(json_out, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:4])
