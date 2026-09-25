# Mapa warunków grzybowych 🍄

Mapa Polski z **indeksem sprzyjających warunków (0–100)** dla czterech jadalnych grzybów:
borowik szlachetny, podgrzybek brunatny, maślak zwyczajny i mleczaj rydz. Tryb „Wszystkie”
pokazuje najwyższy wynik spośród nich. To heurystyczny indeks, a nie prawdopodobieństwo.

## Jak działa model

```
Habitat  = (0.35 host + 0.20 siedlisko + 0.15 gleba + 0.15 wiek drzewostanu
            + 0.05 teren + 0.10 GBIF) × bramka(host, siedlisko)
Weather  = 0.30 opad z opóźnieniem + 0.25 wilgotność gleby + 0.20 temperatura
         + 0.10 temp. gleby + 0.10 wilgotność/VPD + 0.05 bilans wodny
Score    = Habitat × (0.30 + 0.70 × Weather) × Sezon × kary(susza, upał, mróz) × korekta GBIF
```

* Opad liczony jest jako ważona suma z dni t−1…t−35. Każdy gatunek ma własny profil opóźnienia,
  a deszcz z dnia prognozy nie podnosi wyniku od razu.
* Brak danych oznacza UNKNOWN, a nie 0. Obniża **pewność** (confidence), ale nie zeruje wyniku.
* Wszystkie wagi i krzywe są w `backend/app/species/*.py` (gatunki) oraz w `base.py` (model).

## Źródła danych

| Źródło | Użycie |
|---|---|
| BDL (Bank Danych o Lasach), ArcGIS REST `WMS_BDL/MapServer/5` | wydzielenia Lasów Państwowych: gatunek panujący, typ siedliska, wiek |
| Open-Meteo | 40 dni historii + 6 dni prognozy: opad, temperatura, RH, ET0, VPD, wilgotność i temperatura gleby |
| GBIF | obserwacje z Polski: mały prior (nie może dominować wyniku) |
| SoilGrids | pH i skład gleby, tylko w szczegółach klikniętego punktu (API jest wolne) |

Ograniczenie: BDL udostępnia szczegółowe dane drzewostanu dla lasów państwowych.
Lasy prywatne nie są liczone, więc aplikacja nie pokazuje tam wyniku.

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
