# Wyjaśnienie matematyczne strategii „remis po serii bez remisu” + martingale

*Dane: football-data.co.uk, 38 lig, 130 948 meczów (główne ligi europejskie od sezonu 2017/18, pozostałe od 2013). Wyniki do 12–16 października 2026, pobrane 18 października 2026. Liczby w tabelach na górze strony portalu są przeliczane na żywo po każdym odświeżeniu danych.*

> **W skrócie:** seria meczów bez remisu **nie zwiększa** w praktyce szansy na remis w następnym meczu. Podwajanie stawki (martingale) nie zmienia wartości oczekiwanej – zamienia wiele drobnych wygranych na rzadkie, ale bardzo duże straty. Przy kursach rynkowych i polskim podatku 12% od stawki strategia ma **ujemną wartość oczekiwaną**. Portal pomaga ją kontrolować i mierzyć, ale **nie jest sposobem na pewny zysk**.

## 1. Strategia w skrócie

1. Wybieramy ligę, w której mecze grane są po kolei (rzadko o tej samej godzinie).
2. Liczymy mecze bez remisu w kolejności chronologicznej. Gdy seria osiągnie próg **X** (np. 5), stawiamy na remis w następnym meczu stawkę bazową **b** (np. 10 zł).
3. Przegrana → kolejny mecz, stawka × **m** (zwykle m = 2). Remis → wygrana, wracamy do stawki bazowej i czekamy na nową serię.
4. Bezpiecznik: maksymalna liczba kroków **n** (np. 8) albo limit kapitału (bankroll).

Oznaczenia: **p** – prawdopodobieństwo remisu (w danych ok. 26%, w zależności od ligi 23,5–32%), **q = 1 − p**, **k** – kurs na remis, **t** – podatek od stawki (w Polsce 12%), **k′ = k·(1 − t)** – kurs „efektywny” po podatku.

## 2. Niezależność meczów i błąd hazardzisty

Każdy mecz to inne drużyny, inna forma, inne okoliczności. Wynik meczu Legia – Lech nie „wie”, że pięć poprzednich meczów innych drużyn nie zakończyło się remisem. Jeśli mecze są (w przybliżeniu) niezależne, to:

**P(remis | seria bez remisu ≥ X) = P(remis) = p**

Przekonanie, że „remis musi w końcu paść, więc teraz jest bardziej prawdopodobny”, to klasyczny **błąd hazardzisty** (*gambler's fallacy*). Remis w końcu padnie – ale nie dlatego, że seria „nabija” prawdopodobieństwo, tylko dlatego, że p > 0. Długie serie zdarzają się regularnie: przy p = 26% seria 10 meczów bez remisu ma prawdopodobieństwo 0,74¹⁰ ≈ 4,9%, a w lidze z ~300 meczami w sezonie zdarza się kilka razy w sezonie.

### Sprawdzenie na danych

Dla każdego meczu liczymy, jaka seria bez remisu była przed nim (mecze o tej samej godzinie dzielą stan serii), i porównujemy odsetek remisów z bazowym odsetkiem danej ligi.

| Seria przed meczem ≥ X | Mecze | P(remis) | Oczekiwane przy niezależności | Różnica | z |
|---|---:|---:|---:|---:|---:|
| 1 | 96 066 | 26,38% | 26,20% | +0,18 pp | 1,29 |
| 3 | 52 082 | 26,38% | 26,09% | +0,29 pp | 1,48 |
| 5 | 28 269 | 26,27% | 26,00% | +0,27 pp | 1,02 |
| 6 | 20 926 | 26,55% | 25,97% | +0,58 pp | 1,91 |
| 8 | 11 503 | 26,71% | 25,88% | +0,83 pp | 2,04 |
| 9 | 8 409 | 27,05% | 25,85% | +1,20 pp | 2,53 |
| 10 | 6 082 | 27,01% | 25,80% | +1,21 pp | 2,17 |
| 12 | 3 258 | 26,40% | 25,67% | +0,73 pp | 0,95 |

(„Oczekiwane” to średnia bazowych odsetków lig ważona liczbą meczów – ligi z mniejszą liczbą remisów częściej mają długie serie, więc ta wartość spada wraz z X.)

**Wniosek:**

* Odchylenie jest małe: +0,2 do +1,2 punktu procentowego. Testujemy 12 progów naraz, a próbki są zagnieżdżone (mecze z serią ≥ 9 są też w grupie ≥ 8), więc pojedyncze z ≈ 2–2,5 nie jest przekonującym dowodem (po korekcie na wielokrotne testowanie próg to ok. z = 2,9). Dla samych lig „po kolei” (Rumunia, Polska, Belgia, Hiszpania, Rosja) z nie przekracza 1,5.
* Nawet gdyby efekt był prawdziwy i wynosił +1 pp, zmienia p z ok. 26% na 27%. Próg opłacalności to kurs **1/p ≈ 3,70** (bez podatku) albo **1/(0,88·p) ≈ 4,21** (z podatkiem 12%). Średni rynkowy kurs na remis w tych ligach to 3,4–3,9.
* Najważniejszy test: płaski zakład 1 zł na remis w **każdym** meczu po serii ≥ 5 dawał po średnich kursach rynkowych **−6,0%** zwrotu (28 251 zakładów), po serii ≥ 8 **−3,9%** (11 498). Dla porównania na wszystkich meczach: **−7,0%**. Nawet przy najlepszym kursie na rynku w każdym meczu (praktycznie nieosiągalne) wychodzi ok. **0%** – a to przed podatkiem.

Seria minimalnie poprawia wynik, ale nie zmienia znaku: **bukmacher wciąż ma przewagę**.

## 3. Martingale: wzrost stawek

Stawka w kroku n (dla m = 2):

**sₙ = b · 2ⁿ⁻¹ = 10 · 2ⁿ⁻¹**

Łączny koszt n przegranych z rzędu (suma szeregu geometrycznego):

**Sₙ = b · (2ⁿ − 1) = 10 · (2ⁿ − 1)**

Ogólnie dla mnożnika m: Sₙ = b · (mⁿ − 1)/(m − 1).

| Krok n | Stawka | Suma postawionych | P(n porażek z rzędu), p = 26,5% | Zysk netto przy remisie w kroku n (k = 3,5, bez podatku) |
|---:|---:|---:|---:|---:|
| 1 | 10 zł | 10 zł | 73,5% | +25 zł |
| 2 | 20 zł | 30 zł | 54,0% | +40 zł |
| 3 | 40 zł | 70 zł | 39,7% | +70 zł |
| 4 | 80 zł | 150 zł | 29,2% | +130 zł |
| 5 | 160 zł | 310 zł | 21,4% | +250 zł |
| 6 | 320 zł | 630 zł | 15,8% | +490 zł |
| 7 | 640 zł | 1 270 zł | 11,6% | +970 zł |
| 8 | 1 280 zł | 2 550 zł | 8,5% | +1 930 zł |
| 9 | 2 560 zł | 5 110 zł | 6,3% | +3 850 zł |
| 10 | 5 120 zł | 10 230 zł | 4,6% | +7 690 zł |
| 12 | 20 480 zł | 40 950 zł | 2,5% | – |
| 15 | 163 840 zł | 327 670 zł | 1,0% | – |

Stawka rośnie wykładniczo: po 10 przegranych stawiasz 5 120 zł, żeby wygrać „swoje” 10 zł z nawiązką.

## 4. Zysk z cyklu, wymagany kurs i optymalny mnożnik

Zysk netto, gdy remis padnie w kroku n:

**Zₙ = sₙ·(k′ − 1) − Sₙ₋₁**

Dla m = 2: **Zₙ = b · [2ⁿ⁻¹ · (k′ − 2) + 1]**

* Podwajanie odrabia straty, gdy **k′ ≥ 2**, czyli kurs ≥ 2,00 bez podatku lub ≥ 2,27 z podatkiem 12%. Przy kursie 3,0+ podwajanie **odrabia z dużą nadwyżką** – nadwyżka to b·2ⁿ⁻¹·(k′ − 2) i rośnie razem ze stawką. Kapitał ryzykowany jest wtedy niepotrzebnie duży.
* **Optymalny (najmniejszy) mnożnik**, który po każdej wygranej daje stały zysk równy zyskowi z pierwszej stawki, b·(k′ − 1):

  **m\* = k′ / (k′ − 1)**

| Kurs k | m\* bez podatku | m\* z podatkiem 12% | Zysk z cyklu (b = 10 zł) bez / z podatkiem |
|---:|---:|---:|---:|
| 3,0 | 1,500 | 1,610 | 20,00 / 16,40 zł |
| 3,4 | 1,417 | 1,502 | 24,00 / 19,92 zł |
| 3,8 | 1,357 | 1,427 | 28,00 / 23,44 zł |

Przy m ≈ 1,4 i 8 krokach cały cykl kosztuje ok. **344 zł** zamiast **2 550 zł** przy podwajaniu – przy tym samym zysku z wygranej pierwszej stawki. Mniejszy mnożnik **nie poprawia wartości oczekiwanej**, ale wyraźnie zmniejsza wymagany kapitał i rozmiar katastrofy.

## 5. Prawdopodobieństwo k porażek z rzędu

Jeśli mecze są niezależne: **P(k porażek z rzędu) = (1 − p)ᵏ**

| k | p = 25% | p = 26,5% | p = 28% |
|---:|---:|---:|---:|
| 5 | 23,7% | 21,5% | 19,4% |
| 8 | 10,0% | 8,5% | 7,2% |
| 10 | 5,6% | 4,6% | 3,7% |
| 12 | 3,2% | 2,5% | 1,9% |
| 15 | 1,3% | 1,0% | 0,7% |

Uwaga: liczy się seria **od momentu wejścia**, a nie od początku serii. Przy X = 5 i 8 krokach cykl przepada, gdy seria bez remisu dojdzie do 13 – historyczne rekordy w ligach „po kolei” to 20–32 mecze. **W październiku 2026 roku stało się to jednocześnie w dwóch najlepiej pasujących ligach:** w Ekstraklasie seria doszła do 14, a w rumuńskiej Liga I do 17 meczów – cykl startujący przy X = 5 stracił w obu ligach po 2 550 zł.

## 6. Potrzebny bankroll

Aby przetrwać n kroków, trzeba mieć **Sₙ = b·(mⁿ − 1)/(m − 1)**, czyli przy b = 10 zł, m = 2:

* 8 kroków → 2 550 zł (szansa przegrania cyklu ok. 8,5%),
* 10 kroków → 10 230 zł (ok. 4,6%),
* 12 kroków → 40 950 zł (ok. 2,5%).

Każde podwojenie kapitału kupuje tylko **jeden** dodatkowy krok, czyli zmniejsza ryzyko cyklu zaledwie o czynnik q ≈ 0,74.

## 7. Wartość oczekiwana i marża bukmachera

Wartość oczekiwana jednego zakładu za 1 zł: **EV = p·k′ − 1**.

Martingale zmienia jedynie **wielkość** stawek, nie ich jakość, więc dla całego cyklu:

**EV(cykl) = (p·k′ − 1) · E[suma stawek w cyklu]**

Przykład: p = 27%, k = 3,5, b = 10 zł, m = 2, 8 kroków. Oczekiwana suma stawek w cyklu ≈ 427 zł.

* bez podatku: p·k = 0,945 → EV ≈ **−23,5 zł na cykl** (−5,5% od postawionych),
* z podatkiem 12%: p·k′ = 0,832 → EV ≈ **−71,9 zł na cykl** (−16,8%).

**Marża bukmachera.** Kurs „uczciwy” to 1/p. Bukmacher daje mniej – w danych płaski zakład na każdy remis po średnim kursie rynkowym tracił **7%**. Tyle wynosi realna „opłata” za zakład na remis; w Polsce dochodzi do tego **12% podatku od stawki** (stawiasz 10 zł, w grze jest 8,80 zł), a od wygranej powyżej 2 280 zł – 10% podatku od całej wygranej. Razem to ok. **−18% od każdej postawionej złotówki**.

Żeby strategia miała dodatnie EV, trzeba by stale grać po kursie ≥ 1/(p·(1 − t)) ≈ **4,2** przy p = 27% – czyli znacznie powyżej rynku.

## 8. Ryzyko ruiny

Prawdopodobieństwo przegrania przynajmniej jednego pełnego cyklu w C cyklach:

**P(ruina) = 1 − (1 − qⁿ)ᶜ**

| Cykli | 8 kroków | 10 kroków |
|---:|---:|---:|
| 10 | 59% | 38% |
| 20 | 83% | 61% |
| 50 | 99% | 90% |
| 100 | ≈100% | 99% |

Przy X = 5 w jednej lidze wypada ok. **15 cykli na sezon** (w Ekstraklasie 210 cykli w ok. 14 sezonów), więc z bankrollem na 8 kroków przegrany cykl w ciągu sezonu jest bardziej prawdopodobny niż nie (≈ 74%). Jedna porażka (−2 550 zł) zjada zysk z ok. 100 cykli wygranych już w pierwszym kroku (po 25 zł przy kursie 3,5).

## 9. Limity bukmacherów i praktyka

* **Maksymalna stawka / maksymalna wygrana** na zakład bywa niska w mniej popularnych ligach (Rumunia, niższe ligi) – czasem kilkaset–kilka tysięcy złotych. Stawka 5 120 zł w kroku 10 może zostać przycięta.
* **Ograniczanie kont** – bukmacherzy obniżają limity graczom, których uznają za „wymagających”.
* **Kursy się zmieniają** – w backteście używamy średniego kursu rynkowego z pliku źródłowego; realny kurs w chwili zakładu może być niższy.
* **Mecze o tej samej godzinie** – wtedy kilka wyników poznajemy naraz i stawiamy tylko na jeden mecz; to psuje „sekwencyjność”, dlatego wybieramy ligi z małym odsetkiem takich meczów.
* **Grę w Polsce prowadź wyłącznie u bukmacherów z licencją Ministerstwa Finansów.** Hazard uzależnia – w razie potrzeby: Telefon Zaufania 801 889 880.

## 10. Backtest na danych historycznych

Ustawienia: X = 5, b = 10 zł, m = 2, maks. 8 kroków, średni kurs rynkowy, okres jak w danych (Rumunia i Polska od 2013, Belgia i Hiszpania od 2017/18).

| Liga | Cykle | Przegrane cykle | Wynik bez podatku | Wynik z podatkiem 12% | Maks. obsunięcie (z podatkiem) |
|---|---:|---:|---:|---:|---:|
| Rumunia – Liga I | 230 | 13 | +263 zł | −9 515 zł | 10 325 zł |
| Polska – Ekstraklasa | 210 | 14 | +7 333 zł | −5 175 zł | 12 992 zł |
| Belgia – Pro League | 139 | 15 | −5 769 zł | −14 034 zł | 25 591 zł |
| Hiszpania – La Liga | 173 | 15 | −12 593 zł | −19 284 zł | 20 339 zł |

Zmiana samego progu X o 1 potrafi odwrócić wynik z +7 000 zł na −3 000 zł (zakładka „Backtest” → tabela progów). To typowy obraz **szumu**: wynik zależy od tego, czy w danym okresie trafiło się kilka długich serii, a nie od „przewagi”. Przy podatku 12% wszystkie warianty dla tych lig wychodzą na minus.

## 11. Wnioski

1. **Mecze są praktycznie niezależne.** Seria bez remisu nie „ładuje” remisu; ewentualny efekt to ≤ 1 pp, za mało, by pokonać marżę.
2. **Martingale nie tworzy przewagi.** EV cyklu = (p·k′ − 1) × suma stawek – przy ujemnym p·k′ − 1 większe stawki oznaczają większą oczekiwaną stratę.
3. **Częste małe wygrane, rzadkie ogromne straty.** Ok. 92% cykli kończy się zyskiem, ale pozostałe 8% kosztuje ~100 razy więcej.
4. **Jeśli mimo to grasz:** wybierz mnożnik bliski m\* = k′/(k′ − 1) zamiast 2, ustal twardy limit kroków i bankroll, który możesz w całości stracić, szukaj najlepszych kursów i bukmacherów bez podatku (promocje), a wyniki zapisuj w zakładce „Zakłady”.
5. Portal służy do **obserwacji i uczciwego pomiaru** – nie do obiecywania zysku.
