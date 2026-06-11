# modules/modul3_llm.py
import json
import requests
import time
import copy
import re
# --- KONFIGURACJA API ---
API_URL = "http://149.156.194.192:8088/v1/chat/completions" # IP z UPEL
TOKEN = "bsk-00a229f80354793ad87e93fea4691b31521e4fb43a2cf8cd3d916fe02b64a010"


def _call_bielik_api_batch(lista_danych, max_retries=3):
    """Wysyła zbiorcze zapytanie do modelu Bielik z ulepszonym parsowaniem list JSON."""
    
    system_prompt = (
        "Jesteś zaawansowanym systemem ekstrakcji danych (Information Extraction AI). "
        "Otrzymasz tablicę JSON z preferencjami dydaktycznymi. "
        "Twoim zadaniem jest wyciągnięcie grafiku dostępności i zwrot TABLICY (LISTY) obiektów JSON. "
        "Zwracasz TYLKO kod bez wyjaśnień.\n\n"
        
        "### ZASADY MAPOWANIA DNI I GODZIN:\n"
        "1. Dni tygodnia ZAWSZE mapuj na angielskie skróty: Poniedziałek='Mon', Wtorek='Tue', Środa='Wed', Czwartek='Thu', Piątek='Fri'.\n"
        "2. Rozwijaj przedziały: 'poniedziałek-środa' oznacza Mon, Tue, Wed.\n"
        "3. Używaj wyłącznie formatu 24-godzinnego (np. 8, 12, 18, 20).\n"
        "4. Tłumaczenie pojęć czasowych:\n"
        "   - 'rano' / 'przed południem' = 8 do 12.\n"
        "   - 'popołudniami' / 'po południu' = 12 do 18.\n"
        "   - 'cały dzień' / brak podanych godzin = 8 do 20.\n"
        "   - 'przed X' = od 8 do X.\n"
        "   - 'po Y' = od Y do 20.\n\n"
        
        "### KATEGORYZACJA (SLOTY):\n"
        "1. 'MOGĘ' -> przypisz do 'preferred_slots' (jako obiekty {\"day\": \"Skrót\", \"from\": start, \"to\": koniec}).\n"
        "2. 'DOSTĘPNOŚĆ AWARYJNA' -> przypisz do 'emergency_slots'.\n"
        "3. 'NIE MOGĘ' -> przypisz do 'forbidden_slots'. \n"
        "   - UWAGA: Jeśli zakaz brzmi 'przed 11 w żaden dzień' lub 'brak dostępności przed 12', wygeneruj forbidden_slots dla KAŻDEGO dnia (Mon-Fri) w tych godzinach.\n"
        "   - UWAGA: Jeśli zakaz to sam dzień np. 'piątek (zajęcia badawcze)', wygeneruj forbidden_slots dla Fri od 8 do 20.\n"
        "4. Ignoruj prywatne powody (np. rady, badania) - wyciągaj same dni i godziny.\n\n"
        
        "### PREFERENCJE TYPU ZAJĘĆ:\n"
        "- 'lecture_preferences': Szukaj słów 'wykład', 'wykłady'. Jeśli pisze 'nie prowadzę wykładów', wpisz 'brak wykładów'. Jeśli brak, wpisz null.\n"
        "- 'lab_preferences': Szukaj słów 'laboratorium', 'ćwiczenia', 'projekt', 'bloki'. Jeśli brak, wpisz null.\n\n"
        
        "### WYMAGANY SCHEMAT WYJŚCIA (TABLICA):\n"
        "[\n"
        "  {\n"
        "    \"id\": \"ID_WYKLADOWCY\",\n"
        "    \"preferred_slots\": [{\"day\": \"Mon\", \"from\": 8, \"to\": 14}],\n"
        "    \"emergency_slots\": [],\n"
        "    \"forbidden_slots\": [{\"day\": \"Fri\", \"from\": 8, \"to\": 20}],\n"
        "    \"lecture_preferences\": \"rano\",\n"
        "    \"lab_preferences\": \"popołudniami, bloki\"\n"
        "  }\n"
        "]\n\n"
        
        "### PRZYKŁAD (FEW-SHOT):\n"
        "WEJŚCIE:\n"
        "[\n"
        "  {\"id\": \"I99\", \"text\": \"MOGĘ: poniedziałek-środa 8–14. NIE MOGĘ: czwartek. Wykłady rano.\"}\n"
        "]\n"
        "WYJŚCIE:\n"
        "[\n"
        "  {\n"
        "    \"id\": \"I99\",\n"
        "    \"preferred_slots\": [{\"day\": \"Mon\", \"from\": 8, \"to\": 14}, {\"day\": \"Tue\", \"from\": 8, \"to\": 14}, {\"day\": \"Wed\", \"from\": 8, \"to\": 14}],\n"
        "    \"emergency_slots\": [],\n"
        "    \"forbidden_slots\": [{\"day\": \"Thu\", \"from\": 8, \"to\": 20}],\n"
        "    \"lecture_preferences\": \"rano\",\n"
        "    \"lab_preferences\": null\n"
        "  }\n"
        "]\n\n"
        
        "### REGUŁA KRYTYCZNA:\n"
        "Zwróć WYŁĄCZNIE poprawny składniowo JSON zaczynający się od [ i kończący na ]."
    )
    
    payload = {
        "model": "SpeakLeash/bielik-11b-v3.0-instruct:Q4_K_M",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(lista_danych, ensure_ascii=False)}
        ],
        "temperature": 0.1
    }
    
    headers = {"Authorization": f"Bearer {TOKEN}"}
    
    for attempt in range(max_retries):
        try:
            response = requests.post(API_URL, headers=headers, json=payload, timeout=90)
            
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                
                # Wstępne czyszczenie ze znaczników markdown
                content = content.replace("```json", "").replace("```", "").strip()
                
                # Szukamy klamer tablicy (Listy)
                start_idx = content.find('[')
                end_idx = content.rfind(']')
                
                # Fallback, gdyby model uparł się zwrócić słownik
                if start_idx == -1 or end_idx == -1:
                    start_idx = content.find('{')
                    end_idx = content.rfind('}')
                
                if start_idx != -1 and end_idx != -1:
                    content = content[start_idx:end_idx+1]
                    
                    # MAGIA: Usuwamy błędne przecinki na końcu tablic i słowników np. ", ]" -> "]"
                    content = re.sub(r',\s*([\]}])', r'\1', content)
                    
                    try:
                        dane_json = json.loads(content)
                        
                        # Jeśli model zwrócił listę (zgodnie z promptem), transformujemy ją na słownik
                        if isinstance(dane_json, list):
                            wynik_dict = {}
                            for item in dane_json:
                                if "id" in item:
                                    inst_id = item.pop("id")
                                    wynik_dict[inst_id] = item
                            return wynik_dict
                        
                        # Jeśli awaryjnie zwrócił słownik
                        elif isinstance(dane_json, dict):
                            return dane_json
                            
                    except json.JSONDecodeError as e:
                        print(f"   [BŁĄD PARSOWANIA JSON]: {e}")
                        # Drukujemy surowy tekst, aby w razie błędu widzieć, co wypluł model
                        print(f"   [SUROWY TEKST MODELU]:\n{content}\n")
                        return None
                else:
                    print("   [BŁĄD DEBUG] Nie znaleziono klamer struktury JSON w odpowiedzi!")
                    return None
                    
            elif response.status_code == 429:
                print(f"   [UWAGA] Limit API (Próba {attempt+1}/{max_retries})! Czekam 15s...")
                import time
                time.sleep(15)
                continue
                
            else:
                print(f"   [BŁĄD] Odpowiedź API: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"   [BŁĄD] Problem z połączeniem: {e}")
            return None
            
    print("   [BŁĄD] Przekroczono maksymalną liczbę prób połączenia z API.")
    return None
def przeanalizuj_preferencje(surowe_dane_json, tryb_offline=True):
    print("\n-> MODUŁ 3 (LLM): Rozpoczęto analizę preferencji (tryb BATCH - CHUNKING)...")
    
    if tryb_offline:
        print("   [INFO] Tryb offline. Pomijam API i używam domyślnych danych.")
        return surowe_dane_json
        
    wzbogacone_dane = copy.deepcopy(surowe_dane_json)
    instructors = wzbogacone_dane.get('instructors', [])
    
    # --- 1. ZBIERANIE TEKSTÓW DO ANALIZY ---
    paczka_do_analizy = []
    for inst in instructors:
        if inst.get('preferences_text'):
            paczka_do_analizy.append({
                "id": inst['id'],
                "text": inst['preferences_text']
            })
            
    if not paczka_do_analizy:
        print("   [INFO] Brak preferencji do analizy. Przechodzę dalej.")
        return wzbogacone_dane
        
    # --- 2. DZIELENIE NA PACZKI (CHUNKI) I WYSYŁKA DO AI ---
    rozmiar_paczki = 5 # Wysyłamy po 10 wykładowców na raz
    wyniki_llm = {}
    
    print(f"   [INFO] Łącznie {len(paczka_do_analizy)} prowadzących do analizy. Dzielę na paczki po {rozmiar_paczki}...")
    
    for i in range(0, len(paczka_do_analizy), rozmiar_paczki):
        chunk = paczka_do_analizy[i:i + rozmiar_paczki]
        numer_paczki = (i // rozmiar_paczki) + 1
        print(f"\n   [INFO] ---> Przetwarzam paczkę {numer_paczki} (zawiera {len(chunk)} prowadzących)...")
        
        wynik_chunk = _call_bielik_api_batch(chunk)
        
        if wynik_chunk is not None:
            wyniki_llm.update(wynik_chunk) # Doklejamy wyniki paczki do głównego słownika
            print(f"   [OK] Paczka {numer_paczki} przetworzona pomyślnie.")
        else:
            print(f"   [UWAGA] Paczka {numer_paczki} zakończyła się błędem. Wykładowcy z tej paczki dostaną puste preferencje.")
            
        import time
        time.sleep(3) # Przerwa między paczkami
        
    # --- 3. PRZYPISYWANIE OSTATECZNYCH WYNIKÓW ---
    for inst in instructors:
        inst_id = inst['id']
        
        # Nowy, bogatszy schemat domyślny
        domyslne_puste = {
            "preferred_slots": [{"day": day, "from": 8, "to": 20} for day in ["Mon", "Tue", "Wed", "Thu", "Fri"]],
            "emergency_slots": [],
            "forbidden_slots": [],
            "lecture_preferences": None,
            "lab_preferences": None
        }
        
        # Przypisanie wyników z LLM lub wartości domyślnych
        if inst_id in wyniki_llm:
            inst['parsed_preferences'] = wyniki_llm[inst_id]
        elif inst.get('preferences_text'):
            inst['parsed_preferences'] = domyslne_puste
        else:
            inst['parsed_preferences'] = domyslne_puste

    # --- 4. ZAPIS DO CACHE ---
    cache_path = "data/dane_z_preferencjami_cache.json"
    try:
        import os
        os.makedirs("data", exist_ok=True)
        with open(cache_path, 'w', encoding='utf-8') as f:
            import json
            json.dump(wzbogacone_dane, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"   [UWAGA] Nie udało się zapisać cache: {e}")

    print("\n-> MODUŁ 3 (LLM): Zakończono z sukcesem.")
    return wzbogacone_dane

# --- SEKCJA TESTOWA Z PLIKIEM ---
if __name__ == "__main__":
    # Zmień ścieżkę, jeśli plik leży w innym folderze
    sciezka_do_pliku = "dataset_11_06_2026.json" 
    
    print("--- ROZPOCZĘCIE TESTU Z PLIKIEM ---")
    
    try:
        # 1. Wczytujemy dane z pliku JSON
        import json
        with open(sciezka_do_pliku, "r", encoding="utf-8") as f:
            test_dane_json = json.load(f)
        print(f"   [OK] Pomyślnie wczytano dane z pliku: {sciezka_do_pliku}")
        
        # 2. Wywołujemy funkcję (tryb_offline=False wymusza połączenie z API!)
        wynik = przeanalizuj_preferencje(test_dane_json, tryb_offline=False)

        # 3. Wyświetlamy wynik w konsoli
        print("\n--- WYNIK KOŃCOWY ---")
        # Wyświetlamy tylko pierwszego prowadzącego dla czytelności, żeby nie zalać konsoli
        if "instructors" in wynik and len(wynik["instructors"]) > 0:
            print(json.dumps(wynik["instructors"][0], indent=2, ensure_ascii=False))
            print("...\n(wyświetlono tylko pierwszego prowadzącego. Pełne dane są w folderze data/)")
        
    except FileNotFoundError:
        print(f"   [BŁĄD] Nie znaleziono pliku pod ścieżką: {sciezka_do_pliku}")
        print("   Upewnij się, że plik istnieje w tym samym folderze co skrypt.")
    except Exception as e:
        print(f"   [BŁĄD KRYTYCZNY] Coś poszło nie tak: {e}")