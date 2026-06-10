# modules/modul3_llm.py
import json
import requests
import time
import copy

# --- KONFIGURACJA API ---
API_URL = "http://149.156.194.192:8088/v1/chat/completions" # IP z UPEL
TOKEN = "bsk-00a229f80354793ad87e93fea4691b31521e4fb43a2cf8cd3d916fe02b64a010"

def _call_bielik_api_batch(lista_danych):
    """Wysyła JEDNO ZBIORCZE zapytanie do modelu Bielik dla wszystkich prowadzących na raz."""
    
    # Nasz potężny prompt dostosowany do przetwarzania tablicy (Batch Processing)
    system_prompt = (
        "Jesteś zaawansowanym systemem ekstrakcji danych uczelnianych (Information Extraction AI). "
        "Otrzymasz tablicę obiektów z ID wykładowcy i jego tekstem preferencji. "
        "Twoim zadaniem jest przetworzenie wszystkich na raz i zwrócenie JEDNEGO połączonego obiektu JSON, "
        "w którym kluczem jest 'id' wykładowcy. Zwracasz TYLKO kod bez wyjaśnień.\n\n"
        
        "### ZASADY MAPOWANIA (HEURYSTYKI):\n"
        "1. Dni tygodnia ZAWSZE mapuj na angielskie skróty: Poniedziałek='Mon', Wtorek='Tue', Środa='Wed', Czwartek='Thu', Piątek='Fri'.\n"
        "2. Jeśli wykładowca używa określeń potocznych: 'rano' = 08:00-12:00, 'popołudnie' = 12:00-16:00, 'wieczór' = 16:00-20:00.\n"
        "3. Jeśli wykładowca mówi, że NIE MOŻE uczyć w dany dzień, dodaj ten dzień do 'forbidden_slots' od 8 do 20.\n"
        "4. Używaj wyłącznie formatu 24-godzinnego dla godzin (np. 8, 14, 20).\n\n"
        
        "### WYMAGANY SCHEMAT WYJŚCIA:\n"
        "{\n"
        "  \"ID_WYKLADOWCY_1\": {\n"
        "    \"preferred_days\": [\"Skrót\"],\n"
        "    \"preferred_hours_start\": 8,\n"
        "    \"preferred_hours_end\": 20,\n"
        "    \"forbidden_slots\": [{\"day\": \"Skrót\", \"from\": 8, \"to\": 12}]\n"
        "  },\n"
        "  \"ID_WYKLADOWCY_2\": { ... }\n"
        "}\n\n"
        
        "### PRZYKŁAD (FEW-SHOT DLA PACZKI DANYCH):\n"
        "WEJŚCIE:\n"
        "[\n"
        "  {\"id\": \"prof_1\", \"text\": \"Mogę uczyć we wtorki. Rano w poniedziałki nie dam rady.\"},\n"
        "  {\"id\": \"prof_2\", \"text\": \"Nie pracuję w piątki.\"}\n"
        "]\n"
        "WYJŚCIE:\n"
        "{\n"
        "  \"prof_1\": {\"preferred_days\": [\"Tue\"], \"preferred_hours_start\": 8, \"preferred_hours_end\": 20, \"forbidden_slots\": [{\"day\": \"Mon\", \"from\": 8, \"to\": 12}]},\n"
        "  \"prof_2\": {\"preferred_days\": [], \"preferred_hours_start\": 8, \"preferred_hours_end\": 20, \"forbidden_slots\": [{\"day\": \"Fri\", \"from\": 8, \"to\": 20}]}\n"
        "}\n\n"
        
        "### REGUŁA KRYTYCZNA:\n"
        "Zwróć WYŁĄCZNIE poprawny składniowo JSON. Nie dodawaj znaczników ```json, powitania ani tekstu pobocznego. Odpowiedź musi zaczynać się od { i kończyć na }."
    )
    
    payload = {
        "model": "SpeakLeash/bielik-11b-v3.0-instruct:Q4_K_M",
        "messages": [
            {"role": "system", "content": system_prompt},
            # Wysyłamy całą tablicę paczką jako jeden tekst JSON
            {"role": "user", "content": json.dumps(lista_danych, ensure_ascii=False)}
        ],
        "temperature": 0.1, # Niska temperatura = twarda logika
        "max_tokens": 4096  # <--- ZMIANA 1: Zmuszamy serwer do bardzo długiej odpowiedzi
    }
    
    headers = {"Authorization": f"Bearer {TOKEN}"}
    
    try:
        # Podnieśliśmy timeout do 90 sekund, żeby dać mu czas na tak długą odpowiedź
        response = requests.post(API_URL, headers=headers, json=payload, timeout=90)
        if response.status_code == 200:
            content = response.json()["choices"][0]["message"]["content"]
            
            # Pancerne czyszczenie odpowiedzi modelu
            content = content.replace("```json", "").replace("```", "").strip()
            content = content.replace("</tool_call>", "") # <--- ZMIANA 2: Usuwanie błędu halucynacji XML
            
            start_idx = content.find('{')
            end_idx = content.rfind('}')
            if start_idx != -1 and end_idx != -1:
                content = content[start_idx:end_idx+1]
            
            # <--- ZMIANA 3: Ratowanie uciętych JSONów
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                if not content.endswith("}}"):
                    try:
                        return json.loads(content + "}}")
                    except:
                        pass
                return None
            # ----------------------------------------

        elif response.status_code == 429:
            print("   [UWAGA] Limit API! Czekam 10s...")
            time.sleep(10)
            return None
        else:
            print(f"   [BŁĄD] Odpowiedź API: {response.status_code}")
            return None
    except Exception as e:
        print(f"   [BŁĄD] Problem z połączeniem/parsowaniem: {e}")
        return None

def przeanalizuj_preferencje(surowe_dane_json, tryb_offline=True):
    print("\n-> MODUŁ 3 (LLM): Rozpoczęto analizę preferencji (tryb BATCH)...")
    
    if tryb_offline:
        print("   [INFO] Tryb offline. Pomijam API i używam domyślnych danych.")
        return surowe_dane_json
        
    wzbogacone_dane = copy.deepcopy(surowe_dane_json)
    instructors = wzbogacone_dane.get('instructors', [])
    
    # 1. Zbieramy wszystkich profesorów, którzy mają wpisany tekst do JEDNEJ paczki
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
        
    print(f"   [INFO] Wysyłam 1 ZBIORCZE zapytanie dla {len(paczka_do_analizy)} prowadzących...")
    
    # 2. Wysyłamy paczkę do AI - JEDEN RAZ!
    wyniki_llm = _call_bielik_api_batch(paczka_do_analizy)
    
    if wyniki_llm is None:
        print("   [UWAGA] Zapytanie awaryjne nie powiodło się. Używam pustych preferencji.")
        wyniki_llm = {}
        
    # 3. Rozpakowujemy paczkę i przypisujemy wyniki profesorom
    for inst in instructors:
        inst_id = inst['id']
        domyslne_puste = {
            "preferred_days": [], "preferred_hours_start": 8, 
            "preferred_hours_end": 20, "forbidden_slots": []
        }
        
        if inst_id in wyniki_llm:
            inst['parsed_preferences'] = wyniki_llm[inst_id]
            print(f"   [OK] Przeanalizowano: {inst.get('name')}")
        elif inst.get('preferences_text'):
            print(f"   [UWAGA] Brak poprawnego zwrotu dla {inst.get('name')}. Ustawiam puste.")
            inst['parsed_preferences'] = domyslne_puste
        else:
            inst['parsed_preferences'] = domyslne_puste

    # 4. Nadpisywanie Cache
    cache_path = "data/dane_z_preferencjami_cache.json"
    try:
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(wzbogacone_dane, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    print("-> MODUŁ 3 (LLM): Zakończono z sukcesem.")
    return wzbogacone_dane
