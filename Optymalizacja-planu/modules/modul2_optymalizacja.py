import math
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
        # OGRANICZENIA TWARDE (HC-6, HC-7, HC-8)
        if sala.pojemnosc < zajecia.liczba_studentow: return False 
        if sala.typ != zajecia.wymagany_typ_sali: return False     
        if zajecia.baza_przedmiotu not in prowadzacy.kompetencje: return False 
        
        tygodnie_do_sprawdzenia = ['A', 'B'] if proponowany_tydzien == 'AB' else [proponowany_tydzien]
        
        for offset in range(zajecia.wymagane_godziny):
            aktualny_slot = start_slot + offset
            uniwersalny_slot = (proponowany_dzien, aktualny_slot) 
            
            # OGRANICZENIA TWARDE (HC-4, HC-5) - Dostępność Sali i Profesora
            if uniwersalny_slot not in sala.dostepnosc: return False 
            if hasattr(prowadzacy, 'zakazane_sloty') and uniwersalny_slot in prowadzacy.zakazane_sloty: return False 
            
            # Wymogi LLM (HC-4) - Zera w matrycy dostępności AI
            if hasattr(prowadzacy, 'availability_matrix') and prowadzacy.availability_matrix:
                matryca = prowadzacy.availability_matrix
                if proponowany_dzien in matryca:
                    indeks_godziny = aktualny_slot - 8
                    if 0 <= indeks_godziny < 12 and matryca[proponowany_dzien][indeks_godziny] == 0:
                        return False
            
            # OGRANICZENIA TWARDE (HC-1, HC-2, HC-3) - Kolizje 3D (Tygodnie)
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
            zajecia.czestotliwosc = getattr(przedmiot, 'czestotliwosc', 'co_tydzien')
            self.lista_zajec.append(zajecia)
        
        # Heurystyka wstępna: Układaj najtrudniejsze (najdłuższe i największe) zajęcia jako pierwsze
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
            
        # Balans obciążenia: promujemy profesorów, którzy mają najmniej przydzielonych zajęć
        dostepni_prowadzacy.sort(key=lambda p: len(self.stan.zajetosc_prowadzacych.get(p.id, set())))
        
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
                            
        print(f"\n[BŁĄD W DANYCH] Brak miejsca (Twardy Limit) dla przedmiotu: '{zajecia.przedmiot_id}'!")
        return False
        

class AlgorytmWyzarzania:
    def __init__(self, stan_planu, lista_zajec, prowadzacy_db, sale_db):
        self.stan = stan_planu
        self.lista_zajec = lista_zajec
        self.prowadzacy_db = prowadzacy_db
        self.sale_db = list(sale_db.values())
        self.dni_tygodnia = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
        
        # --- ZOPTYMALIZOWANE WAGI KONKURSOWE OGRANICZEŃ MIĘKKICH (SC) ---
        self.KARA_KRYTYCZNA_PENSUM = 5000 # SC-6: Kwadratowa kara za złamanie 8h-12h (Ekstremalna waga)
        self.WAGA_NIECHETNIE = 200        # SC-1: Preferencje LLM (Wysoka waga)
        self.WAGA_BALANSU_GODZIN = 80     # SC-6: Dążenie do środka przedziału (10h)
        self.WAGA_OKIENKO = 50            # SC-2: Okienka prowadzących (Średnia waga)
        self.WAGA_SC3_PRZEDMIOT = 50      # SC-3: Kumulacja tego samego przedmiotu w 1 dzień (Średnia)
        self.WAGA_SC4_ROWNOMIERNE = 10    # SC-4: Wariancja obciążenia w tygodniu dla grupy (Niska)
        self.WAGA_SC5_LOKALIZACJA = 10    # SC-5: Zmiana budynków przez studentów (Niska)

    def oblicz_koszt(self):
        koszt = 0
        
        # Lokalne referencje = szybsze obliczenia pętli (Performance boost)
        w_okienko = self.WAGA_OKIENKO
        w_sc3 = self.WAGA_SC3_PRZEDMIOT
        w_sc5 = self.WAGA_SC5_LOKALIZACJA
        w_sc4 = self.WAGA_SC4_ROWNOMIERNE
        w_niechetnie = self.WAGA_NIECHETNIE
        kara_kryt = self.KARA_KRYTYCZNA_PENSUM
        w_balans = self.WAGA_BALANSU_GODZIN
        
        harmonogram_prow = {p_id: {'A': {}, 'B': {}} for p_id in self.prowadzacy_db.keys()}
        grupy_id_set = set(z.grupa_id for z in self.lista_zajec)
        harmonogram_grup = {g_id: {'A': {}, 'B': {}} for g_id in grupy_id_set}
        
        for zajecia in self.lista_zajec:
            prowadzacy = self.prowadzacy_db[zajecia.prowadzacy_id]
            g_start = zajecia.przypisany_start_slot
            wym_g = zajecia.wymagane_godziny
            godziny = range(g_start, g_start + wym_g)
            tygodnie = ['A', 'B'] if zajecia.przypisany_tydzien == 'AB' else [zajecia.przypisany_tydzien]
            dzien = zajecia.przypisany_dzien
            
            for t in tygodnie:
                harmonogram_prow[zajecia.prowadzacy_id][t].setdefault(dzien, []).extend(godziny)
                
                if dzien not in harmonogram_grup[zajecia.grupa_id][t]:
                    harmonogram_grup[zajecia.grupa_id][t][dzien] = []
                harmonogram_grup[zajecia.grupa_id][t][dzien].append(
                    (g_start, g_start + wym_g, zajecia.baza_przedmiotu, zajecia.przypisana_sala_id)
                )
            
            # SC-1: Preferencje AI (Sloty niechciane)
            if hasattr(prowadzacy, 'availability_matrix') and prowadzacy.availability_matrix:
                matryca = prowadzacy.availability_matrix
                if dzien in matryca:
                    for godzina in godziny:
                        if 0 <= (godzina - 8) < 12 and matryca[dzien][godzina - 8] == 1:
                            mnoznik = 1 if zajecia.przypisany_tydzien == 'AB' else 0.5
                            koszt += w_niechetnie * mnoznik

        # Analiza Prowadzących (SC-2, SC-6)
        for p_id, tyg_dict in harmonogram_prow.items():
            g_A, g_B = 0, 0
            for tydz, dni in tyg_dict.items():
                for d, sloty in dni.items():
                    if tydz == 'A': g_A += len(sloty)
                    else: g_B += len(sloty)
                    
                    # SC-2: Okienka (Luki w środku dnia)
                    if len(sloty) > 1:
                        okienka = (max(sloty) - min(sloty) + 1) - len(sloty)
                        if okienka > 0: koszt += okienka * w_okienko
            
            srednia_godzin = (g_A + g_B) / 2.0
            
            # SC-6: Bezwzględne ramy czasowe z karą nieliniową (kwadratową)
            if srednia_godzin < 8.0:
                koszt += ((8.0 - srednia_godzin) ** 2) * kara_kryt  
            elif srednia_godzin > 12.0:
                koszt += ((srednia_godzin - 12.0) ** 2) * kara_kryt
            else:
                koszt += abs(10.0 - srednia_godzin) * w_balans

        # Analiza Grup Studenckich (SC-3, SC-4, SC-5)
        for g_id, tyg_dict in harmonogram_grup.items():
            for tydz, dni in tyg_dict.items():
                godz_dni = []
                for dzien in self.dni_tygodnia:
                    zaj_w_dniu = dni.get(dzien, [])
                    godz_dni.append(sum(k - s for s, k, _, _ in zaj_w_dniu))
                    
                    if not zaj_w_dniu: continue
                    
                    zaj_w_dniu.sort(key=lambda x: x[0])
                    przedm_dzis = set()
                    
                    for i, zaj in enumerate(zaj_w_dniu):
                        s, k, b_przedm, s_id = zaj
                        
                        # SC-3: Zakaz kilku takich samych przedmiotów w jeden dzień
                        if b_przedm in przedm_dzis:
                            koszt += w_sc3
                        przedm_dzis.add(b_przedm)
                        
                        # SC-5: Lokacje budynków na styk
                        if i < len(zaj_w_dniu) - 1:
                            nast_s, _, _, nast_s_id = zaj_w_dniu[i+1]
                            if k == nast_s and str(s_id)[:2] != str(nast_s_id)[:2]:
                                koszt += w_sc5

                # SC-4: Balans godzin dla grupy metodą wariancji
                srednia_g = sum(godz_dni) / 5.0
                wariancja = sum((g - srednia_g)**2 for g in godz_dni) / 5.0
                koszt += int(wariancja * w_sc4)
                        
        return koszt
   
    # Podbita dokładność optymalizacji
    def optymalizuj(self, temp_pocz=500.0, temp_konc=1.0, alfa=0.99, iter_na_temp=150):
        aktualny_koszt = self.oblicz_koszt()
        najlepszy_koszt = aktualny_koszt
        temp = temp_pocz
        historia_kosztow = [] 
        
        while temp > temp_konc:
            for _ in range(iter_na_temp):
                zajecia = random.choice(self.lista_zajec)
                
                st_tyg = zajecia.przypisany_tydzien
                st_dzien = zajecia.przypisany_dzien
                st_slot = zajecia.przypisany_start_slot
                st_sala_id = zajecia.przypisana_sala_id
                st_prow_id = zajecia.prowadzacy_id
                st_sala = next(s for s in self.sale_db if s.id == st_sala_id)
                st_prow = self.prowadzacy_db[st_prow_id]
                
                self.stan.usun_zajecia(zajecia)
                
                znaleziono = False
                mozliwe_tygodnie = ['AB'] if zajecia.czestotliwosc == 'co_tydzien' else ['A', 'B']
                
                # Zwiększona siatka badawcza (Neighborhood Search)
                for _ in range(20):
                    n_tyg = random.choice(mozliwe_tygodnie)
                    n_dzien = random.choice(self.dni_tygodnia)
                    n_slot = random.randint(8, 20 - zajecia.wymagane_godziny)
                    n_sala = random.choice(self.sale_db)
                    
                    zastepcy = [p for p in self.prowadzacy_db.values() if zajecia.baza_przedmiotu in p.kompetencje]
                    n_prow = random.choice(zastepcy)
                    
                    if self.stan.czy_ruch_jest_legalny(zajecia, n_tyg, n_dzien, n_slot, n_sala, n_prow):
                        self.stan.wstaw_zajecia(zajecia, n_tyg, n_dzien, n_slot, n_sala, n_prow)
                        znaleziono = True
                        break
                        
                if not znaleziono:
                    self.stan.wstaw_zajecia(zajecia, st_tyg, st_dzien, st_slot, st_sala, st_prow)
                    continue
                    
                nowy_koszt = self.oblicz_koszt()
                delta = nowy_koszt - aktualny_koszt
                
                if delta < 0 or random.random() < math.exp(-delta / temp):
                    aktualny_koszt = nowy_koszt
                    if aktualny_koszt < najlepszy_koszt: najlepszy_koszt = aktualny_koszt
                else:
                    self.stan.usun_zajecia(zajecia)
                    self.stan.wstaw_zajecia(zajecia, st_tyg, st_dzien, st_slot, st_sala, st_prow)
            
            historia_kosztow.append(aktualny_koszt)
            temp *= alfa 
            
        return historia_kosztow