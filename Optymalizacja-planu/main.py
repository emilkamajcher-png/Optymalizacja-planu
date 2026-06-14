import os
import sys
import json
import time
import subprocess

# Importujemy nasze moduły
from modules import modul1_parser
from modules import modul2_optymalizacja
from modules import modul3_llm

PLIK_WEJSCIOWY = "data/dataset_11_06_2026.json"
PLAN_WYNIK = "data/wynik_planu.json"

# --- FUNKCJE POMOCNICZE ---

def zapisz_plan(sciezka, sukces, lista_zajec, historia):
    """Zapisuje wygenerowany plan do pliku JSON, aby Streamlit mógł go odczytać."""
    wynik = {
        "sukces": sukces,
        "historia_kosztow": historia,
        "zajecia": [
            {
                "id": z.id,
                "prowadzacy_id": z.prowadzacy_id,
                "przypisany_dzien": z.przypisany_dzien,
                "przypisany_start_slot": z.przypisany_start_slot,
                "przypisana_sala_id": z.przypisana_sala_id,
                "grupa_id": z.grupa_id,
                "baza_przedmiotu": z.baza_przedmiotu,
            }
            for z in lista_zajec
        ],
    }
    with open(sciezka, "w", encoding="utf-8") as f:
        json.dump(wynik, f, indent=2, ensure_ascii=False)


def uruchom_dashboard():
    """Uruchamia interfejs webowy w przeglądarce."""
    print("\nCzy chcesz uruchomić graficzny interfejs (Dashboard Streamlit)?")
    print("Uwaga: Dashboard webowy zrestartuje silnik wizualny z użyciem własnej pamięci podręcznej.")
    wybor = input("Wpisz 'T' (Tak) lub 'N' (Nie) i wciśnij Enter: ").strip().upper()
    
    if wybor == 'T':
        print("\nUruchamianie serwera wizualizacji... (Za chwilę w przeglądarce otworzy się nowa karta)")
        subprocess.run([sys.executable, "-m", "streamlit", "run", "modules/modul4_wizualizacja.py"])
    else:
        print("\nZakończono pracę programu.")


# --- GŁÓWNA LOGIKA ---

def uruchom_system():
    print("="*60)
    print(" 🚀 START SYSTEMU HARMONOGRAMOWANIA OPTIPLAN (AGH)")
    print("="*60)
    
    # Bezpiecznik: jeśli plan już istnieje, pytamy, czy na pewno chcemy liczyć go od nowa
    if os.path.exists(PLAN_WYNIK):
        print(f"\n✅ Znaleziono gotowy plik planu: {PLAN_WYNIK}.")
        wybor_opt = input("Czy chcesz uruchomić ciężką optymalizację od nowa? Wpisz 'N', aby pominąć (T/N): ").strip().upper()
        if wybor_opt != 'T':
            print("Pomijam optymalizację.")
            uruchom_dashboard()
            return
            
    start_time = time.time()
    
    print("\n[1/4] Wczytywanie surowych danych wejściowych...")
    if not os.path.exists(PLIK_WEJSCIOWY):
        print(f"❌ BŁĄD KRYTYCZNY: Nie znaleziono pliku '{PLIK_WEJSCIOWY}'!")
        print("Upewnij się, że masz folder 'data' z odpowiednim plikiem JSON.")
        sys.exit(1)
        
    with open(PLIK_WEJSCIOWY, 'r', encoding='utf-8') as f:
        surowe_dane = json.load(f)

    print("\n[2/4] Uruchamianie Modułu 3 (Analiza Preferencji LLM)...")
    dane_z_preferencjami = modul3_llm.przeanalizuj_preferencje(surowe_dane, tryb_offline=False)
    
    print("\n[3/4] Uruchamianie Modułu 1 (Budowa Struktur Danych)...")
    prowadzacy_db, sale_db, przedmioty_db = modul1_parser.zbuduj_baze_obiektow(dane_z_preferencjami)

    print("\n[4/4] Uruchamianie Modułu 2 (Silnik Optymalizacji)...")
    stan_bazowy = modul2_optymalizacja.StanPlanu()
    algorytm = modul2_optymalizacja.AlgorytmKonstruktywny(stan_bazowy, prowadzacy_db, sale_db, przedmioty_db)
    
    czy_sukces = algorytm.rozwiaz()
    historia = [] # Pusta lista na wypadek, gdyby HC=0 się nie powiodło
    
    if czy_sukces:
        print("      Plan bazowy ułożony. Uruchamiam Symulowane Wyżarzanie...")
        optymalizator = modul2_optymalizacja.AlgorytmWyzarzania(stan_bazowy, algorytm.lista_zajec, prowadzacy_db, sale_db)
        
        # PAMIĘTAJ! Metoda 'optymalizuj' musi zwracać historię kosztów (return self.historia_kosztow)
        historia = optymalizator.optymalizuj() 
        
        # Zapisujemy gotowy plan na dysku
        zapisz_plan(PLAN_WYNIK, czy_sukces, algorytm.lista_zajec, historia)
        print(f"      💾 Plan został zapisany do: {PLAN_WYNIK}")
        
    czas_dzialania = time.time() - start_time
   
    print("\n" + "="*60)
    if czy_sukces:
        print(f" ✅ SUKCES! Znaleziono poprawny plan (HC = 0).")
        print(f" ⏱️ Czas weryfikacji i układania: {czas_dzialania:.3f} sekund")
        print(f" 📊 Zaplanowano zajęć: {len(algorytm.lista_zajec)}")
    else:
        print(" ❌ PORAŻKA: Algorytm Konstruktywny nie znalazł legalnego ułożenia!")
    print("="*60)

    # Uruchamiamy Streamlit na samym końcu
    uruchom_dashboard()


if __name__ == "__main__":
    uruchom_system()
