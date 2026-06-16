import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import numpy as np
import json

from modules import modul1_parser
from modules import modul2_optymalizacja

st.set_page_config(layout="wide", page_title="OptiPlan - Optymalizacja Planu")

st.markdown("""
    <style>
    .stApp { background-color: #f4f7f9; }
    div[data-testid="stVerticalBlock"] > div:has(div.element-container) {
        background-color: white; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); margin-bottom: 20px;
    }
    table.custom-plan-table { width: 100%; border-collapse: collapse; font-family: 'Segoe UI', sans-serif; table-layout: fixed; }
    table.custom-plan-table th { background-color: #eaeef2; color: #1e293b; font-weight: 700; padding: 16px; border: 1px solid #cbd5e1; text-align: center; width: 18%; font-size: 16px; }
    table.custom-plan-table th:first-child { width: 10%; }
    table.custom-plan-table td { border: 1px solid #cbd5e1; height: 85px; padding: 6px; vertical-align: top; background-color: #ffffff; }
    .time-cell { background-color: #f8fafc; font-weight: 700; color: #475569; text-align: center !important; vertical-align: middle !important; font-size: 15px; }
    .stTable { border: none !important; }
    </style>
    """, unsafe_allow_html=True)

HOURS_RANGE = range(8, 20)
DAYS_PL = ["Pon", "Wt", "Śr", "Czw", "Pt"]
DAY_MAP_ENG_TO_PL = {"Mon": "Pon", "Tue": "Wt", "Wed": "Śr", "Thu": "Czw", "Fri": "Pt"}

# UWAGA: Usunięto @st.cache_data, aby program zawsze czytał aktualny, najświeższy plik!
def uruchom_silnik_i_pobierz_plan():  
    # 1. Ścieżki do plików, dokładnie tak jak chciałaś
    cache_path = os.path.join("data", "dane_z_preferencjami_cache.json")
    plan_path = os.path.join("data", "wynik_planu.json")
    
    # 2. Wczytujemy z pamięci gotowe bazy obiektów (Twój preferowany sposób)
    with open(cache_path, 'r', encoding='utf-8') as plik:
        dane_cache = json.load(plik)
    prowadzacy_db, sale_db, przedmioty_db = modul1_parser.zbuduj_baze_obiektow(dane_cache)
    
    # 3. Tworzymy puste struktury zajęć
    stan = modul2_optymalizacja.StanPlanu()
    algorytm = modul2_optymalizacja.AlgorytmKonstruktywny(stan, prowadzacy_db, sale_db, przedmioty_db)
    
    # 4. Wczytujemy gotowy plan zapisany przez silnik
    with open(plan_path, 'r', encoding='utf-8') as f:
        gotowy_wynik = json.load(f)
        
    # 5. Odtwarzamy przypisania z pliku JSON na obiekty Pythona
    plan_dict = {z["id"]: z for z in gotowy_wynik.get("zajecia", [])}
    for z_obj in algorytm.lista_zajec:
        if z_obj.id in plan_dict:
            z_data = plan_dict[z_obj.id]
            z_obj.przypisany_dzien = z_data.get("przypisany_dzien")
            z_obj.przypisany_start_slot = z_data.get("przypisany_start_slot")
            z_obj.przypisana_sala_id = z_data.get("przypisana_sala_id")
            z_obj.prowadzacy_id = z_data.get("prowadzacy_id")
    
    # Pobieramy prawdziwy czas z pliku wynikowego, a nie czas czytania z dysku!
    rzeczywisty_czas = gotowy_wynik.get("czas_optymalizacji", 0.0)
    
    historia = gotowy_wynik.get("historia_kosztow") or []
    return gotowy_wynik.get("sukces", False), algorytm.lista_zajec, prowadzacy_db, sale_db, przedmioty_db, rzeczywisty_czas, historia

with st.spinner("Wczytywanie gotowego planu z dysku..."):
    try:
        SUKCES, LISTA_ZAJEC, PROWADZACY_DB, SALE_DB, PRZEDMIOTY_DB, CZAS_WYKONANIA, HISTORIA_KOSZTOW = uruchom_silnik_i_pobierz_plan()
    except FileNotFoundError:
        st.error("Nie znaleziono wymaganych plików w folderze 'data'. Najpierw uruchom główny plik 'main.py'!")
        st.stop()

with st.sidebar:
    st.title("OptiPlan")
    st.caption("Optymalizacja planu zajęć")
    
    if not SUKCES:
        st.error("Błąd algorytmu: Brak możliwości ułożenia planu dla podanych ograniczeń twardych!")
    else:
        st.success("Wygenerowano zoptymalizowany plan (HC = 0)")
    
    st.subheader("WYBIERZ PERSPEKTYWĘ")
    perspektywa_typ = st.radio("Widok z perspektywy:", ["Grupa", "Prowadzący", "Sala"])
    
    if perspektywa_typ == "Grupa":
        opcje_grup = sorted(list(set([z.grupa_id for z in LISTA_ZAJEC])))
        wybrany_id = st.selectbox("Wybierz grupę:", opcje_grup, index=None, placeholder="Wpisz nazwę grupy...")
        context_title = f"Grupy {wybrany_id}" if wybrany_id else "Wybierz grupę"
    elif perspektywa_typ == "Prowadzący":
        opcje_prof = {p_id: p.imie_nazwisko for p_id, p in PROWADZACY_DB.items()}
        wybrany_id = st.selectbox("Wybierz prowadzącego:", list(opcje_prof.keys()), format_func=lambda x: opcje_prof[x], index=None, placeholder="Zacznij wpisywać nazwisko...")
        context_title = PROWADZACY_DB[wybrany_id].imie_nazwisko if wybrany_id else "Wybierz osobę z listy"
    else: 
        opcje_sale = sorted(list(SALE_DB.keys()))
        wybrany_id = st.selectbox("Wybierz salę:", opcje_sale, index=None, placeholder="Wpisz numer sali...")
        context_title = f"Sali {wybrany_id}" if wybrany_id else "Wybierz salę"
        
    st.divider()
    
    st.subheader("DODATKOWE FILTRY")
    lista_prow_nazwiska = ["Wszyscy"] + [p.imie_nazwisko for p in PROWADZACY_DB.values()]
    lista_sal = ["Wszystkie"] + sorted(list(SALE_DB.keys()))
    lista_grup = ["Wszystkie"] + sorted(list(set([z.grupa_id for z in LISTA_ZAJEC])))
    
    filtr_prow = st.selectbox("Prowadzący", lista_prow_nazwiska)
    filtr_sala = st.selectbox("Sala", lista_sal)
    filtr_grupa = st.selectbox("Grupa", lista_grup)
    filtr_typ = st.selectbox("Typ zajęć", ["Wszystkie", "Wykład", "Ćwiczenia", "Lab", "Projekt"])

    st.divider()
    st.subheader("EKSPORUJ WYNIKI")

    def wygeneruj_json_planu(lista_zajec):
        plan_wyjsciowy = []
        for z in lista_zajec:
            plan_wyjsciowy.append({
                "id_zajec": z.id,
                "przedmiot_id": getattr(z, 'przedmiot_id', z.id),
                "grupa_id": z.grupa_id,
                "prowadzacy_id": z.prowadzacy_id,
                "sala_id": z.przypisana_sala_id,
                "dzien": z.przypisany_dzien,
                "start_slot": z.przypisany_start_slot,
                "czas_trwania_godz": getattr(z, 'wymagane_godziny', 1)
            })
        return json.dumps(plan_wyjsciowy, indent=4, ensure_ascii=False)

    def wygeneruj_log_kosztow(historia, czas_wykonania):
        log_lines = ["RAPORT OPTYMALIZACJI - OPTIPLAN", f"Czas wykonywania silnika (LLM + HC + SC): {czas_wykonania:.2f} s", "-"*50]
        if historia:
            for i, koszt in enumerate(historia): log_lines.append(f"Iteracja chlodzenia {i}: Punkty karne = {koszt}")
            log_lines.append("-" * 50)
            log_lines.append(f"Ostateczny, zoptymalizowany koszt planu: {historia[-1]} pkt.")
        else:
            log_lines.append("Brak historii optymalizacji.")
        return "\n".join(log_lines)

    st.download_button(label="Pobierz wygenerowany plan (JSON)", data=wygeneruj_json_planu(LISTA_ZAJEC), file_name="zoptymalizowany_plan.json", mime="application/json", use_container_width=True, key="btn_download_json")
    st.download_button(label="Pobierz log z funkcji celu (TXT)", data=wygeneruj_log_kosztow(HISTORIA_KOSZTOW, CZAS_WYKONANIA), file_name="log_optymalizacji.txt", mime="text/plain", use_container_width=True, key="btn_download_log")

def render_plan(typ_widoku, wybrany_identyfikator, tytul_naglowka):
    st.header(f"Plan zajęć - {tytul_naglowka}")
    wybrane_zajecia = []
    for zajecia in LISTA_ZAJEC:
        if typ_widoku == "Grupa" and zajecia.grupa_id != wybrany_identyfikator: continue
        if typ_widoku == "Prowadzący" and zajecia.prowadzacy_id != wybrany_identyfikator: continue
        if typ_widoku == "Sala" and zajecia.przypisana_sala_id != wybrany_identyfikator: continue
        
        prof_obj = PROWADZACY_DB.get(zajecia.prowadzacy_id)
        if filtr_prow != "Wszyscy" and (prof_obj and prof_obj.imie_nazwisko != filtr_prow): continue
        if filtr_sala != "Wszystkie" and zajecia.przypisana_sala_id != filtr_sala: continue
        if filtr_grupa != "Wszystkie" and zajecia.grupa_id != filtr_grupa: continue
        if filtr_typ != "Wszystkie" and filtr_typ.lower() not in getattr(zajecia, 'wymagany_typ_sali', '').lower(): continue
        wybrane_zajecia.append(zajecia)

    zajecia_map = {}
    for z in wybrane_zajecia:
        pl_dzien = DAY_MAP_ENG_TO_PL.get(z.przypisany_dzien)
        if pl_dzien: zajecia_map[(z.przypisany_start_slot, pl_dzien)] = z

    skip_slots = set()
    html = '<table class="custom-plan-table"><thead><tr><th>Godzina</th><th>Pon</th><th>Wt</th><th>Śr</th><th>Czw</th><th>Pt</th></tr></thead><tbody>'
    for h in HOURS_RANGE:
        html += f'<tr><td class="time-cell">{h:02d}:00</td>'
        for d_pl in DAYS_PL:
            if (h, d_pl) in skip_slots: continue
            zajecia = zajecia_map.get((h, d_pl))
            if zajecia:
                duration = getattr(zajecia, 'wymagane_godziny', 1)
                for offset in range(1, duration): skip_slots.add((h + offset, d_pl))
                
                typ_lower = getattr(zajecia, 'wymagany_typ_sali', '').lower()
                if "wykł" in typ_lower or "wyklad" in typ_lower or "zs" in typ_lower: kolor_boxa, skrot_typu = "#0284c7", "WYK"
                elif "ćwi" in typ_lower or "cwi" in typ_lower or "cwl" in typ_lower: kolor_boxa, skrot_typu = "#8b5cf6", "ĆW"
                elif "lab" in typ_lower: kolor_boxa, skrot_typu = "#10b981", "LAB"
                elif "proj" in typ_lower: kolor_boxa, skrot_typu = "#f59e0b", "PRO"
                else: kolor_boxa, skrot_typu = "#f43f5e", "ZAJ"
                
                h_start, h_koniec = zajecia.przypisany_start_slot, zajecia.przypisany_start_slot + duration
                prof_obj = PROWADZACY_DB.get(zajecia.prowadzacy_id)
                przedmiot_obj = PRZEDMIOTY_DB.get(getattr(zajecia, 'przedmiot_id', ''))
                
                html += f'<td rowspan="{duration}" style="padding: 4px; vertical-align: top;"><div style="border: 1px solid #cbd5e1; border-radius: 8px; overflow: hidden; box-shadow: 0 3px 6px rgba(0,0,0,0.1); height: 100%; display: flex; flex-direction: column;">'
                html += f'<div style="background-color: {kolor_boxa}; color: white; padding: 8px 10px;"><div style="display: flex; justify-content: space-between; font-weight: 800; font-size: 14px; text-shadow: 1px 1px 2px rgba(0,0,0,0.2);"><span>{h_start}:00-{h_koniec}:00</span><span>{skrot_typu}</span></div></div>'
                html += f'<div style="background-color: #f8fafc; color: #334155; padding: 8px 10px; flex-grow: 1; border-top: 1px solid #e2e8f0;">'
                html += f'<div style="font-weight: 700; color: #0f172a; font-size: 14px; margin-bottom: 4px;">{przedmiot_obj.nazwa if przedmiot_obj else getattr(zajecia, "przedmiot_id", "Nieznany")}</div>'
                html += f'<div style="color: #1e293b; font-size: 13px; font-weight: 600;">{prof_obj.imie_nazwisko if prof_obj else zajecia.prowadzacy_id}</div>'
                html += f'<div style="font-weight: 700; color: {kolor_boxa}; margin-top: 4px; font-size: 13px;">{zajecia.przypisana_sala_id}</div>'
                html += f'</div></div></td>'
            else:
                html += '<td style="color: #cbd5e1; text-align: center; vertical-align: middle; font-size: 16px;">—</td>'
        html += '</tr>'
    html += '</tbody></table>'
    st.markdown(html, unsafe_allow_html=True)

def render_optimization():
    st.header("Postęp optymalizacji - Widok ogólny")
    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader("Przebieg funkcji celu")
        if HISTORIA_KOSZTOW:
            # Przygotuj wartości do wykresu. Skala logarytmiczna nie obsługuje wartości <= 0,
            # więc gdy występują zera/ujemne wartości, użyjemy skali liniowej.
            iters = list(range(len(HISTORIA_KOSZTOW)))
            try:
                y_vals = np.array(HISTORIA_KOSZTOW, dtype=float)
            except Exception:
                # Jeśli konwersja się nie powiedzie, pokazujemy informację i przerywamy rysowanie
                st.warning("Nieprawidłowy format historii kosztów — oczekiwano listy liczb.")
                return

            use_log = np.all(y_vals > 0)
            y_plot = y_vals.copy()
            if not use_log:
                # minimalne przesunięcie by uniknąć problemów z zerami przy wyświetlaniu wartości
                y_plot = y_plot

            fig_opt = go.Figure(go.Scatter(x=iters, y=y_plot, name="Punkty karne (SC)", line=dict(color='#0284c7', width=3)))
            yaxis_title = "Punkty karne (log)" if use_log else "Punkty karne"
            fig_opt.update_layout(height=300, margin=dict(l=20, r=20, t=20, b=20), xaxis_title="Iteracje funkcji", yaxis_title=yaxis_title, yaxis_type="log" if use_log else "linear", font=dict(size=16))
            st.plotly_chart(fig_opt, use_container_width=True)
        else:
            st.info("Brak historii optymalizacji.")

    with col2:
        st.subheader("Zaspokojenie ograniczeń (HC)")
        fig_gauge = go.Figure(go.Indicator(mode="gauge+number", value=100 if SUKCES else 0, title={'text': "Sukces (%)"}, gauge={'axis': {'range': [0, 100]}, 'bar': {'color': "#10b981"}}))
        fig_gauge.update_layout(height=300, margin=dict(l=20, r=20, t=20, b=20), font=dict(size=14))
        st.plotly_chart(fig_gauge, use_container_width=True)
        
    st.divider()
    col3, col4 = st.columns(2)
    with col3:
        st.subheader("Struktura i zajętość sal")
        dane_sal = [{"Sala": s_id, "Typ": s.typ, "Pojemność": s.pojemnosc, "Obciążenie (godz)": sum([getattr(z, 'wymagane_godziny', 1) for z in LISTA_ZAJEC if z.przypisana_sala_id == s_id])} for s_id, s in SALE_DB.items()]
        fig_tree = px.treemap(pd.DataFrame(dane_sal), path=[px.Constant("Wszystkie Sale"), 'Typ', 'Sala'], values='Pojemność', color='Obciążenie (godz)', color_continuous_scale='Spectral', labels={'Obciążenie (godz)': 'Godz/tydz'})
        fig_tree.update_traces(root_color="lightgrey")
        fig_tree.update_layout(height=450, margin=dict(t=20, l=10, r=10, b=10), font=dict(size=15))
        st.plotly_chart(fig_tree, use_container_width=True)
        
    with col4:
        st.subheader("Obciążenie prowadzących (godz/tydz)")
        imiona_prof = [p.imie_nazwisko for p in PROWADZACY_DB.values()]
        godziny_przydzielone = [0.0] * len(imiona_prof)
        for zajecia in LISTA_ZAJEC:
            if p_obj := PROWADZACY_DB.get(zajecia.prowadzacy_id):
                godziny_przydzielone[list(PROWADZACY_DB.keys()).index(zajecia.prowadzacy_id)] += getattr(zajecia, 'wymagane_godziny', 1)
                
        df_prof = pd.DataFrame({'Profesor': imiona_prof, 'Godziny': godziny_przydzielone}).sort_values(by='Godziny', ascending=True)
        with st.container(height=450, border=True):
            fig_bar = px.bar(df_prof, x='Godziny', y='Profesor', orientation='h', text='Godziny', color='Godziny', color_continuous_scale='Portland', labels={'Godziny':'Średnio godzin', 'Profesor':''})
            fig_bar.update_traces(texttemplate='%{text:.1f}h', textposition='outside')
            fig_bar.add_vline(x=12, line_dash="dash", line_color="red", annotation_text="Max 12h")
            fig_bar.add_vline(x=8, line_dash="dash", line_color="orange", annotation_text="Min 8h", annotation_position="bottom left")
            fig_bar.update_layout(height=max(400, len(imiona_prof) * 35), margin=dict(l=10, r=30, t=10, b=10), coloraxis_showscale=False, font=dict(size=14))
            st.plotly_chart(fig_bar, use_container_width=True)

def render_statistics():
    st.header("Raport statystyczny")
    st.markdown("Szczegółowe dane liczbowe i wykazy w formie tabelarycznej.")
    
    l_zajec = len(LISTA_ZAJEC)
    naruszenia_twarde = 0 if SUKCES else len([z for z in LISTA_ZAJEC if getattr(z, 'przypisany_dzien', None) is None])
    koszt_koncowy = HISTORIA_KOSZTOW[-1] if HISTORIA_KOSZTOW else 0
    spadek_kosztu = (HISTORIA_KOSZTOW[0] - HISTORIA_KOSZTOW[-1]) if HISTORIA_KOSZTOW else 0
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Łączna liczba zajęć", f"{l_zajec}")
    c2.metric("Naruszenia twarde", f"{naruszenia_twarde}", "0", delta_color="off")
    c3.metric("Punkty Karne (SC)", f"{koszt_koncowy}", f"-{spadek_kosztu}")
    c4.metric("Czas ostatniej optymalizacji", f"{CZAS_WYKONANIA:.2f} s")
    
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Wykaz Prowadzących")
        with st.container(height=500, border=True):
            dane_prow = [{"Imię i nazwisko": p.imie_nazwisko, "Godz (tyg)": f"{s:.1f}", "Limit": 12, "Status": "Ok" if s <= 12 else "!"} for p_id, p in PROWADZACY_DB.items() for s in [sum([getattr(z, 'wymagane_godziny', 1) for z in LISTA_ZAJEC if z.prowadzacy_id == p_id])]]
            st.dataframe(pd.DataFrame(dane_prow), use_container_width=True, hide_index=True)
            
    with col2:
        st.subheader("Wykaz Sal")
        with st.container(height=500, border=True):
            dane_sal = [{"Sala": s_id, "Typ": s.typ, "Poj": s.pojemnosc, "Zajętość (godz)": f"{zaj:.1f}"} for s_id, s in SALE_DB.items() for zaj in [sum([getattr(z, 'wymagane_godziny', 1) for z in LISTA_ZAJEC if z.przypisana_sala_id == s_id])]]
            st.dataframe(pd.DataFrame(dane_sal), use_container_width=True, hide_index=True)

tab_plan, tab_opt, tab_stat = st.tabs(["Plan zajęć", "Optymalizacja", "Raport statystyczny"])
with tab_plan: render_plan(perspektywa_typ, wybrany_id, context_title)
with tab_opt: render_optimization()
with tab_stat: render_statistics()
