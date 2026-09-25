# Mapa warunków grzybowych 🍄

Mapa Polski z **indeksem sprzyjających warunków (0–100)** dla 10 popularnych jadalnych grzybów
leśnych: borowik szlachetny, podgrzybek brunatny, kurka, maślak zwyczajny, rydz, kania,
koźlarz babka, koźlarz czerwony, opieńka miodowa i borowik usiatkowany. Tryb „Wszystkie”
pokazuje najwyższy wynik spośród nich. To heurystyczny indeks, a nie prawdopodobieństwo.
Gąski zielonki świadomie nie ma: od 2011 roku nie jest dopuszczona do obrotu po przypadkach zatruć.

Interfejs: ciemna mapa podkładowa w stylu GTA V (OpenFreeMap), wynik jako półprzezroczyste
„plamy” (heatmapa skalibrowana tak, by ciągły las o wyniku S miał kolor S z legendy) albo siatka,
wyszukiwarka miejsc (Photon/OSM), pinezka i szczegóły po pojedynczym kliknięciu, kreskowanie terenów poza lasem
(podwójne kliknięcie tylko przybliża).

## Jak działa model

```
Habitat  = (0.35 host + 0.20 siedlisko + 0.15 gleba + 0.15 wiek drzewostanu
            + 0.05 teren + 0.10 GBIF) × bramka(host, siedlisko)
Weather  = 0.30 opad z opóźnieniem + 0.25 wilgotność gleby + 0.20 temperatura
         + 0.10 temp. gleby + 0.10 wilgotność/VPD + 0.05 bilans wodny
Weather *= 0.4 + 0.6 × mean(opad z opóźnieniem, wilgotność gleby)   # bez wody nie ma owocników
x        = Habitat × (0.30 + 0.70 × Weather) × Sezon × kary(susza, upał, mróz) × korekta GBIF
Score    = 100 × x^2.2      # kalibracja: przeciętne warunki ~30–45, 85+ tylko przy prawie idealnych
```

* Opad liczony jest jako ważona suma z dni t−1…t−35. Każdy gatunek ma własny profil opóźnienia,
  a deszcz z dnia prognozy nie podnosi wyniku od razu.
* Brak danych oznacza UNKNOWN, a nie 0. Obniża **pewność** (confidence), ale nie zeruje wyniku.
* Wszystkie wagi i krzywe są w `backend/app/species/*.py` (gatunki) oraz w `base.py` (model).

## Źródła danych

| Źródło | Użycie |
|---|---|
| BDL (Bank Danych o Lasach), ArcGIS REST `WMS_BDL/MapServer/5` i `/6` | wydzielenia Lasów Państwowych oraz lasów innych własności z planów PUL: gatunek panujący, typ siedliska, wiek |
| Open-Meteo | 40 dni historii + 6 dni prognozy: opad, temperatura, RH, ET0, VPD, wilgotność i temperatura gleby |
| GBIF | obserwacje z Polski: mały prior (nie może dominować wyniku) |
| SoilGrids | pH i skład gleby, tylko w szczegółach klikniętego punktu (API jest wolne) |

Na darmowym Renderze Open-Meteo często zwraca 429, bo Render współdzieli adresy IP.
Wtedy działają dwa zabezpieczenia:
1. backend podaje przeglądarce brakujące punkty pogodowe, a przeglądarka pobiera je z Open-Meteo
   (z własnego IP) i odsyła na `POST /api/v1/weather`; serwer trzyma je w cache dla wszystkich,
2. workflow `weather-grid.yml` co 6 godzin buduje z GitHub Actions krajową siatkę pogody (~30 km)
   i zapisuje ją na gałęzi `weather-data`. Workflow `probe.yml`, uruchamiany ręcznie, sprawdza źródła i wdrożoną aplikację.

Ograniczenie: lasy, których nie ma w żadnej warstwie BDL (część lasów prywatnych bez planu PUL),
nie mają wyniku. Na mapie są czysto ciemnozielone, a każdy przeanalizowany las ma choćby lekkie
zabarwienie, więc „brak danych” nie wygląda jak „słabe warunki”. Tereny poza lasem są delikatnie kreskowane.

## Uruchomienie lokalne

```bash
cd backend && pip install -r requirements-dev.txt && python -m pytest -q
uvicorn app.main:app --reload            # API na :8000
cd ../frontend && npm ci && npm run dev  # frontend na :5173 (proxy /api -> :8000)
```

## Deploy

Push do `main` uruchamia GitHub Actions (testy backendu i build frontendu).
Render (Blueprint `render.yaml`, jedna darmowa usługa Docker) wdraża kod po zielonych checkach.
Adresy źródeł można nadpisać zmiennymi `BDL_LAYER_URL`, `OPEN_METEO_URL`, `GBIF_URL` i `SOILGRIDS_URL`.
