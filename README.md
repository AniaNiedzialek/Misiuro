# Misiuri Bot

Skrypt w Pythonie automatyzujący proces monitorowania wybranej kategorii produktów w sklepie **misiuri.com**, 
dodawania dostępnych produktów do koszyka oraz (opcjonalnie) składania zamówienia.

## Wymagania

- Python 3.8+
- [Playwright](https://playwright.dev/python/)
- Konto w sklepie misiuri.com (login i hasło)
- Zainstalowany `git`
- Plik `.env` z danymi logowania i adresowymi

## Instrukcja uruchomienia

### 1. Sklonuj repozytorium
```bash
git clone https://github.com/AniaNiedzialek/Misiuro
```

### 2. Utwórz i aktywuj wirtualne środowisko

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell):**
```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Zainstaluj zależności
```bash
pip install -r requirements.txt
playwright install
```

### 4. Utwórz plik `.env`
W katalogu głównym projektu utwórz plik `.env` i wprowadź swoje dane:
```env
MISIURI_EMAIL=twoj_email@example.com
MISIURI_PASSWORD=twoje_haslo
FULL_NAME=Imie Nazwisko
STREET=Ulica 1
POSTCODE=00-000
CITY=Miasto
PHONE=123456789
HEADLESS=false
AUTO_PLACE_ORDER=false
POLL_SECONDS=10
```

**Parametry:**
- `HEADLESS=false` – uruchamia przeglądarkę w trybie widocznym (do debugowania)
- `AUTO_PLACE_ORDER=true` – automatyczne składanie zamówienia po dodaniu do koszyka
- `POLL_SECONDS` – czas w sekundach między kolejnymi sprawdzeniami kategorii

### 5. Uruchom skrypt
```bash
python3 misiuri_bot.py
```

## Jak działa skrypt
1. Loguje się do sklepu na podane konto.
2. Przechodzi do wybranej kategorii produktów (np. broszki, kubki).
3. Wyszukuje pierwszy dostępny produkt, który można dodać do koszyka.
4. Dodaje produkt do koszyka.
5. Przechodzi do kasy, uzupełnia dane adresowe.
6. Wybiera metodę płatności "Za pobraniem".
7. Jeśli `AUTO_PLACE_ORDER=true` – składa zamówienie automatycznie.

## Uwaga
- Jeśli produkt jest wyprzedany, skrypt przechodzi do kolejnego.
- Zaleca się testowanie w trybie `HEADLESS=false`, aby widzieć działania w przeglądarce.
