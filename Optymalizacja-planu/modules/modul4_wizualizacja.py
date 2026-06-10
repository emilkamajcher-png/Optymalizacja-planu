import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import numpy as np
import time
import json

from modules import modul1_parser
from modules import modul2_optymalizacja
from modules import modul3_llm

st.set_page_config(layout="wide", page_title="OptiPlan - Optymalizacja Planu")

st.markdown("""
    <style>
    .stApp { background-color: #f4f7f9; }
    div[data-testid="stVerticalBlock"] > div:has(div.element-container) {
        background-color: white;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        margin-bottom: 20px;
    }
    table.custom-plan-table {
        width: 100%; border-collapse: collapse; font-family: 'Segoe UI', sans-serif; table-layout: fixed;
    }
    table.custom-plan-table th {
        background-color: #eaeef2; color: #334155; font-weight: 600; padding: 14px; border: 1px solid #cbd5e1; text-align: center; width: 18%;
    }
    table.custom-plan-table th:first-child { width: 10%; }
    table.custom-plan-table td {
        border: 1px solid #cbd5e1; height: 80px; padding: 4px; vertical-align: top; background-color: #ffffff;
    }
    .time-cell {
        background-color: #f8fafc; font-weight: bold; color: #64748b; text-align: center !important; vertical-align: middle !important; font-size: 13px;
    }
    .stTable { border: none !important; }
    </style>
    """, unsafe_allow_html=True)

HOURS_RANGE = range(8, 20)
HOURS_LABELS = [f"{h:02d}:00" for h in HOURS_RANGE]
DAY_MAP_ENG_TO_PL = {"Mon": "Pon", "Tue": "Wt", "Wed": "Śr", "Thu": "Czw", "Fri": "Pt"}
DAYS_PL = ["Pon", "Wt", "Śr", "Czw", "Pt"]

@st.cache_data
def uruchom_silnik_i_pobierz_plan(sciezka_danych):
    start = time.time()
    
    with open(sciezka_danych, 'r', encoding='utf-8') as plik:
        surowe_dane = json.load(plik)
        
    # Uruchamiamy moduł 3 (AI). Adapter został USUNIĘTY, 
    # bo modul3 sam wkleja gotową macierz do 'availability_matrix'!
    dane_po_llm = modul3_llm.przeanalizuj_preferencje(surowe_dane, tryb_offline=False)
        
    prowadzacy_db, sale_db, przedmioty_db = modul1_parser.zbuduj_baze_obiektow(dane_po_llm)
    
    stan = modul2_optymalizacja.StanPlanu()
    algorytm = modul2_optymalizacja.AlgorytmKonstruktywny(stan, prowadzacy_db, sale_db, przedmioty_db)
    sukces = algorytm.rozwiaz()
    
    historia = []
    if sukces:
        optymalizator = modul2_optymalizacja.AlgorytmWyzarzania(stan, algorytm.lista_zajec, prowadzacy_db, sale_db)
        historia = optymalizator.optymalizuj(temp_pocz=1000.0, temp_konc=1.0, alfa=0.95, iter_na_temp=150)
        
    execution_time = time.time() - start
    return sukces, algorytm.lista_zajec, prowadzacy_db, sale_db, przedmioty_db, execution_time, historia

sciezka_bazy = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sciezka_do_danych = os.path.join(sciezka_bazy, "data", "dane_testowe.json")

with st.spinner("Sztuczna Inteligencja (Bielik) analizuje paczkę preferencji i układa plan..."):
    SUKCES, LISTA_ZAJEC, PROWADZACY_DB, SALE_DB, PRZEDMIOTY_DB, CZAS_WYKONANIA, HISTORIA_KOSZTOW = uruchom_silnik_i_pobierz_plan(sciezka_do_danych)

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
        context_name = st.selectbox("Wybierz grupę:", opcje_grup if opcje_grup else ["Brak danych"], key="sel_grup_main")
        context_title = f"Grupy {context_name}"
        wybrany_id = context_name
    elif perspektywa_typ == "Prowadzący":
        opcje_prof = {p_id: p.imie_nazwisko for p_id, p in PROWADZACY_DB.items()}
        wybrany_id = st.selectbox("Wybierz prowadzącego:", list(opcje_prof.keys()), format_func=lambda x: opcje_prof[x], key="sel_prof_main")
        context_title = PROWADZACY_DB[wybrany_id].imie_nazwisko if wybrany_id else ""
    else:
        opcje_sale = sorted(list(SALE_DB.keys()))
        wybrany_id = st.selectbox("Wybierz salę:", opcje_sale if opcje_sale else ["Brak danych"], key="sel_sala_main")
        context_title = f"Sali {wybrany_id}"
        
    st.divider()
    
    st.subheader("WYBÓR TYGODNIA")
    widok_tygodnia = st.radio("Pokaż plan dla:", ["Semestr (Oba)", "Tydzień A (Nieparzysty)", "Tydzień B (Parzysty)"])
    
    st.divider()
    
    st.subheader("DODATKOWE FILTRY")
    lista_prow_nazwiska = ["Wszyscy"] + [p.imie_nazwisko for p in PROWADZACY_DB.values()]
    lista_sal = ["Wszystkie"] + sorted(list(SALE_DB.keys()))
    lista_grup = ["Wszystkie"] + sorted(list(set([z.grupa_id for z in LISTA_ZAJEC])))
    
    filtr_prow = st.selectbox("Prowadzący", lista_prow_nazwiska, key="filter_prow")
    filtr_sala = st.selectbox("Sala", lista_sal, key="filter_sala")
    filtr_grupa = st.selectbox("Grupa", lista_grup, key="filter_grupa")
    filtr_typ = st.selectbox("Typ zajęć", ["Wszystkie", "Wykład", "Ćwiczenia", "Lab", "Projekt"], key="filter_typ")

def render_plan(typ_widoku, wybrany_identyfikator, tytul_naglowka):
    st.header(f"Plan zajęć - Widok: {tytul_naglowka}")
    st.caption(f"Aktualny filtr okresu: {widok_tygodnia}")
    
    wybrane_zajecia = []
    for zajecia in LISTA_ZAJEC:
        if typ_widoku == "Grupa" and zajecia.grupa_id != wybrany_identyfikator: continue
        if typ_widoku == "Prowadzący" and zajecia.prowadzacy_id != wybrany_identyfikator: continue
        if typ_widoku == "Sala" and zajecia.przypisana_sala_id != wybrany_identyfikator: continue
        
        tydzien_zajec = getattr(zajecia, 'przypisany_tydzien', 'AB')
        if widok_tygodnia == "Tydzień A (Nieparzysty)" and tydzien_zajec == 'B': continue
        if widok_tygodnia == "Tydzień B (Parzysty)" and tydzien_zajec == 'A': continue
        
        prof_obj = PROWADZACY_DB.get(zajecia.prowadzacy_id)
        if filtr_prow != "Wszyscy" and (prof_obj and prof_obj.imie_nazwisko != filtr_prow): continue
        if filtr_sala != "Wszystkie" and zajecia.przypisana_sala_id != filtr_sala: continue
        if filtr_grupa != "Wszystkie" and zajecia.grupa_id != filtr_grupa: continue
        if filtr_typ != "Wszystkie" and filtr_typ.lower() not in getattr(zajecia, 'wymagany_typ_sali', '').lower(): continue
            
        wybrane_zajecia.append(zajecia)

    zajecia_map = {}
    for z in wybrane_zajecia:
        pl_dzien = DAY_MAP_ENG_TO_PL.get(z.przypisany_dzien)
        if pl_dzien:
            zajecia_map[(z.przypisany_start_slot, pl_dzien)] = z

    skip_slots = set()
    
    html = '<table class="custom-plan-table">'
    html += '<thead><tr><th>Godzina</th><th>Pon</th><th>Wt</th><th>Śr</th><th>Czw</th><th>Pt</th></tr></thead>'
    html += '<tbody>'
    
    for h in HOURS_RANGE:
        html += f'<tr><td class="time-cell">{h:02d}:00</td>'
        
        for d_pl in DAYS_PL:
            if (h, d_pl) in skip_slots:
                continue
                
            zajecia = zajecia_map.get((h, d_pl))
            
            if zajecia:
                duration = zajecia.wymagane_godziny
                for offset in range(1, duration):
                    skip_slots.add((h + offset, d_pl))
                
                typ_lower = getattr(zajecia, 'wymagany_typ_sali', '').lower()
                if "wykł" in typ_lower or "wyklad" in typ_lower or "zs" in typ_lower: kolor_boxa, skrot_typu = "#0e7373", "WYK"
                elif "ćwi" in typ_lower or "cwi" in typ_lower or "cwl" in typ_lower: kolor_boxa, skrot_typu = "#5b3b70", "ĆW"
                elif "lab" in typ_lower: kolor_boxa, skrot_typu = "#2b5c8f", "LAB"
                elif "proj" in typ_lower: kolor_boxa, skrot_typu = "#b25e1d", "PRO"
                else: kolor_boxa, skrot_typu = "#1e293b", "ZAJ"
                
                h_start = zajecia.przypisany_start_slot
                h_koniec = h_start + duration
                czas_kafelka = f"{h_start}:00-{h_koniec}:00"
                sala_info = zajecia.przypisana_sala_id
                prof_obj = PROWADZACY_DB.get(zajecia.prowadzacy_id)
                prof_nazwisko = prof_obj.imie_nazwisko if prof_obj else zajecia.prowadzacy_id
                
                html += f'<td rowspan="{duration}" style="padding: 4px; vertical-align: top;">'
                html += f'<div style="border: 1px solid #cbd5e1; border-radius: 6px; overflow: hidden; box-shadow: 0 2px 5px rgba(0,0,0,0.08); height: 100%; display: flex; flex-direction: column;">'
                html += f'<div style="background-color: {kolor_boxa}; color: white; padding: 6px 10px;">'
                html += f'<div style="display: flex; justify-content: space-between; font-weight: bold; font-size: 10px; opacity: 0.9;">'
                html += f'<span>{czas_kafelka}</span><span>{skrot_typu}</span>'
                html += f'</div></div>'
                html += f'<div style="background-color: #ffffff; color: #334155; padding: 6px 10px; flex-grow: 1; border-top: 1px solid #e2e8f0; font-size: 11px;">'
                html += f'<div style="color: #475569; font-size: 13px; font-weight: 500;">{prof_nazwisko}</div>'
                html += f'<div style="font-weight: 600; color: #1e293b; margin-top: 2px;">{sala_info}</div>'
                html += f'</div></div></td>'
            else:
                html += '<td style="color: #cbd5e1; text-align: center; vertical-align: middle; font-size: 14px;">—</td>'
                
        html += '</tr>'
    html += '</tbody></table>'
    st.markdown(html, unsafe_allow_html=True)

def render_optimization():
    st.header("Postęp optymalizacji - Widok ogólny")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Przebieg funkcji celu (Algorytm Wyżarzania)")
        if HISTORIA_KOSZTOW:
            iters = list(range(len(HISTORIA_KOSZTOW)))
            fig_opt = go.Figure()
            fig_opt.add_trace(go.Scatter(x=iters, y=HISTORIA_KOSZTOW, name="Punkty karne (SC)", line=dict(color='#1f77b4', width=3)))
            fig_opt.update_layout(height=300, margin=dict(l=20, r=20, t=20, b=20), xaxis_title="Iteracje chłodzenia", yaxis_title="Koszt planu (im niżej, tym lepiej)")
            st.plotly_chart(fig_opt, use_container_width=True)
        else:
            st.info("Brak historii optymalizacji.")

    with col2:
        st.subheader("Zaspokojenie ograniczeń (HC)")
        fig_gauge = go.Figure(go.Indicator(
            mode = "gauge+number", value = 100 if SUKCES else 0, title = {'text': "Sukces (%)"}, gauge = {'axis': {'range': [0, 100]}, 'bar': {'color': "#007bff"}}
        ))
        fig_gauge.update_layout(height=300, margin=dict(l=20, r=20, t=20, b=20))
        st.plotly_chart(fig_gauge, use_container_width=True)
        
    st.divider()
    
    col3, col4 = st.columns(2)
    
    with col3:
        st.subheader("Struktura i zajętość sal (Treemap)")
        dane_sal = []
        for s_id, s in SALE_DB.items():
            godz_A = sum([z.wymagane_godziny for z in LISTA_ZAJEC if z.przypisana_sala_id == s_id and getattr(z, 'przypisany_tydzien', 'AB') in ['AB', 'A']])
            godz_B = sum([z.wymagane_godziny for z in LISTA_ZAJEC if z.przypisana_sala_id == s_id and getattr(z, 'przypisany_tydzien', 'AB') in ['AB', 'B']])
            srednie_zajecie = (godz_A + godz_B) / 2.0
            dane_sal.append({"Sala": s_id, "Typ": s.typ, "Pojemność": s.pojemnosc, "Obciążenie (godz)": srednie_zajecie})
            
        df_sale = pd.DataFrame(dane_sal)
        fig_tree = px.treemap(
            df_sale, path=[px.Constant("Wszystkie Sale"), 'Typ', 'Sala'], values='Pojemność',
            color='Obciążenie (godz)', color_continuous_scale='Blues', labels={'Obciążenie (godz)': 'Śr. godz/tydz'}
        )
        fig_tree.update_traces(root_color="lightgrey")
        fig_tree.update_layout(height=450, margin=dict(t=20, l=10, r=10, b=10))
        st.plotly_chart(fig_tree, use_container_width=True)
        
    with col4:
        st.subheader("Obciążenie prowadzących (godz/tydz)")
        imiona_prof = [p.imie_nazwisko for p in PROWADZACY_DB.values()]
        godziny_przydzielone = [0.0] * len(imiona_prof)
        for zajecia in LISTA_ZAJEC:
            prof_obj = PROWADZACY_DB.get(zajecia.prowadzacy_id)
            if prof_obj:
                idx = list(PROWADZACY_DB.keys()).index(zajecia.prowadzacy_id)
                dodatek_godzin = zajecia.wymagane_godziny if getattr(zajecia, 'przypisany_tydzien', 'AB') == 'AB' else (zajecia.wymagane_godziny / 2.0)
                godziny_przydzielone[idx] += dodatek_godzin
                
        df_prof = pd.DataFrame({'Profesor': imiona_prof, 'Godziny': godziny_przydzielone})
        df_prof = df_prof.sort_values(by='Godziny', ascending=True)
        
        with st.container(height=450, border=True):
            wewn_wysokosc = max(400, len(imiona_prof) * 35)
            fig_bar = px.bar(
                df_prof, x='Godziny', y='Profesor', orientation='h', text='Godziny', color='Godziny',
                color_continuous_scale='teal', labels={'Godziny':'Średnio godzin', 'Profesor':''}
            )
            fig_bar.update_traces(texttemplate='%{text:.1f}h', textposition='outside')
            fig_bar.add_vline(x=12, line_dash="dash", line_color="red", annotation_text="Max 12h")
            fig_bar.add_vline(x=8, line_dash="dash", line_color="orange", annotation_text="Min 8h", annotation_position="bottom left")
            fig_bar.update_layout(height=wewn_wysokosc, margin=dict(l=10, r=30, t=10, b=10), coloraxis_showscale=False)
            st.plotly_chart(fig_bar, use_container_width=True)

def render_statistics():
    st.header("Raport statystyczny")
    st.markdown("Szczegółowe dane liczbowe i wykazy w formie tabelarycznej.")
    
    l_zajec = len(LISTA_ZAJEC)
    naruszenia_twarde = 0 if SUKCES else len([z for z in LISTA_ZAJEC if z.przypisany_dzien is None])
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
        st.subheader("Wykaz Prowadzących (Średnie obciążenie)")
        dane_prow = []
        for p_id, p in PROWADZACY_DB.items():
            godz_A = sum([z.wymagane_godziny for z in LISTA_ZAJEC if z.prowadzacy_id == p_id and getattr(z, 'przypisany_tydzien', 'AB') in ['AB', 'A']])
            godz_B = sum([z.wymagane_godziny for z in LISTA_ZAJEC if z.prowadzacy_id == p_id and getattr(z, 'przypisany_tydzien', 'AB') in ['AB', 'B']])
            srednio_na_tydzien = (godz_A + godz_B) / 2.0
            dane_prow.append({"Imię i nazwisko": p.imie_nazwisko, "Liczba godzin (śr/tyg)": f"{srednio_na_tydzien:.1f}", "Maks. limit (tyg)": 12, "Status": "Ok" if 8 <= srednio_na_tydzien <= 12 else "Poza normą"})
        st.dataframe(pd.DataFrame(dane_prow), use_container_width=True, hide_index=True)
        
    with col2:
        st.subheader("Wykaz Sal")
        dane_sal = []
        for s_id, s in SALE_DB.items():
            godz_A = sum([z.wymagane_godziny for z in LISTA_ZAJEC if z.przypisana_sala_id == s_id and getattr(z, 'przypisany_tydzien', 'AB') in ['AB', 'A']])
            godz_B = sum([z.wymagane_godziny for z in LISTA_ZAJEC if z.przypisana_sala_id == s_id and getattr(z, 'przypisany_tydzien', 'AB') in ['AB', 'B']])
            srednie_zajecie_sali = (godz_A + godz_B) / 2.0
            dane_sal.append({"Sala": s_id, "Typ": s.typ, "Pojemność": s.pojemnosc, "Zajętość (śr. godz)": f"{srednie_zajecie_sali:.1f}"})
        st.dataframe(pd.DataFrame(dane_sal), use_container_width=True, hide_index=True)

tab_plan, tab_opt, tab_stat = st.tabs(["Plan zajęć", "Optymalizacja", "Raport statystyczny"])
with tab_plan: render_plan(perspektywa_typ, wybrany_id, context_title)
with tab_opt: render_optimization()
with tab_stat: render_statistics()