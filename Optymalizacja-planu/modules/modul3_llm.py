import json
import requests
import time
import copy
import re
import os

API_URL = "http://149.156.194.192:8088/v1/chat/completions"  
TOKEN = "bsk-00a229f80354793ad87e93fea4691b31521e4fb43a2cf8cd3d916fe02b64a010"

DNI_TYGODNIA = ["Mon", "Tue", "Wed", "Thu", "Fri"]

MAPOWANIE_DNI = {
    "mon": "Mon", "monday": "Mon",
    "tue": "Tue", "tuesday": "Tue",
    "wed": "Wed", "wednesday": "Wed",
    "thu": "Thu", "thursday": "Thu",
    "fri": "Fri", "friday": "Fri",
    "poniedzialek": "Mon", "poniedziałek": "Mon", "pon": "Mon",
    "wtorek": "Tue", "wt": "Tue",
    "sroda": "Wed", "środa": "Wed", "sr": "Wed",
    "czwartek": "Thu", "czw": "Thu",
    "piatek": "Fri", "piątek": "Fri", "pt": "Fri",
}

def _parsuj_godzine(wartosc, domyslna):
    if wartosc is None:
        return domyslna
    if isinstance(wartosc, (int, float)):
        return int(wartosc)
    tekst = str(wartosc).strip().lower()
    match = re.search(r"(\d{1,2})", tekst)
    return int(match.group(1)) if match else domyslna

def _parsuj_zakres_czasu(slot):
    """Obsługuje from/to, start/end oraz pole time='8–14'."""
    start = slot.get("from", slot.get("start"))
    koniec = slot.get("to", slot.get("end"))
    if (start is None or koniec is None) and slot.get("time"):
        czas = str(slot["time"]).replace("–", "-").replace("—", "-")
        if "-" in czas:
            czesci = czas.split("-", 1)
            start = start if start is not None else czesci[0].strip()
            koniec = koniec if koniec is not None else czesci[1].strip()
    return _parsuj_godzine(start, 8), _parsuj_godzine(koniec, 20)

def _normalizuj_dzien(dzien_str):
    if not dzien_str:
        return None
    dzien_str = str(dzien_str).strip()
    if dzien_str in DNI_TYGODNIA:
        return dzien_str
    return MAPOWANIE_DNI.get(dzien_str.lower(), None)

def rozpakuj_dni(dzien_str):
    """Rozpakowuje Mon, Mon-Fri, poniedziałek–piątek itd."""

    if not dzien_str:
        return []
    dzien_str = str(dzien_str).strip()

    if dzien_str in DNI_TYGODNIA:
        return [dzien_str]

    pojedynczy = _normalizuj_dzien(dzien_str)

    if pojedynczy:
        return [pojedynczy]

    wynik = set()
    tekst = dzien_str.replace("–", "-").replace("—", "-")

    if "-" in tekst:
        start_raw, koniec_raw = tekst.split("-", 1)
        start = _normalizuj_dzien(start_raw.strip())
        koniec = _normalizuj_dzien(koniec_raw.strip())

        if start and koniec and start in DNI_TYGODNIA and koniec in DNI_TYGODNIA:
            idx_start = DNI_TYGODNIA.index(start)
            idx_koniec = DNI_TYGODNIA.index(koniec)

            for i in range(min(idx_start, idx_koniec), max(idx_start, idx_koniec) + 1):
                wynik.add(DNI_TYGODNIA[i])

    for slowo in re.split(r"[,;/\s]+", tekst):
        dzien = _normalizuj_dzien(slowo.strip())

        if dzien:
            wynik.add(dzien)

    for skrot in DNI_TYGODNIA:
        if skrot in dzien_str:
            wynik.add(skrot)
    return list(wynik)

def normalizuj_slot(slot):
    """Jednolity format: {'day': 'Mon', 'from': 8, 'to': 14}."""
    if not isinstance(slot, dict):
        return None
    dni = rozpakuj_dni(slot.get("day", ""))

    if not dni:
        return None
    start, koniec = _parsuj_zakres_czasu(slot)
    start = max(8, min(20, start))
    koniec = max(8, min(20, koniec))
    if koniec <= start:
        return None
    return [{"day": dzien, "from": start, "to": koniec} for dzien in dni]

def normalizuj_liste_slotow(sloty):
    wynik = []
    for slot in sloty or []:
        znormalizowane = normalizuj_slot(slot)
        if znormalizowane:
            wynik.extend(znormalizowane)
    return wynik

def normalizuj_preferencje_llm(prefs):
    """Naprawia typowe błędy Bielika (polskie dni, start/end, time)."""
    if not isinstance(prefs, dict):
        return domyslne_preferencje_neutralne()
    znormalizowane = {
        "preferred_slots": normalizuj_liste_slotow(prefs.get("preferred_slots", [])),
        "emergency_slots": normalizuj_liste_slotow(prefs.get("emergency_slots", [])),
        "forbidden_slots": normalizuj_liste_slotow(prefs.get("forbidden_slots", [])),
        "lecture_preferences": prefs.get("lecture_preferences"),
        "lab_preferences": prefs.get("lab_preferences"),
    }
    return znormalizowane

def domyslne_preferencje_neutralne():
    """Bezpieczny fallback: wszystko dozwolone (1), nic preferowanego."""
    return {
        "preferred_slots": [],
        "emergency_slots": [],
        "forbidden_slots": [],
        "lecture_preferences": None,
        "lab_preferences": None,
    }

def generuj_matryce_dostepnosci(prefs):
    """
    Tłumaczy sloty na macierz dla algorytmu optymalizacji.
    0 = zakaz (HC-4), 1 = dozwolone, 2 = preferowane (SC-1).
    Hierarchia: 0 nadpisuje wszystko, 2 nadpisuje 1, 1 nie nadpisuje 2 ani 0.
    """
    prefs = normalizuj_preferencje_llm(prefs)
    matryca = {dzien: [1] * 12 for dzien in DNI_TYGODNIA}
    
    def wpisz_sloty(sloty, wartosc):
        for slot in sloty:
            dzien = slot.get("day")
            if dzien not in matryca:
                continue
            s_idx = max(0, int(slot["from"]) - 8)
            k_idx = min(12, int(slot["to"]) - 8)
            for i in range(s_idx, k_idx):
                # Twarda hierarchia nadpisywania
                if wartosc == 0:
                    matryca[dzien][i] = 0  # 0 nadpisuje wszystko (betonowy zakaz)
                elif wartosc == 2 and matryca[dzien][i] != 0:
                    matryca[dzien][i] = 2  # 2 wchodzi tylko, gdy nie ma zakazu
                elif wartosc == 1 and matryca[dzien][i] == 1:
                    matryca[dzien][i] = 1  # 1 wchodzi tylko na czyste jedynki (niczego nie psuje)

    # Najpierw awaryjne, potem preferowane, a na koniec jako mur wjeżdżają zakazy!
    wpisz_sloty(prefs.get("emergency_slots", []), 1)
    wpisz_sloty(prefs.get("preferred_slots", []), 2)
    wpisz_sloty(prefs.get("forbidden_slots", []), 0)
    
    return matryca


def _system_prompt():
   
   return (
        "Jesteś zaawansowanym systemem ekstrakcji danych (Information Extraction AI). "
        "Otrzymasz tablicę JSON z preferencjami dydaktycznymi. "
        "Twoim zadaniem jest wyciągnięcie grafiku dostępności i zwrot TABLICY (LISTY) obiektów JSON. "
        "Zwracasz TYLKO poprawny JSON — bez komentarzy, bez markdown.\n\n"
        "### KRYTYCZNE WYMAGANIA FORMATU (MUSISZ ICH PRZESTRZEGAĆ):\n"
        "0. ZWRACAJ TYLKO PRAWIDŁOWY JSON. Klucze (np. \"id\", \"preferred_slots\") MUSZĄ być w PODWÓJNYCH cudzysłowach! ZAKAZ używania apostrofów.\n"
        "1. Pole 'day' ZAWSZE w angielskim skrócie: Mon, Tue, Wed, Thu, Fri.\n"
        "2. Godziny ZAWSZE jako liczby całkowite w polach 'from' i 'to' (NIE używaj 'start', 'end', 'time').\n"
        "3. Każdy dzień musi być OSOBNYM obiektem. ZAKAZ myślników i zakresów w polu 'day' "
        "(np. NIE pisz 'Mon-Fri' — zamiast tego 5 osobnych obiektów).\n"
        "4. Zakres godzin jest półotwarty: slot 8–12 oznacza from=8, to=12 (godziny 8,9,10,11).\n"
        "5. Zwróć dokładnie tyle elementów tablicy, ile otrzymałeś wejść (po jednym na id).\n\n"
        "6. ABSOLUTNY ZAKAZ MYŚLENIA NA GŁOS. ZABRANIA SIĘ używania znaczników <think>. Odpowiedź MUSI zaczynać się od znaku '[' a kończyć na ']'. Żadnych wstępów, żadnych wyjaśnień.\n"
        "### ZASADY MAPOWANIA DNI I GODZIN:\n"
        "1. Dni tygodnia mapuj na: Poniedziałek='Mon', Wtorek='Tue', Środa='Wed', Czwartek='Thu', Piątek='Fri'.\n"
        "2. Rozwijaj przedziały dni na osobne obiekty: 'poniedziałek-środa' -> Mon, Tue, Wed.\n"
        "3. Format 24-godzinny (8, 12, 18, 20).\n"
        "4. Tłumaczenie pojęć czasowych:\n"
        "   - 'rano' / 'przed południem' = from 8, to 12\n"
        "   - 'popołudniami' / 'po południu' = from 12, to 18\n"
        "   - 'cały dzień' / brak godzin = from 8, to 20\n"
        "   - 'przed X' = from 8, to X\n"
        "   - 'po Y' / 'brak dostępności po Y' = from Y, to 20\n\n"
        "### KATEGORYZACJA (SLOTY):\n"
        "1. 'MOGĘ' -> preferred_slots (preferowane okna dostępności).\n"
        "2. 'DOSTĘPNOŚĆ AWARYJNA' -> emergency_slots (możliwe, ale niepreferowane).\n"
        "3. 'NIE MOGĘ' -> forbidden_slots (twarde zakazy).\n"
        "   - Rozbijaj listy dni ('i', ',', '-') na osobne obiekty.\n"
        "   - 'po 15 w żaden dzień' -> 5 obiektów forbidden: Mon-Fri, from 15, to 20.\n"
        "   - 'przed 12' -> 5 obiektów forbidden: Mon-Fri, from 8, to 12.\n"
        "   - 'środa i piątek (cały dzień)' -> Wed i Fri, from 8, to 20.\n"
        "4. Ignoruj powody prywatne (seminarium, rada) — liczy się tylko efekt czasowy.\n\n"
        "### PRZYKŁAD 1:\n"
        "WEJŚCIE:\n"
        "[{\"id\": \"I99\", \"text\": \"MOGĘ: poniedziałek i wtorek 8–14. NIE MOGĘ: czwartek (cały dzień); po 15 w żaden dzień.\"}]\n"
        "WYJŚCIE:\n"
        "[{\n"
        "  \"id\": \"I99\",\n"
        "  \"preferred_slots\": [{\"day\": \"Mon\", \"from\": 8, \"to\": 14}, {\"day\": \"Tue\", \"from\": 8, \"to\": 14}],\n"
        "  \"emergency_slots\": [],\n"
        "  \"forbidden_slots\": [\n"
        "    {\"day\": \"Thu\", \"from\": 8, \"to\": 20},\n"
        "    {\"day\": \"Mon\", \"from\": 15, \"to\": 20},\n"
        "    {\"day\": \"Tue\", \"from\": 15, \"to\": 20},\n"
        "    {\"day\": \"Wed\", \"from\": 15, \"to\": 20},\n"
        "    {\"day\": \"Fri\", \"from\": 15, \"to\": 20}\n"
        "  ],\n"
        "  \"lecture_preferences\": null,\n"
        "  \"lab_preferences\": null\n"
        "}]\n\n"
        "### PRZYKŁAD 2:\n"
        "WEJŚCIE:\n"
        "[{\"id\": \"I27\", \"text\": \"MOGĘ: poniedziałek–piątek 12–18. NIE MOGĘ: przed 12; środa 16–18 (seminarium). DOSTĘPNOŚĆ AWARYJNA: środa 12–16, piątek 14–18.\"}]\n"
        "WYJŚCIE:\n"
        "[{\n"
        "  \"id\": \"I27\",\n"
        "  \"preferred_slots\": [\n"
        "    {\"day\": \"Mon\", \"from\": 12, \"to\": 18}, {\"day\": \"Tue\", \"from\": 12, \"to\": 18},\n"
        "    {\"day\": \"Wed\", \"from\": 12, \"to\": 18}, {\"day\": \"Thu\", \"from\": 12, \"to\": 18},\n"
        "    {\"day\": \"Fri\", \"from\": 12, \"to\": 18}\n"
        "  ],\n"
        "  \"emergency_slots\": [\n"
        "    {\"day\": \"Wed\", \"from\": 12, \"to\": 16}, {\"day\": \"Fri\", \"from\": 14, \"to\": 18}\n"
        "  ],\n"
        "  \"forbidden_slots\": [\n"
        "    {\"day\": \"Mon\", \"from\": 8, \"to\": 12}, {\"day\": \"Tue\", \"from\": 8, \"to\": 12},\n"
        "    {\"day\": \"Wed\", \"from\": 8, \"to\": 12}, {\"day\": \"Thu\", \"from\": 8, \"to\": 12},\n"
        "    {\"day\": \"Fri\", \"from\": 8, \"to\": 12}, {\"day\": \"Wed\", \"from\": 16, \"to\": 20}\n"
        "  ],\n"
        "  \"lecture_preferences\": null,\n"
        "  \"lab_preferences\": null\n"
        "}]\n\n"
        "### PRZYKŁAD 3:\n"
        "WEJŚCIE:\n"
        "[{\"id\": \"I30\", \"text\": \"MOGĘ: poniedziałek, wtorek i czwartek 8–12. NIE MOGĘ: środa i piątek (ograniczenie twarde); brak dostępności po godz. 14. DOSTĘPNOŚĆ AWARYJNA: czwartek 12–14, poniedziałek 12–14.\"}]\n"
        "WYJŚCIE:\n"
        "[{\n"
        "  \"id\": \"I30\",\n"
        "  \"preferred_slots\": [\n"
        "    {\"day\": \"Mon\", \"from\": 8, \"to\": 12}, {\"day\": \"Tue\", \"from\": 8, \"to\": 12},\n"
        "    {\"day\": \"Thu\", \"from\": 8, \"to\": 12}\n"
        "  ],\n"
        "  \"emergency_slots\": [\n"
        "    {\"day\": \"Thu\", \"from\": 12, \"to\": 14}, {\"day\": \"Mon\", \"from\": 12, \"to\": 14}\n"
        "  ],\n"
        "  \"forbidden_slots\": [\n"
        "    {\"day\": \"Wed\", \"from\": 8, \"to\": 20}, {\"day\": \"Fri\", \"from\": 8, \"to\": 20},\n"
        "    {\"day\": \"Mon\", \"from\": 14, \"to\": 20}, {\"day\": \"Tue\", \"from\": 14, \"to\": 20},\n"
        "    {\"day\": \"Thu\", \"from\": 14, \"to\": 20}\n"
        "  ],\n"
        "  \"lecture_preferences\": \"rano\",\n"
        "  \"lab_preferences\": null\n"
        "}]\n\n"
        "### WYMAGANY SCHEMAT WYJŚCIA:\n"
        "[{\n"
        "  \"id\": \"ID_WYKLADOWCY\",\n"
        "  \"preferred_slots\": [],\n"
        "  \"emergency_slots\": [],\n"
        "  \"forbidden_slots\": [],\n"
        "  \"lecture_preferences\": null,\n"
        "  \"lab_preferences\": null\n"
        "}]"
    )

def _wyciagnij_json_z_odpowiedzi(content):
    #wycięcie "myślenia na głos" modelu (wszystko między <think> a </think>)
    content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
    content = content.replace("```json", "").replace("```", "").strip()
    
    start_idx = content.find("[")
    end_idx = content.rfind("]")
    if start_idx == -1:
        start_idx = content.find("{")
        end_idx = content.rfind("}")
    if start_idx == -1 or end_idx == -1:
        return None
        
    clean_json = content[start_idx:end_idx + 1]

    clean_json = re.sub(r",\s*([\]}])", r"\1", clean_json)
    return json.loads(clean_json)

def _call_bielik_api_batch(lista_danych, max_retries=3):
    payload = {
        "model": "SpeakLeash/bielik-11b-v3.0-instruct:Q4_K_M",
        "messages": [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": json.dumps(lista_danych, ensure_ascii=False)},
        ],
        "temperature": 0.1,
        "max_tokens": 4096
    }
    headers = {"Authorization": f"Bearer {TOKEN}"}
    for attempt in range(max_retries):
        try:
            response = requests.post(API_URL, headers=headers, json=payload, timeout=90)
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                try:
                    dane_json = _wyciagnij_json_z_odpowiedzi(content)
                except json.JSONDecodeError as e:
                    print(f"   [BŁĄD PARSOWANIA JSON]: {e}")
                    print(f"   [PODGLĄD BŁĘDU AI]: {content[:400]}")
                    return None
                if isinstance(dane_json, list):
                    wynik_dict = {}
                    for item in dane_json:
                        if isinstance(item, dict) and "id" in item:
                            item = copy.deepcopy(item)
                            inst_id = item.pop("id")
                            wynik_dict[inst_id] = normalizuj_preferencje_llm(item)
                    return wynik_dict
                if isinstance(dane_json, dict):
                    return {k: normalizuj_preferencje_llm(v) for k, v in dane_json.items()}
                return None
            if response.status_code == 429:
                print(f"   [UWAGA] Limit API (próba {attempt + 1}/{max_retries}). Czekam 15s...")
                time.sleep(15)
                continue
            print(f"   [BŁĄD API] status={response.status_code}, body={response.text[:200]}")
            return None
        except Exception as e:
            print(f"   [BŁĄD] Problem z połączeniem: {e}")
            return None
    return None

def przeanalizuj_preferencje(surowe_dane_json, tryb_offline=False):
    print("\n-> MODUŁ 3 (LLM): Rozpoczęto analizę preferencji (tryb BATCH)...")
    if tryb_offline:
        print("   [INFO] Tryb offline. Pomijam API.")
        wzbogacone = copy.deepcopy(surowe_dane_json)
        for inst in wzbogacone.get("instructors", []):
            prefs = normalizuj_preferencje_llm(inst.get("parsed_preferences", domyslne_preferencje_neutralne()))
            inst["parsed_preferences"] = prefs
            inst["parsed_preferences"]["availability_matrix"] = generuj_matryce_dostepnosci(prefs)
        return wzbogacone
    wzbogacone_dane = copy.deepcopy(surowe_dane_json)
    instructors = wzbogacone_dane.get("instructors", [])
    paczka_do_analizy = [
        {"id": inst["id"], "text": inst["preferences_text"]}
        for inst in instructors
        if inst.get("preferences_text")
    ]

    if not paczka_do_analizy:
        return wzbogacone_dane

    rozmiar_paczki = 4
    wyniki_llm = {}
    print(f"   [INFO] {len(paczka_do_analizy)} prowadzących, paczki po {rozmiar_paczki}...")

    for i in range(0, len(paczka_do_analizy), rozmiar_paczki):
        chunk = paczka_do_analizy[i:i + rozmiar_paczki]
        numer_paczki = (i // rozmiar_paczki) + 1
        print(f"\n   [INFO] ---> Paczka {numer_paczki}: {[x['id'] for x in chunk]}")
        wynik_chunk = _call_bielik_api_batch(chunk)
        if wynik_chunk is not None:
            wyniki_llm.update(wynik_chunk)
            print(f"   [OK] Paczka {numer_paczki} przetworzona.")
        else:
            print(f"   [UWAGA] Paczka {numer_paczki} nieudana — fallback neutralny.")
        time.sleep(1)
    for inst in instructors:
        inst_id = inst["id"]
        if inst_id in wyniki_llm:
            prefs = wyniki_llm[inst_id]
        else:
            prefs = domyslne_preferencje_neutralne()
            print(f"   [FALLBACK] {inst_id}: brak odpowiedzi LLM, ustawiono neutralne preferencje.")
        inst["parsed_preferences"] = prefs
        inst["parsed_preferences"]["availability_matrix"] = generuj_matryce_dostepnosci(prefs)
    cache_path = "data/dane_z_preferencjami_cache.json"
    try:
        os.makedirs("data", exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(wzbogacone_dane, f, indent=2, ensure_ascii=False)
        print(f"   [INFO] Zapisano cache: {cache_path}")
    except Exception as e:
        print(f"   [UWAGA] Nie udało się zapisać cache: {e}")
    print("\n-> MODUŁ 3 (LLM): Zakończono.")

    return wzbogacone_dane