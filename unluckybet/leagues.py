"""Katalog lig dostępnych w darmowych plikach CSV football-data.co.uk."""

from dataclasses import dataclass


@dataclass(frozen=True)
class League:
    code: str
    name: str
    country: str
    source: str  # "main" = mmz4281/<sezon>/<kod>.csv, "extra" = new/<kod>.csv


LEAGUES = [
    # Główne ligi europejskie (pliki sezonowe)
    League("E0", "Premier League", "Anglia", "main"),
    League("E1", "Championship", "Anglia", "main"),
    League("E2", "League One", "Anglia", "main"),
    League("E3", "League Two", "Anglia", "main"),
    League("EC", "National League", "Anglia", "main"),
    League("SC0", "Premiership", "Szkocja", "main"),
    League("SC1", "Championship", "Szkocja", "main"),
    League("SC2", "League One", "Szkocja", "main"),
    League("SC3", "League Two", "Szkocja", "main"),
    League("D1", "Bundesliga", "Niemcy", "main"),
    League("D2", "2. Bundesliga", "Niemcy", "main"),
    League("I1", "Serie A", "Włochy", "main"),
    League("I2", "Serie B", "Włochy", "main"),
    League("SP1", "La Liga", "Hiszpania", "main"),
    League("SP2", "Segunda División", "Hiszpania", "main"),
    League("F1", "Ligue 1", "Francja", "main"),
    League("F2", "Ligue 2", "Francja", "main"),
    League("N1", "Eredivisie", "Holandia", "main"),
    League("B1", "Pro League", "Belgia", "main"),
    League("P1", "Liga Portugal", "Portugalia", "main"),
    League("T1", "Süper Lig", "Turcja", "main"),
    League("G1", "Super League", "Grecja", "main"),
    # Ligi "extra" (jeden plik z całą historią od 2012)
    League("ARG", "Liga Profesional", "Argentyna", "extra"),
    League("AUT", "Bundesliga", "Austria", "extra"),
    League("BRA", "Serie A", "Brazylia", "extra"),
    League("CHN", "Super League", "Chiny", "extra"),
    League("DNK", "Superliga", "Dania", "extra"),
    League("FIN", "Veikkausliiga", "Finlandia", "extra"),
    League("IRL", "Premier Division", "Irlandia", "extra"),
    League("JPN", "J1 League", "Japonia", "extra"),
    League("MEX", "Liga MX", "Meksyk", "extra"),
    League("NOR", "Eliteserien", "Norwegia", "extra"),
    League("POL", "Ekstraklasa", "Polska", "extra"),
    League("ROU", "Liga I", "Rumunia", "extra"),
    League("RUS", "Premier Liga", "Rosja", "extra"),
    League("SWE", "Allsvenskan", "Szwecja", "extra"),
    League("SWZ", "Super League", "Szwajcaria", "extra"),
    League("USA", "MLS", "USA", "extra"),
]

BY_CODE = {lg.code: lg for lg in LEAGUES}

# Kraj w pliku new_league_fixtures.csv -> kod ligi
EXTRA_COUNTRY_TO_CODE = {
    "Argentina": "ARG", "Austria": "AUT", "Brazil": "BRA", "China": "CHN",
    "Denmark": "DNK", "Finland": "FIN", "Ireland": "IRL", "Japan": "JPN",
    "Mexico": "MEX", "Norway": "NOR", "Poland": "POL", "Romania": "ROU",
    "Russia": "RUS", "Sweden": "SWE", "Switzerland": "SWZ", "USA": "USA",
}
