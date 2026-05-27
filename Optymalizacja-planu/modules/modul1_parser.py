
class Prowadzacy:
    # NAPRAWA 1: Dodano 'availability_matrix', aby algorytm optymalizacji mógł dołączyć matrycę z LLM
    __slots__ = ['id', 'imie_nazwisko', 'kompetencje', 'preferowane_dni', 'zakazane_sloty', 'limit_slotow_tydzien', 'availability_matrix']
    
    def __init__(self, dane_json):
        self.id = dane_json['id']
        self.imie_nazwisko = dane_json['name']
        self.kompetencje = set(dane_json['subjects']) 
        
        # Bezpieczne pobranie pensum
        hps = dane_json.get('hours_per_semester', 210)
        self.limit_slotow_tydzien = max(1, int(hps / 15))
        
        # Pobieramy preferencje, szukając pod obydwoma kluczami (bezpieczny fallback)
        prefs = dane_json.get('parsed_preferences', dane_json.get('extracted_preferences', {}))
        
        self.preferowane_dni = set(prefs.get('preferred_days', []))
        self.zakazane_sloty = set()
        
        # NAPRAWA 2: Przywrócone bezpieczne przetwarzanie zakazów (Ochrona przed błędem NoneType)
        for zakaz in prefs.get('forbidden_slots', []):
            if zakaz is None: continue
            dzien = zakaz.get('day')
            start = zakaz.get('from')
            koniec = zakaz.get('to')
            
            # Sprawdzamy, czy dane z AI są na pewno liczbami
            if dzien and isinstance(start, int) and isinstance(koniec, int):
                for godzina in range(start, koniec):
                    self.zakazane_sloty.add((dzien, godzina))
                    
        self.availability_matrix = None


class Sala:
    __slots__ = ['id', 'typ', 'pojemnosc', 'dostepnosc']
    def __init__(self, dane_json):
        self.id = dane_json['id']
        self.typ = dane_json['type']
        self.pojemnosc = dane_json['capacity']
        self.dostepnosc = set()
        
        # Jeśli JSON ma wpisaną dostępność - używamy jej bezpiecznie
        if 'availability' in dane_json and dane_json['availability']:
            for dzien, godziny in dane_json['availability'].items():
                if godziny:
                    for godzina in godziny:
                        self.dostepnosc.add((dzien, godzina))
        else:
            # Domyślne ustawienie: uczelnia otwarta Pn-Pt 8:00 - 20:00
            for dzien in ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']:
                for godzina in range(8, 20):
                    self.dostepnosc.add((dzien, godzina))


class Przedmiot:
    # NAPRAWA 3: Dodano 'czestotliwosc' do zadeklarowanej pamięci
    __slots__ = ['id', 'subject_id', 'group_id', 'nazwa', 'typ', 'liczba_studentow', 'wymagane_godziny', 'wymagany_typ_sali', 'czestotliwosc']
    
    def __init__(self, dane_json):
        self.id = dane_json['id']
        
        self.subject_id = dane_json.get('subject_id', self.id)
        self.group_id = dane_json.get('group_id', self.id)
        
        self.nazwa = dane_json['name']
        self.typ = dane_json['type']
        self.liczba_studentow = dane_json.get('students', 20)
        
        if 'hours_per_week' in dane_json:
            self.wymagane_godziny = dane_json['hours_per_week']
        else:
            hps = dane_json.get('hours_per_semester', 30)
            self.wymagane_godziny = max(1, int(hps / 14)) 
            
        self.wymagany_typ_sali = dane_json['required_room_type']
        
        # Jeśli JSON ma 'frequency', używamy tego, a jak nie - domyślnie 'co_tydzien'
        self.czestotliwosc = dane_json.get('frequency', 'co_tydzien')


class Zajecia:
    # NAPRAWA 4: Dodano 'czestotliwosc' oraz 'przypisany_tydzien' dla kalendarza 3D
    __slots__ = ['id', 'przedmiot_id', 'baza_przedmiotu', 'grupa_id', 'liczba_studentow', 
                 'wymagany_typ_sali', 'wymagane_godziny', 'prowadzacy_id', 
                 'przypisany_dzien', 'przypisany_start_slot', 'przypisana_sala_id',
                 'czestotliwosc', 'przypisany_tydzien']
                 
    def __init__(self, przedmiot, id_zajec):
        self.id = id_zajec
        self.przedmiot_id = przedmiot.id
        self.liczba_studentow = przedmiot.liczba_studentow
        self.wymagany_typ_sali = przedmiot.wymagany_typ_sali
        self.wymagane_godziny = przedmiot.wymagane_godziny
        
        self.baza_przedmiotu = przedmiot.subject_id
        self.grupa_id = przedmiot.group_id 
        
        # Pobieramy częstotliwość z obiektu przedmiotu
        self.czestotliwosc = przedmiot.czestotliwosc
        self.przypisany_tydzien = None
        
        self.prowadzacy_id = None 
        self.przypisany_dzien = None
        self.przypisany_start_slot = None
        self.przypisana_sala_id = None


def zbuduj_baze_obiektow(dane_json):
    return (
        {p['id']: Prowadzacy(p) for p in dane_json.get('instructors', [])},
        {s['id']: Sala(s) for s in dane_json.get('rooms', [])},
        {c['id']: Przedmiot(c) for c in dane_json.get('courses', [])}
    )