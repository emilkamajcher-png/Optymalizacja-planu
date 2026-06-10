import math
import random
from modules.modul1_parser import Zajecia

class StanPlanu:
    __slots__ = ['zajetosc_sal', 'zajetosc_prowadzacych', 'zajetosc_grup']
    
    def __init__(self):
        self.zajetosc_sal = {}          
        self.zajetosc_prowadzacych = {} 
        self.zajetosc_grup = {}         

    def czy_ruch_jest_legalny(self, zajecia, proponowany_tydzien, proponowany_dzien, start_slot, sala, prowadzacy):
        if sala.pojemnosc < zajecia.liczba_studentow: return False 
        if sala.typ != zajecia.wymagany_typ_sali: return False     
        if zajecia.baza_przedmiotu not in prowadzacy.kompetencje: return False 
        
        # Określamy w których tygodniach fizycznie sprawdzamy miejsce
        tygodnie_do_sprawdzenia = ['A', 'B'] if proponowany_tydzien == 'AB' else [proponowany_tydzien]
        
        # Sprawdzamy twardy limit (max 12h) DLA KAŻDEGO z analizowanych tygodni osobno
        for t in tygodnie_do_sprawdzenia:
            obecne_godz = len([s for s in self.zajetosc_prowadzacych.get(prowadzacy.id, set()) if s[0] == t])
            if obecne_godz + zajecia.wymagane_godziny > 12:
                return False

        for offset in range(zajecia.wymagane_godziny):
            aktualny_slot = start_slot + offset
            # Dostępność uczelni/profesora jest uniwersalna (2D)
            uniwersalny_slot = (proponowany_dzien, aktualny_slot) 
            
            if uniwersalny_slot not in sala.dostepnosc: return False 
            if hasattr(prowadzacy, 'zakazane_sloty') and uniwersalny_slot in prowadzacy.zakazane_sloty: return False 
            
            # Wymogi LLM
            if hasattr(prowadzacy, 'availability_matrix') and prowadzacy.availability_matrix:
                matryca = prowadzacy.availability_matrix
                if proponowany_dzien in matryca:
                    indeks_godziny = aktualny_slot - 8
                    if 0 <= indeks_godziny < 12 and matryca[proponowany_dzien][indeks_godziny] == 0:
                        return False
            
            # Zajętość sal i grup jest tygodniowa (3D)
            for t in tygodnie_do_sprawdzenia:
                slot_3d = (t, proponowany_dzien, aktualny_slot)
                if slot_3d in self.zajetosc_sal.get(sala.id, set()): return False 
                if slot_3d in self.zajetosc_prowadzacych.get(prowadzacy.id, set()): return False 
                if slot_3d in self.zajetosc_grup.get(zajecia.grupa_id, set()): return False 

        return True

    def wstaw_zajecia(self, zajecia, tydzien, dzien, start_slot, sala, prowadzacy):
        zajecia.przypisany_tydzien = tydzien
        zajecia.przypisany_dzien = dzien
        zajecia.przypisany_start_slot = start_slot
        zajecia.przypisana_sala_id = sala.id
        zajecia.prowadzacy_id = prowadzacy.id
        
        tygodnie_do_wpisania = ['A', 'B'] if tydzien == 'AB' else [tydzien]
        
        for t in tygodnie_do_wpisania:
            for offset in range(zajecia.wymagane_godziny):
                slot_3d = (t, dzien, start_slot + offset)
                self.zajetosc_sal.setdefault(sala.id, set()).add(slot_3d)
                self.zajetosc_prowadzacych.setdefault(prowadzacy.id, set()).add(slot_3d)
                self.zajetosc_grup.setdefault(zajecia.grupa_id, set()).add(slot_3d)

    def usun_zajecia(self, zajecia):
        tydzien = getattr(zajecia, 'przypisany_tydzien', None)
        dzien = zajecia.przypisany_dzien
        start_slot = zajecia.przypisany_start_slot
        
        if dzien is None or start_slot is None or tydzien is None: return 
        
        tygodnie_do_usuniecia = ['A', 'B'] if tydzien == 'AB' else [tydzien]
        
        for t in tygodnie_do_usuniecia:
            for offset in range(zajecia.wymagane_godziny):
                slot_3d = (t, dzien, start_slot + offset)
                self.zajetosc_sal[zajecia.przypisana_sala_id].remove(slot_3d)
                self.zajetosc_prowadzacych[zajecia.prowadzacy_id].remove(slot_3d)
                self.zajetosc_grup[zajecia.grupa_id].remove(slot_3d)
                
        zajecia.przypisany_tydzien = None
        zajecia.przypisany_dzien = None
        zajecia.przypisany_start_slot = None
        zajecia.przypisana_sala_id = None
        zajecia.prowadzacy_id = None


class AlgorytmKonstruktywny:
    def __init__(self, stan_planu, prowadzacy_db, sale_db, przedmioty_db):
        self.stan = stan_planu
        self.prowadzacy_db = prowadzacy_db
        self.sale_db = list(sale_db.values())
        self.dni_tygodnia = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
        self.lista_zajec = []
        for przedmiot in przedmioty_db.values():
            zajecia = Zajecia(przedmiot, id_zajec=f"ZAJ_{przedmiot.id}")
            # Dodajemy atrybut domyślny, jeśli parser jeszcze go nie posiada
            zajecia.czestotliwosc = getattr(przedmiot, 'czestotliwosc', 'co_tydzien')
            self.lista_zajec.append(zajecia)
        self.lista_zajec.sort(key=lambda z: (z.wymagane_godziny, z.liczba_studentow), reverse=True)

    def rozwiaz(self):
        return self._backtrack(0)
        
    def _backtrack(self, indeks_zajec):
        if indeks_zajec == len(self.lista_zajec): return True
        zajecia = self.lista_zajec[indeks_zajec]
        
        dostepni_prowadzacy = [p for p in self.prowadzacy_db.values() if zajecia.baza_przedmiotu in p.kompetencje]
        if not dostepni_prowadzacy:
            print(f"\n[BŁĄD W DANYCH] Żaden profesor nie umie uczyć: '{zajecia.baza_przedmiotu}'!")
            return False
            
        dostepni_prowadzacy.sort(key=lambda p: len(self.stan.zajetosc_prowadzacych.get(p.id, set())))
        
        # Określamy, jakie tygodnie algorytm ma przetestować
        mozliwe_tygodnie = ['AB'] if zajecia.czestotliwosc == 'co_tydzien' else ['A', 'B']
            
        for prowadzacy in dostepni_prowadzacy:
            for sala in self.sale_db:
                if sala.typ != zajecia.wymagany_typ_sali or sala.pojemnosc < zajecia.liczba_studentow: continue 
                
                for tydzien in mozliwe_tygodnie:
                    for dzien in self.dni_tygodnia:
                        for start_slot in range(8, 20 - zajecia.wymagane_godziny + 1):
                            if self.stan.czy_ruch_jest_legalny(zajecia, tydzien, dzien, start_slot, sala, prowadzacy):
                                self.stan.wstaw_zajecia(zajecia, tydzien, dzien, start_slot, sala, prowadzacy)
                                if self._backtrack(indeks_zajec + 1): return True
                                self.stan.usun_zajecia(zajecia)
                            
        print(f"\n[BŁĄD W DANYCH] Brak miejsca dla: '{zajecia.przedmiot_id}'!")
        return False
class AlgorytmWyzarzania:
    def __init__(self, stan_planu, lista_zajec, prowadzacy_db, sale_db):
        self.stan = stan_planu
        self.lista_zajec = lista_zajec
        self.prowadzacy_db = prowadzacy_db
        self.sale_db = list(sale_db.values())
        self.dni_tygodnia = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
        
        # Wagi Funkcji Celu wg wytycznych konkursowych
        self.WAGA_NIECHETNIE = 80       # SC-1 (Wysoka)
        self.WAGA_OKIENKO = 50          # SC-2 (Średnia)
        self.WAGA_SC3_PRZEDMIOT = 50    # SC-3 (Średnia)
        self.WAGA_SC4_ROWNOMIERNE = 15  # SC-4 (Niska)
        self.WAGA_SC5_LOKALIZACJA = 15  # SC-5 (Niska)
        self.WAGA_BALANSU_GODZIN = 30   # SC-6 Soft
        self.KARA_KRYTYCZNA_PENSUM = 2000 # SC-6 Hard Penalty

    def oblicz_koszt(self):
        koszt = 0
        
        harmonogram_prow = {p.id: {'A': {}, 'B': {}} for p in self.prowadzacy_db.values()}
        
        # Inicjalizacja harmonogramu grup (potrzebne do SC-3, SC-4, SC-5)
        grupy_id_set = set(z.grupa_id for z in self.lista_zajec)
        harmonogram_grup = {g_id: {'A': {}, 'B': {}} for g_id in grupy_id_set}
        
        for zajecia in self.lista_zajec:
            prowadzacy = self.prowadzacy_db[zajecia.prowadzacy_id]
            godziny = range(zajecia.przypisany_start_slot, zajecia.przypisany_start_slot + zajecia.wymagane_godziny)
            tygodnie = ['A', 'B'] if zajecia.przypisany_tydzien == 'AB' else [zajecia.przypisany_tydzien]
            
            for t in tygodnie:
                # Rejestr dla prowadzących
                harmonogram_prow[zajecia.prowadzacy_id][t].setdefault(zajecia.przypisany_dzien, []).extend(godziny)
                
                # Rejestr dla grup studenckich
                if zajecia.przypisany_dzien not in harmonogram_grup[zajecia.grupa_id][t]:
                    harmonogram_grup[zajecia.grupa_id][t][zajecia.przypisany_dzien] = []
                
                # Zapisujemy format: (start, koniec, przedm_id, sala_id, id_zajecia)
                harmonogram_grup[zajecia.grupa_id][t][zajecia.przypisany_dzien].append(
                    (zajecia.przypisany_start_slot, zajecia.przypisany_start_slot + zajecia.wymagane_godziny, zajecia.baza_przedmiotu, zajecia.przypisana_sala_id, zajecia.id)
                )
            
            # SC-1: Preferencje prowadzących (LLM)
            if hasattr(prowadzacy, 'availability_matrix') and prowadzacy.availability_matrix:
                matryca = prowadzacy.availability_matrix
                if zajecia.przypisany_dzien in matryca:
                    for godzina in godziny:
                        if 0 <= (godzina - 8) < 12 and matryca[zajecia.przypisany_dzien][godzina - 8] == 1:
                            mnoznik = 1 if zajecia.przypisany_tydzien == 'AB' else 0.5
                            koszt += self.WAGA_NIECHETNIE * mnoznik

        # Analiza ograniczeń Prowadzących (SC-2, SC-6)
        for p_id, tyg_dict in harmonogram_prow.items():
            godziny_A = 0
            godziny_B = 0
            for tydz, dni in tyg_dict.items():
                for dzien, sloty in dni.items():
                    if tydz == 'A': godziny_A += len(sloty)
                    if tydz == 'B': godziny_B += len(sloty)
                    
                    # SC-2: Minimalizacja okienek dla prowadzących
                    if len(sloty) > 1:
                        rozpietosc = max(sloty) - min(sloty) + 1
                        okienka = rozpietosc - len(sloty)
                        if okienka > 0: 
                            koszt += okienka * self.WAGA_OKIENKO
            
            # SC-6: Maksymalne obciążenie tygodniowe
            srednia_godzin = (godziny_A + godziny_B) / 2.0
            if srednia_godzin < 8.0:
                koszt += (8.0 - srednia_godzin) * self.KARA_KRYTYCZNA_PENSUM  
            elif srednia_godzin > 12.0:
                koszt += (srednia_godzin - 12.0) * self.KARA_KRYTYCZNA_PENSUM
            else:
                koszt += abs(10.0 - srednia_godzin) * self.WAGA_BALANSU_GODZIN

        # Analiza ograniczeń Grup Studenckich (SC-3, SC-4, SC-5)
        for g_id, tyg_dict in harmonogram_grup.items():
            for tydz, dni in tyg_dict.items():
                godziny_w_dniach = []
                for dzien in self.dni_tygodnia:
                    zajecia_w_dniu = dni.get(dzien, [])
                    suma_godzin_dnia = sum(koniec - start for start, koniec, _, _, _ in zajecia_w_dniu)
                    godziny_w_dniach.append(suma_godzin_dnia)
                    
                    if not zajecia_w_dniu: continue
                    
                    zajecia_w_dniu.sort(key=lambda x: x[0])
                    przedmioty_w_dniu = set()
                    
                    for i, zaj in enumerate(zajecia_w_dniu):
                        start, koniec, baza_przedm, sala_id, id_zajecia = zaj
                        
                        # SC-3: Grupowanie zajęć tego samego przedmiotu
                        if baza_przedm in przedmioty_w_dniu:
                            koszt += self.WAGA_SC3_PRZEDMIOT
                        przedmioty_w_dniu.add(baza_przedm)
                        
                        # SC-5: Minimalizacja przemieszczania się (określane po pierwszych 2 znakach nazwy sali)
                        if i < len(zajecia_w_dniu) - 1:
                            nast_start, _, _, nast_sala_id, _ = zajecia_w_dniu[i+1]
                            if koniec == nast_start: # Brak okienka dla studentów (zmiana budynku w 0 minut)
                                budynek_obecny = str(sala_id)[:2]
                                budynek_nastepny = str(nast_sala_id)[:2]
                                if budynek_obecny != budynek_nastepny:
                                    koszt += self.WAGA_SC5_LOKALIZACJA

                # SC-4: Równomierne rozłożenie obciążenia dni (karanie wariancji z 5 dni roboczych)
                srednia_dla_grupy = sum(godziny_w_dniach) / 5.0
                wariancja = sum((g - srednia_dla_grupy)**2 for g in godziny_w_dniach) / 5.0
                koszt += int(wariancja * self.WAGA_SC4_ROWNOMIERNE)
                        
        return koszt
   
    def optymalizuj(self, temp_pocz=1000.0, temp_konc=1.0, alfa=0.98, iter_na_temp=200):
        aktualny_koszt = self.oblicz_koszt()
        najlepszy_koszt = aktualny_koszt
        temp = temp_pocz
        historia_kosztow = [] 
        
        while temp > temp_konc:
            for _ in range(iter_na_temp):
                zajecia = random.choice(self.lista_zajec)
                
                stary_tydzien = zajecia.przypisany_tydzien
                stary_dzien = zajecia.przypisany_dzien
                stary_slot = zajecia.przypisany_start_slot
                stary_sala_id = zajecia.przypisana_sala_id
                stary_prowadzacy_id = zajecia.prowadzacy_id
                stara_sala = next(s for s in self.sale_db if s.id == stary_sala_id)
                prowadzacy = self.prowadzacy_db[stary_prowadzacy_id]
                
                self.stan.usun_zajecia(zajecia)
                
                znaleziono_miejsce = False
                mozliwe_tygodnie = ['AB'] if zajecia.czestotliwosc == 'co_tydzien' else ['A', 'B']
                
                for _ in range(15):
                    nowy_tydzien = random.choice(mozliwe_tygodnie)
                    nowy_dzien = random.choice(self.dni_tygodnia)
                    nowy_slot = random.randint(8, 20 - zajecia.wymagane_godziny)
                    nowa_sala = random.choice(self.sale_db)
                    
                    dostepni_zastepcy = [p for p in self.prowadzacy_db.values() if zajecia.baza_przedmiotu in p.kompetencje]
                    nowy_prowadzacy = random.choice(dostepni_zastepcy)
                    
                    if self.stan.czy_ruch_jest_legalny(zajecia, nowy_tydzien, nowy_dzien, nowy_slot, nowa_sala, nowy_prowadzacy):
                        self.stan.wstaw_zajecia(zajecia, nowy_tydzien, nowy_dzien, nowy_slot, nowa_sala, nowy_prowadzacy)
                        znaleziono_miejsce = True
                        break
                        
                if not znaleziono_miejsce:
                    self.stan.wstaw_zajecia(zajecia, stary_tydzien, stary_dzien, stary_slot, stara_sala, prowadzacy)
                    continue
                    
                nowy_koszt = self.oblicz_koszt()
                delta = nowy_koszt - aktualny_koszt
                
                if delta < 0 or random.random() < math.exp(-delta / temp):
                    aktualny_koszt = nowy_koszt
                    if aktualny_koszt < najlepszy_koszt: najlepszy_koszt = aktualny_koszt
                else:
                    self.stan.usun_zajecia(zajecia)
                    self.stan.wstaw_zajecia(zajecia, stary_tydzien, stary_dzien, stary_slot, stara_sala, prowadzacy)
            
            historia_kosztow.append(aktualny_koszt)
            temp *= alfa 
            
        return historia_kosztow       

