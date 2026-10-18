# Unlucky Bet

Portal (PWA) do obserwacji lig piłkarskich, w których mecze grane są po kolei, i do uczciwego testowania strategii
**„po X meczach bez remisu stawiam na remis, po przegranej podwajam stawkę”** (martingale).

> ⚠️ To narzędzie analityczne, nie maszynka do zarabiania. Dane pokazują, że seria bez remisu praktycznie nie zwiększa
> szansy na remis, a martingale nie daje przewagi nad bukmacherem – szczegóły w zakładce **Matematyka**
> (`docs/wyjasnienie-matematyczne.md`). Graj tylko u legalnych bukmacherów i tylko za pieniądze, które możesz stracić.

## Co potrafi

- **Ligi – badanie:** 38 lig z darmowych danych [football-data.co.uk](https://www.football-data.co.uk/) (bez klucza API).
  Dla każdej ligi: odsetek meczów granych o tej samej godzinie (czy liga jest „po kolei”), bieżąca seria bez remisu,
  historyczny odsetek remisów, najdłuższa seria, średni kurs na remis, następny mecz.
- **Pulpit:** obserwowane ligi, pasek postępu serii do progu X, alerty, sugerowana stawka i następny mecz.
- **Strategia dla ligi:** próg X, stawka bazowa, mnożnik, limit kroków, bankroll, rodzaj kursu, podatek od stawki (12%),
  aktywna/nieaktywna. Aktywna strategia jest śledzona „na żywo” od daty startu na prawdziwych wynikach
  (krok martingale, następna stawka, strata w cyklu, historia zysków/strat).
- **Backtest:** symulacja na danych historycznych z prawdziwymi kursami, wykres salda, tabela wyników dla X = 1…12,
  lista przegranych cykli.
- **Zakłady:** dziennik własnych zakładów z automatycznym rozliczaniem po pojawieniu się wyniku.
- **Matematyka:** wyjaśnienie (błąd hazardzisty, wzrost stawek, wymagany kurs, optymalny mnożnik, EV, marża,
  ryzyko ruiny, limity), test niezależności na danych i kalkulator martingale.
- **PWA:** instalacja na telefonie, działanie offline (ostatnio pobrane dane), powiadomienia push.
- **Hasło** do portalu (zmienna `APP_PASSWORD`).

## Uruchomienie lokalne

Wymagany Python 3.11+.

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m unluckybet refresh       # pierwsze pobranie danych: ok. 3–6 min
python -m unluckybet serve         # http://127.0.0.1:5000
```

Lokalnie dane trafiają do SQLite (`data/unluckybet.db`). Inne polecenia:

| Polecenie | Opis |
|---|---|
| `python -m unluckybet summary` | podsumowanie lig w terminalu |
| `python -m unluckybet refresh --full` | pobierz wszystkie sezony od nowa |
| `python -m unluckybet notify` | sprawdź alerty i wyślij powiadomienia push |
| `python -m unluckybet vapid` | wygeneruj klucze do powiadomień push |
| `pip install -r requirements-dev.txt && python -m pytest` | testy |
| `python tools/make_icons.py` | odtwórz ikony aplikacji (wymaga `pip install pillow`) |

## Zmienne środowiskowe

| Zmienna | Wymagana | Opis |
|---|---|---|
| `DATABASE_URL` | na hostingu – tak | PostgreSQL, np. z Neon: `postgresql://...`. Bez niej używany jest lokalny SQLite. |
| `APP_PASSWORD` | na hostingu – tak | Hasło do portalu. Bez niej portal jest otwarty (tylko lokalnie!). |
| `SECRET_KEY` | zalecana | Klucz do podpisywania sesji (Render generuje go sam). |
| `CRON_TOKEN` | zalecana | Token do adresu `/api/cron?token=...` (zewnętrzny pinger). Render generuje go sam. |
| `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT` | nie | Powiadomienia push. Generuje je `python -m unluckybet vapid`. |
| `REFRESH_INTERVAL_MIN` | nie | Co ile minut odświeżać dane (domyślnie 60). |
| `UNLUCKYBET_SEASONS` | nie | Ile sezonów głównych lig pobierać (domyślnie 10). |

## Publikacja w internecie za darmo (Render + Neon) – krok po kroku

Portal działa na darmowym planie [Render](https://render.com), a dane trzyma w darmowej bazie
[Neon](https://neon.tech) (PostgreSQL). Baza musi być zewnętrzna, bo darmowy Render kasuje dysk przy każdym
wdrożeniu i restarcie – plik SQLite by zniknął.

### Krok 1. Baza danych w Neon (ok. 5 min)

1. Wejdź na <https://neon.tech> → **Sign up** (najprościej „Continue with GitHub” lub Google).
2. Utwórz projekt: **Create project** → nazwa np. `unlucky-bet`, region **AWS US East 2 (Ohio)** → **Create**.
   Region bazy powinien zgadzać się z regionem usługi w `render.yaml` (`region: ohio`). Jeśli wybierzesz inny
   region Neon (np. Frankfurt), zmień też `region` w `render.yaml` (np. na `frankfurt`).
3. Na pulpicie projektu kliknij **Connect** i skopiuj **Connection string** – wygląda tak:
   `postgresql://uzytkownik:haslo@ep-xxx.eu-central-1.aws.neon.tech/neondb?sslmode=require`.
   Zachowaj go na chwilę (np. w notatniku) – to Twój `DATABASE_URL`.

### Krok 2. Klucze do powiadomień (opcjonalnie, ok. 2 min)

Jeśli chcesz powiadomienia push na telefon, wygeneruj klucze – na swoim komputerze w folderze projektu:

```bash
pip install -r requirements.txt
python -m unluckybet vapid
```

Skopiuj trzy wypisane linie (`VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT` – w ostatniej wpisz swój e-mail).
Klucz prywatny traktuj jak hasło. Ten krok można pominąć i dodać klucze później.

### Krok 3. Usługa w Render (ok. 10 min)

1. Wejdź na <https://render.com> → **Get Started** → zaloguj się przez **GitHub** i zezwól Renderowi na dostęp
   do repozytorium `unlucky-bet`.
2. W panelu Render kliknij **New +** → **Blueprint**.
3. Wybierz repozytorium **unluckycode/unlucky-bet** → **Connect**. Render odczyta plik `render.yaml`
   (usługa `unlucky-bet`, plan **Free**).
4. Render poprosi o wartości zmiennych oznaczonych jako do uzupełnienia:
   - `DATABASE_URL` – wklej connection string z Neon (krok 1),
   - `APP_PASSWORD` – wymyśl hasło do portalu,
   - `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT` – z kroku 2 (albo zostaw puste).
   `SECRET_KEY` i `CRON_TOKEN` Render wygeneruje sam.
5. Kliknij **Apply** / **Deploy Blueprint**. Pierwsze wdrożenie trwa kilka minut.
6. Po zakończeniu w usłudze **unlucky-bet** zobaczysz adres, np. `https://unlucky-bet.onrender.com`. Otwórz go,
   wpisz hasło. Za pierwszym razem portal sam pobierze dane (3–6 min) – strona odświeży się automatycznie.

Zmiana zmiennych później: Render → usługa **unlucky-bet** → **Environment** → edytuj → **Save Changes**
(usługa uruchomi się ponownie). Każdy `git push` do gałęzi `main` wdraża nową wersję automatycznie.

> **Uwaga – darmowy Render usypia usługę** po ok. 15 minutach bez ruchu. Pierwsze wejście po przerwie trwa
> 30–60 sekund (budzenie). Uśpiona usługa nie sprawdza wyników i nie wysyła powiadomień – dlatego warto ustawić
> pinger z kroku 4. Darmowy limit Rendera (750 godzin/miesiąc) wystarcza na jedną usługę działającą cały czas.

### Krok 4. Automatyczne sprawdzanie wyników – pinger cron-job.org (ok. 5 min)

Zadania cykliczne Render (Cron Jobs) są płatne, więc używamy darmowego zewnętrznego pingera, który co kilkanaście
minut wywołuje adres `/api/cron`. To budzi usługę, odświeża wyniki (najwyżej raz na `REFRESH_INTERVAL_MIN` minut)
i wysyła powiadomienia.

1. Skopiuj token: Render → **unlucky-bet** → **Environment** → `CRON_TOKEN` → ikona oka/kopiowania.
2. Wejdź na <https://cron-job.org> → **Sign up** (darmowe konto) → potwierdź e-mail.
3. **Create cronjob**:
   - **Title:** `unlucky-bet`,
   - **URL:** `https://TWOJ-ADRES.onrender.com/api/cron?token=TWOJ_CRON_TOKEN`,
   - **Execution schedule:** *Every 10 minutes* (co 10 minut – usługa nie zdąży usnąć),
   - w **Advanced** ustaw **Timeout** na maksimum (budzenie może trwać do minuty – pojedynczy błąd „timeout”
     po uśpieniu usługi jest niegroźny, następne wywołanie już przejdzie).
4. **Create**. W historii wywołań powinien pojawić się status `200` lub `202`.

Alternatywa: w repozytorium jest workflow `.github/workflows/cron-ping.yml` (co 30 min). Wystarczy dodać w GitHub →
**Settings → Secrets and variables → Actions** sekrety `APP_URL` (adres z Render) i `CRON_TOKEN`. GitHub potrafi
jednak opóźniać takie zadania, a co 30 min usługa zdąży usnąć – cron-job.org jest pewniejszy.

### Logowanie nie działa – co sprawdzić

1. **Render → unlucky-bet → Logs**. Po każdym starcie aplikacja wypisuje linię (bez ujawniania hasła), np.:
   `INFO unluckybet.auth: [auth] APP_PASSWORD ustawione: 9 znaków (usunięto białe znaki z początku/końca); SECRET_KEY: z env; ciasteczko Secure: True`.
   - `APP_PASSWORD nie jest ustawione` → zmienna nie dotarła do usługi (zła usługa, literówka w nazwie, niezapisane zmiany).
   - Liczba znaków inna niż długość Twojego hasła → w wartości jest coś dodatkowego albo czegoś brakuje.
2. Przy nieudanej próbie w logach pojawia się `Nieudane logowanie: wpisano N znaków, oczekiwano M` – porównaj N i M.
3. **Po zmianie zmiennej** w **Environment** kliknij **Save Changes** (Render sam restartuje usługę) i poczekaj, aż w
   **Events** pojawi się zakończone wdrożenie. Dopiero wtedy nowe hasło działa. Jeśli zmiana nie dotarła:
   **Manual Deploy → Deploy latest commit**.
4. Spacje i znaki nowej linii na początku/końcu oraz cudzysłowy wokół hasła są ignorowane; polskie litery są obsługiwane.
5. Komunikat o **ciasteczku sesji** (a nie „Nieprawidłowe hasło”) oznacza, że przeglądarka blokuje ciasteczka albo strona
   jest otwarta przez `http://` – użyj adresu `https://…onrender.com` i wyłącz blokowanie ciasteczek dla tej strony.

### Inne hostingi

Jest też `Dockerfile` (np. dla Koyeb, Fly.io albo własnego serwera). Ustaw te same zmienne środowiskowe.
Vercel nie jest zalecany – działa w modelu funkcji bez stałego procesu, a portal odświeża dane w tle.

## Instalacja na telefonie

### Android (Chrome)

1. Otwórz adres portalu w **Chrome** i zaloguj się.
2. Menu **⋮** → **Zainstaluj aplikację** (lub **Dodaj do ekranu głównego**). Możesz też użyć przycisku
   **Zainstaluj aplikację** w zakładce **Ustawienia**.
3. Uruchom **Unlucky Bet** z ikony → **Ustawienia** → **Włącz powiadomienia** → zezwól.
4. Kliknij **Wyślij test** – powinno przyjść powiadomienie.

### iPhone / iPad (Safari, iOS 16.4 lub nowszy)

1. Otwórz adres portalu w **Safari** (nie w Chrome – na iOS instalować PWA może tylko Safari) i zaloguj się.
2. Przycisk **Udostępnij** (kwadrat ze strzałką) → **Do ekranu początkowego** → **Dodaj**.
3. **Uruchom aplikację z ikony na ekranie początkowym** – na iPhonie powiadomienia działają tylko w zainstalowanej
   aplikacji, nie w zwykłej karcie Safari. Jeśli trzeba, zaloguj się ponownie.
4. **Ustawienia** → **Włącz powiadomienia** → **Pozwól**. Potem **Wyślij test**.
5. Wymagany jest **iOS 16.4+** (Ustawienia → Ogólne → Uaktualnienia).

Powiadomienia przychodzą, gdy:
- seria bez remisu w obserwowanej lidze osiągnie Twój próg X,
- pojawi się wynik meczu z aktywnej strategii (wygrana / przegrana + następna stawka),
- automatycznie rozliczy się zapisany zakład.

Offline aplikacja pokazuje ostatnio otwarte strony z ostatnio pobranymi danymi.

## Dane i zasady liczenia

- Źródło: [football-data.co.uk](https://www.football-data.co.uk/data.php) – pliki CSV z wynikami, godzinami meczów
  i kursami (średni rynkowy, najlepszy, Bet365) oraz terminarz. Główne ligi: ostatnie 10 sezonów (godziny meczów od 2019/20),
  pozostałe ligi: od 2013 r. Wyniki pojawiają się w źródle z opóźnieniem ok. 1–3 dni.
- Seria bez remisu liczona jest chronologicznie po wszystkich meczach ligi (także na przełomie sezonów).
- „Mecze o tej samej godzinie” – odsetek meczów z ostatnich 3 sezonów, które startowały o tej samej dacie i godzinie co inny
  mecz tej ligi, bez ostatniego tygodnia zakończonych sezonów.
- Strategia: cykl startuje, gdy seria przed meczem ≥ X; trwa do remisu albo limitu kroków; po stop-lossie nowy cykl dopiero
  po kolejnym remisie i nowej serii X. Przy meczach o tej samej godzinie obstawiany jest jeden (pierwszy alfabetycznie).
  Wygrana = stawka × (1 − podatek) × kurs.

## Struktura

```
unluckybet/
  leagues.py    katalog lig
  ingest.py     pobieranie i import CSV
  db.py         SQLite / PostgreSQL
  analysis.py   serie, nakładanie godzin, test niezależności
  strategy.py   silnik martingale (backtest i śledzenie na żywo)
  services.py   odświeżanie w tle, stan strategii
  notify.py     Web Push
  web.py        aplikacja Flask
  templates/, static/   interfejs, service worker, manifest, ikony
docs/wyjasnienie-matematyczne.md
render.yaml, Dockerfile, wsgi.py
```
