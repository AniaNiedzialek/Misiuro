import os, re, json, time
from pathlib import Path
from urllib.parse import urljoin
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PWSTimeout

BASE = "https://misiuri.com"
# CATEGORY_URL="https://misiuri.com/pl/c/Kubki/16"
CATEGORY_URL = "https://misiuri.com/pl/c/Broszki/13"
SEEN_FILE = Path("seen.json")
MAX_ITEMS_PER_RUN = int(os.getenv("MAX_ITEMS_PER_RUN", "3"))  # ile broszek kupować maksymalnie w jednym uruchomieniu


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

def choose_payment_and_submit_cart(page):
    # Dostawa – jeśli coś trzeba zaznaczyć, wybierz pierwszy widoczny wariant
    try:
        page.locator("label:has-text('Kurier')").first.click(timeout=1500)
    except:
        pass

    # Płatność: "przelew Bank ING"
    # Szukamy po etykiecie, potem po tekście
    chose = False
    try:
        page.get_by_label(re.compile("przelew Bank ING", re.I)).first.check()
        chose = True
    except:
        try:
            page.locator("label:has-text('przelew Bank ING')").first.click(timeout=1500)
            chose = True
        except:
            pass

    if not chose:
        print("[INFO] Nie znalazłam płatności 'przelew Bank ING' – zostawiam domyślną.")

    # Przejdź dalej z koszyka
    for sel in ["button:has-text('Zamawiam')", "a:has-text('Zamawiam')"]:
        try:
            page.locator(sel).first.click(timeout=2000)
            return
        except:
            continue
    # awaryjnie
    try:
        page.goto(f"{BASE}/order", wait_until="domcontentloaded")
    except:
        pass


def go_to_cart_then_checkout(page):
    # Jeśli jesteśmy w mini-koszyku – klik "do kasy" / "koszyk"
    try:
        page.locator("a:has-text('do kasy')").first.click(timeout=1500)
    except:
        try:
            page.locator("a:has-text('koszyk')").first.click(timeout=1500)
        except:
            page.goto(f"{BASE}/koszyk", wait_until="domcontentloaded")

    # Teraz strona koszyka: wybierz płatność ING i kliknij "Zamawiam"
    choose_payment_and_submit_cart(page)



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

def process_multiple(page, auto_place_order: bool):
    seen = load_seen()
    links = collect_product_links_on_category(page)
    if not links:
        print("Brak produktów w tej kategorii – odświeżę za chwilę.")
        return 0

    # tylko nowości
    new_links = [u for u in links if u not in seen]

    bought = 0
    for url in new_links:
        if bought >= MAX_ITEMS_PER_RUN:
            break

        # wejdź i sprawdź dostępność
        try:
            page.goto(url, wait_until="domcontentloaded")
        except Exception:
            continue

        if not has_add_to_cart_button(page):
            continue

        print(f"[KUPNO] Próbuję: {url}")

        if not add_to_cart(page):
            print("[INFO] Klik 'Dodaj do koszyka' się nie udał – następny.")
            continue

        # koszyk → wybór ING → dalej
        go_to_cart_then_checkout(page)

        # dane + regulamin + CAPTCHA (pauza) → Podsumowanie → Zamawiam
        result = accept_terms_and_wait_for_captcha_then_continue(page)

        # zapisz i zlicz
        seen.add(url)
        save_seen(seen)

        if result == "submitted":
            bought += 1
            print("[OK] Zamówienie złożone.")
        else:
            print("[INFO] Zatrzymano bez finalizacji.")
            # jeśli przerwałaś ręcznie – wyjdź z pętli
            break

        # po zamówieniu wróć do kategorii, żeby brać kolejne
        try:
            page.goto(CATEGORY_URL, wait_until="domcontentloaded")
        except:
            pass

    return bought


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

def accept_terms_and_wait_for_captcha_then_continue(page):
    # Zaznacz regulamin
    check_terms(page)

    try:
        page.get_by_label(re.compile("Zapozna[ł|łem]em się z regulaminem", re.I)).check(timeout=1500)
    except:
        try:
            page.locator("label:has-text('regulaminem')").first.click(timeout=1500)
        except:
            pass

    # Uzupełnij brakujące pola, jeśli nie wypełniło się z konta
    fill_address_if_needed(page)

    # --- CAPTCHA ---
    # Nie mogę uczyć obchodzenia reCAPTCHA. Zróbmy bezpieczną pauzę i czekajmy,
    # aż ją zaznaczysz (checkbox stanie się "zaznaczony"), wtedy idziemy dalej.
    print("[AKCJA] Zaznacz proszę CAPTCHA 'I'm not a robot'. Skrypt czeka, aż zniknie blokada...")

    # Heurystyka: czekamy aż przycisk 'Podsumowanie' stanie się aktywny/klikalny
    # (po captcha często znika blokada/disabled)
    try:
        page.wait_for_function(
            """() => {
                const btn = [...document.querySelectorAll('button, a')].find(b => /Podsumowanie/i.test(b.innerText));
                if (!btn) return false;
                return !btn.hasAttribute('disabled') && getComputedStyle(btn).pointerEvents !== 'none';
            }""",
            timeout=120000  # 2 minuty na ręczne odkliknięcie
        )
    except:
        print("[INFO] Nie widzę aktywnego przycisku 'Podsumowanie' – spróbuję kliknąć mimo wszystko.")
    
    # Kliknij "Podsumowanie"
    for sel in ["button:has-text('Podsumowanie')", "a:has-text('Podsumowanie')"]:
        try:
            page.locator(sel).first.click(timeout=2000)
            break
        except:
            continue

    # Ostatnia strona – złóż zamówienie
    for sel in ["button:has-text('Zamawiam')",
                "button:has-text('Złóż zamówienie')",
                "button:has-text('Potwierdzam')"]:
        try:
            page.locator(sel).first.click(timeout=2500)
            page.wait_for_load_state("networkidle", timeout=10000)
            return "submitted"
        except:
            continue
    return "paused"

def check_terms(page):
    # 1) Spróbuj po labelce z tekstem
    try:
        page.locator("label:has-text('regulaminem')").first.click(timeout=1200)
        return
    except: 
        pass
    # 2) Jeżeli label nie działa, znajdź input typu checkbox w tej sekcji
    try:
        box = page.locator("input[type='checkbox']").filter(
            has=page.locator("xpath=ancestor::*/descendant::*[contains(., 'regulamin')]")
        ).first
        if box.count():
            # jeśli jest niewidoczny pod labelką – kliknij label powiązany przez 'for'
            try:
                fid = box.get_attribute("id")
                if fid:
                    page.locator(f"label[for='{fid}']").first.click(timeout=800)
                    return
            except:
                pass
            # awaryjnie kliknij sam input (JS)
            page.evaluate("(el)=>el.click()", box)
    except:
        pass

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
                n = process_multiple(page, auto_place_order=True)  # skoro to tryb „kupuj”, ustaw True
                if n > 0:
                    print(f"[INFO] Złożono {n} zamówień w tej turze.")
            except Exception as e:
                print("Błąd w pętli:", e)

            # po serii zakupów – odśwież i czekaj
            try:
                page.goto(CATEGORY_URL, wait_until="domcontentloaded")
            except:
                try: page.reload(wait_until="domcontentloaded")
                except: pass

            time.sleep(poll_seconds)

