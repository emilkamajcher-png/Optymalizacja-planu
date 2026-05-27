# modules/modul3_llm.py
import json
import requests
import time
import copy

# --- KONFIGURACJA API ---
API_URL = "http://149.156.194.192:8088/v1/chat/completions" # IP z UPEL
TOKEN = "bsk-00a229f80354793ad87e93fea4691b31521e4fb43a2cf8cd3d916fe02b64a010"

def _call_bielik_api_batch(lista_danych):
    """Wysyła JEDNO ZBIORCZE zapytanie do modelu Bielik i zwraca siatki (0, 1, 2) dla wszystkich."""
    
    system_prompt = (
        "Jesteś zaawansowanym systemem ekstrakcji danych uczelnianych (Information Extraction AI). "
        "Otrzymasz tablicę obiektów z ID wykładowcy i jego tekstem preferencji. "
        "Twoim zadaniem jest przetworzenie wszystkich na raz i zwrócenie JEDNEGO połączonego obiektu JSON, "
        "w którym kluczem jest 'id' wykładowcy. Zwracasz TYLKO kod bez wyjaśnień.\n\n"
        
        "### ZASADY GENEROWANIA MACIERZY:\n"
        "1. Dla każdego wykładowcy stwórz siatkę godzinową dla dni: Mon, Tue, Wed, Thu, Fri.\n"
        "2. Dla każdego dnia stwórz listę wartości dla godzin od 8 do 19 (czyli dokładnie 12 pozycji w liście: indeks 0 to godzina 8, indeks 11 to godzina 19).\n"
        "3. Przypisz wartości liczbowe według kryteriów:\n"
        "   0 - NIE MOGĘ (brak dostępności, zakaz, zebrania, badania, praca w firmie),\n"
        "   1 - MOGĘ W RAZIE POTRZEBY (warunkowo, wolę unikać, w ostateczności, rzadko ale się da),\n"
        "   2 - MOGĘ (na pewno, preferowane godziny, idealne rano/popołudniu, jestem elastyczny).\n\n"
        
        "### WYMAGANY SCHEMAT WYJŚCIA:\n"
        "{\n"
        "  \"ID_WYKLADOWCY_1\": {\n"
        "    \"Mon\": [2, 2, 2, 2, 0, 0, 0, 1, 1, 1, 1, 1],\n"
        "    \"Tue\": [2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2],\n"
        "    \"Wed\": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],\n"
        "    \"Thu\": [1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2],\n"
        "    \"Fri\": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]\n"
        "  },\n"
        "  \"ID_WYKLADOWCY_2\": { ... }\n"
        "}\n\n"
        
        "### REGUŁA KRYTYCZNA:\n"
        "Zwróć WYŁĄCZNIE poprawny składniowo JSON. Nie dodawaj znaczników ```json, powitania ani tekstu pobocznego. Odpowiedź musi zaczynać się od { i kończyć na }."
    )
    
    payload = {
        "model": "SpeakLeash/bielik-11b-v3.0-instruct:Q4_K_M",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(lista_danych, ensure_ascii=False)}
        ],
        "temperature": 0.0 # Całkowita sztywność logiczna dla prawidłowych tablic int
    }
    
    headers = {"Authorization": f"Bearer {TOKEN}"}
    
    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=90)
        if response.status_code == 200:
            content = response.json()["choices"][0]["message"]["content"]
            
            content = content.replace("```json", "").replace("```", "").strip()
            start_idx = content.find('{')
            end_idx = content.rfind('}')
            if start_idx != -1 and end_idx != -1:
                content = content[start_idx:end_idx+1]
                
            return json.loads(content)
        elif response.status_code == 429:
            print("   [UWAGA] Limit API! Czekam 20s...")
            time.sleep(20)
            return None
        else:
            print(f"   [BŁĄD] Odpowiedź API: {response.status_code}")
            return None
    except Exception as e:
        print(f"   [BŁĄD] Problem z połączeniem/parsowaniem: {e}")
        return None

def get_default_matrix():
    """Generuje domyślną bezpieczną siatkę (same jedynki - tryb neutralny) w razie awarii LLM."""
    days = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    return {day: [1] * 12 for day in days}

def przeanalizuj_preferencje(surowe_dane_json, tryb_offline=False, delay_seconds=3):
    print("\n-> MODUŁ 3 (LLM): Rozpoczęto analizę preferencji (tryb BATCH + MATRIX)...")
    
    if tryb_offline:
        print("   [INFO] Tryb offline. Pomijam API i używam domyślnych macierzy.")
        wzbogacone_dane = copy.deepcopy(surowe_dane_json)
        for inst in wzbogacone_dane.get('instructors', []):
            inst['parsed_preferences'] = get_default_matrix()
        return wzbogacone_dane
        
    wzbogacone_dane = copy.deepcopy(surowe_dane_json)
    instructors = wzbogacone_dane.get('instructors', [])
    
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
        
    if delay_seconds > 0:
        print(f"   [DANE] Opóźnienie obronne systemu: {delay_seconds}s...")
        time.sleep(delay_seconds)
        
    print(f"   [INFO] Wysyłam 1 ZBIORCZE zapytanie dla {len(paczka_do_analizy)} prowadzących...")
    wyniki_llm = _call_bielik_api_batch(paczka_do_analizy)
    
    if wyniki_llm is None:
        print("   [UWAGA] Zapytanie awaryjne nie powiodło się. Używam domyślnych macierzy.")
        wyniki_llm = {}
        
    # Rozpakowywanie i przypisywanie macierzy cyfrowych 0,1,2
    for inst in instructors:
        inst_id = inst['id']
        
        if inst_id in wyniki_llm:
            # Zachowujemy klucz 'parsed_preferences', bo pod niego podpina się reszta Waszego systemu
            inst['parsed_preferences'] = wyniki_llm[inst_id]
            print(f"   [OK] Wygenerowano macierz dla: {inst.get('name')}")
        else:
            print(f"   [UWAGA] Brak poprawnego zwrotu dla {inst.get('name')}. Ustawiam macierz domyślną.")
            inst['parsed_preferences'] = get_default_matrix()

    # Nadpisywanie Cache
    cache_path = "data/dane_z_preferencjami_cache.json"
    try:
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(wzbogacone_dane, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    print("-> MODUŁ 3 (LLM): Zakończono z sukcesem.")
    return wzbogacone_dane
