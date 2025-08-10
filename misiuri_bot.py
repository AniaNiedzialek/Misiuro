import os, re, json, time
from pathlib import Path
from urllib.parse import urljoin
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PWSTimeout

BASE = "https://misiuri.com"
# CATEGORY_URL="https://misiuri.com/pl/c/Kubki/16"
CATEGORY_URL = "https://misiuri.com/pl/c/Broszki/13"
SEEN_FILE = Path("seen.json")

def accept_cookies_if_any(page):
    try:
        page.locator("button:has-text('Akceptuj')").first.click(timeout=1200)
    except:
        pass

def load_seen():
    if SEEN_FILE.exists():
        try:
            return set(json.loads(SEEN_FILE.read_text()))
        except:
            return set()
    return set()

def save_seen(seen):
    SEEN_FILE.write_text(json.dumps(sorted(list(seen)), ensure_ascii=False, indent=2))

def get_env_bool(name, default=False):
    v = os.getenv(name, str(default)).strip().lower()
    return v in ("1", "true", "yes", "y")

def login(page):
    page.goto(BASE, wait_until="domcontentloaded")
    # klik "Zaloguj się" po tekście zamiast roli+name
    try:
        page.locator("a:has-text('Zaloguj')").first.click(timeout=2000)
    except:
        page.locator("button:has-text('Zaloguj')").first.click(timeout=2000)

    page.wait_for_load_state("domcontentloaded")
    page.get_by_label(re.compile("E-mail|Email", re.I)).fill(os.environ["MISIURI_EMAIL"])
    page.get_by_label(re.compile("Hasło", re.I)).fill(os.environ["MISIURI_PASSWORD"])
    page.locator("button:has-text('Zaloguj')").first.click()
    page.wait_for_load_state("networkidle")


def collect_product_links_on_category(page):
    # Wejdź na kategorię i daj chwilę na doładowanie
    page.goto(CATEGORY_URL, wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except:
        pass

    accept_cookies_if_any(page)

    # 1. Najpierw próbujemy złapać TYLKO broszki
    links = page.locator('a[href*="/pl/p/Broszka/"]').evaluate_all(
        "els => [...new Set(els.map(e => e.href))]"
    )

    # 2. Jeśli nic nie znalazło (np. jeszcze się doczytuje) – lekki scroll i próba jeszcze raz
    if not links:
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(500)
            links = page.locator('a[href*="/pl/p/Broszka/"]').evaluate_all(
                "els => [...new Set(els.map(e => e.href))]"
            )
        except:
            pass

    # 3. Ostateczny filtr bezpieczeństwa (tylko Broszka)
    links = [u for u in links if "/pl/p/Broszka/" in u]

    print(f"[DEBUG] znaleziono linków w Broszkach: {len(links)}")
    return sorted(set(links))


def add_to_cart(page):
    # najpierw cookies/warianty (opcjonalnie – możesz dodać później)
    try:
        page.locator("button:has-text('Akceptuj')").first.click(timeout=800)
    except:
        pass

    # przewiń trochę w dół
    page.evaluate("window.scrollBy(0, 400)")

    selectors = [
        "button:has-text('Dodaj do koszyka')",
        "button:has-text('Do koszyka')",
        "a:has-text('Dodaj do koszyka')",
        "a:has-text('Do koszyka')",
        "button[name='add-to-cart']",
        "#projector_button_basket",
        "button.projector_details__cart-submit",
        "a.add_to_cart_button",
        "[data-action='add-to-cart']",
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible():
                loc.click(timeout=1200)
                return True
        except:
            continue

    # awaryjnie – klik JS
    for sel in selectors:
        try:
            el = page.locator(sel).first
            if el.count() and el.is_visible():
                page.evaluate("(el)=>el.click()", el)
                return True
        except:
            continue
    return False

def go_to_cart_or_checkout(page):
    # do koszyka/do kasy po tekście
    try:
        page.locator("a:has-text('do kasy')").first.click(timeout=1500)
    except:
        try:
            page.locator("a:has-text('koszyk')").first.click(timeout=1500)
        except:
            page.goto(f"{BASE}/koszyk", wait_until="domcontentloaded")

    # "Zamawiam" / "Przejdź do kasy" po tekście
    try:
        page.locator("button:has-text('Zamawiam')").first.click(timeout=1500)
    except:
        try:
            page.locator("button:has-text('Przejdź do kasy')").first.click(timeout=1500)
        except:
            pass


def fill_address_if_needed(page):
    # wypełnij tylko jeśli pola są widoczne (gdy konto nie ma zapisanego adresu)
    def fill(regex, value):
        if not value: return
        try:
            page.get_by_label(regex).fill(value, timeout=1000)
        except:
            pass
    fill(re.compile("Imię i nazwisko|Imię|Nazwisko", re.I), os.getenv("FULL_NAME"))
    fill(re.compile("Ulica|Adres", re.I), os.getenv("STREET"))
    fill(re.compile("Kod pocztowy", re.I), os.getenv("POSTCODE"))
    fill(re.compile("Miasto", re.I), os.getenv("CITY"))
    fill(re.compile("Telefon", re.I), os.getenv("PHONE"))

def choose_cod_and_submit(page, auto_place_order: bool):
    # "Za pobraniem" – po etykiecie/tekście
    try:
        page.locator("label:has-text('Za pobraniem')").first.click(timeout=1500)
    except:
        try:
            page.get_by_label(re.compile("Za pobraniem", re.I)).first.check()
        except:
            pass

    # regulamin/zgody
    try:
        page.get_by_label(re.compile("akceptuj|regulamin|zgodę", re.I)).check()
    except:
        pass

    if auto_place_order:
        for sel in ["button:has-text('Zamawiam')",
                    "button:has-text('Złóż zamówienie')",
                    "button:has-text('Potwierdzam')"]:
            try:
                page.locator(sel).first.click(timeout=1500)
                break
            except:
                continue
        page.wait_for_load_state("networkidle")
        return "submitted"
    else:
        return "paused_at_checkout"


def try_buy_first_new(pw, headless: bool, auto_place_order: bool):
    seen = load_seen()
    browser = pw.chromium.launch(headless=headless, args=["--disable-blink-features=AutomationControlled"])
    context = browser.new_context()
    page = context.new_page()

    # jeśli wymagane logowanie – zrób to raz
    try:
        login(page)
    except Exception as e:
        # gdy już zalogowany layout może być inny – to OK
        pass

    # zbierz linki w kategorii Broszki
    links = collect_product_links_on_category(page)
    # UNCOMMENT for broszki
    # new_links = [u for u in links if u not in seen]
    # test
    new_links = links  # TEST: traktuj wszystko jako nowe

    if not new_links:
        print("Brak nowych broszek.")
        browser.close()
        return False

    target = new_links[0]
    print(f"Nowa broszka wykryta: {target}")

    # wejdź na produkt
    page.goto(target, wait_until="domcontentloaded")

    # dodaj do koszyka
    if not add_to_cart(page):
        print("Nie znalazłam przycisku 'Do koszyka'.")
        browser.close()
        return False

    # przejdź do koszyka/kasy
    go_to_cart_or_checkout(page)

    # wypełnij dane adresowe jeśli trzeba
    fill_address_if_needed(page)

    # wybierz 'Za pobraniem' i (opcjonalnie) złóż zamówienie
    result = choose_cod_and_submit(page, auto_place_order)

    # zapisz jako „widziane”
    seen.add(target)
    save_seen(seen)

    if result == "submitted":
        print("Zamówienie złożone. Sprawdź e-mail z potwierdzeniem.")
    else:
        print("Jestem na stronie podsumowania z wybraną opcją 'Za pobraniem'. Dokończ ręcznie.")

    if headless:
        # w trybie headless i tak zamykamy
        browser.close()
    else:
        # daj obejrzeć wynik
        print("Zamknij okno przeglądarki, gdy skończysz.")
        try:
            page.wait_for_timeout(15000)
        except:
            pass
        browser.close()
    return True

def process_once(page, auto_place_order: bool):
    seen = load_seen()
    links = collect_product_links_on_category(page)
    if not links:
        print("Brak produktów w tej kategorii – odświeżę za chwilę.")
        return

    # TEST: traktuj wszystko jako nowe
    # new_links = [u for u in links if u not in seen]
    new_links = links

    # znajdź pierwszy produkt, który da się dodać do koszyka
    target = find_first_available_product(page, new_links)
    if not target:
        print("Nie znalazłam dostępnego produktu (większość może być wyprzedana). Odświeżę za chwilę.")
        return

    print(f"Cel: {target}")
    # Jesteśmy już na stronie produktu (find_first_available_product zrobił goto)
    # spróbuj dodać do koszyka
    if not add_to_cart(page):
        print("Przycisk był widoczny, ale klik się nie powiódł – spróbuję przy następnym odświeżeniu.")
        return

    # przejście do koszyka/kasy
    go_to_cart_or_checkout(page)

    # wypełnienie adresu (jeśli potrzebne) i wybór 'Za pobraniem'
    fill_address_if_needed(page)
    result = choose_cod_and_submit(page, auto_place_order)

    # zapisz ten produkt jako widziany (żeby tryb normalny omijał go później)
    seen.add(target)
    save_seen(seen)

    if result == "submitted":
        print("Zamówienie złożone (AUTO_PLACE_ORDER=true).")
    else:
        print("Zatrzymano na podsumowaniu – kliknij 'Zamawiam' ręcznie (AUTO_PLACE_ORDER=false).")


def has_add_to_cart_button(page) -> bool:
    # szukamy jakiegokolwiek sensownego „Dodaj/Do koszyka”
    candidates = [
        "button:has-text('Dodaj do koszyka')",
        "button:has-text('Do koszyka')",
        "a:has-text('Dodaj do koszyka')",
        "a:has-text('Do koszyka')",
        "button[name='add-to-cart']",
        "#projector_button_basket",
        "button.projector_details__cart-submit",
        "a.add_to_cart_button",
        "[data-action='add-to-cart']",
    ]
    for sel in candidates:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible():
                # jeśli przycisk jest, uznajemy że produkt potencjalnie dostępny
                return True
        except:
            continue

    # czasem sklepy pokazują etykiety wyprzedania
    try:
        if page.locator(":text('Wyprzedane'), :text('Brak w magazynie')").first.count():
            return False
    except:
        pass
    return False

def find_first_available_product(page, links):
    for url in links:
        try:
            page.goto(url, wait_until="domcontentloaded")
        except Exception:
            # sporadyczne net::ERR_ABORTED – spróbuj ponownie
            try:
                page.reload(wait_until="domcontentloaded")
            except:
                continue

        # (opcjonalnie) akceptacja cookies
        try:
            page.locator("button:has-text('Akceptuj')").first.click(timeout=600)
        except:
            pass

        # jeśli ma przycisk koszyka → bierzemy ten produkt
        if has_add_to_cart_button(page):
            return url
    return None


if __name__ == "__main__":
    load_dotenv()
    headless = get_env_bool("HEADLESS", False)
    auto_place_order = get_env_bool("AUTO_PLACE_ORDER", False)
    poll_seconds = int(os.getenv("POLL_SECONDS", "10"))

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=headless, args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context()
        page = context.new_page()

        # Zaloguj raz na starcie (jeśli potrzeba)
        try:
            login(page)
        except Exception:
            pass  # już zalogowana

        while True:
            try:
                process_once(page, auto_place_order)
            except Exception as e:
                print("Błąd w pętli:", e)

            # Zamiast zamykać – po prostu odświeżamy kategorię i czekamy
            # try:
            #     page.goto(CATEGORY_URL, wait_until="domcontentloaded")
            # except Exception:
            #     pass
            # time.sleep(poll_seconds)
            # na końcu pętli
            try:
                page.goto(CATEGORY_URL, wait_until="domcontentloaded")
            except Exception:
                try:
                    page.reload(wait_until="domcontentloaded")
                except:
                    pass
            time.sleep(poll_seconds)
