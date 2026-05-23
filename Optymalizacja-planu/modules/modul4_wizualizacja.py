import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import numpy as np
import time
import json

# Importujemy nasze moduły
from modules import modul1_parser
from modules import modul2_optymalizacja
from modules import modul3_llm

# Konfiguracja strony
st.set_page_config(layout="wide", page_title="OptiPlan - Optymalizacja Planu")

# --- STYLE CSS ---
st.markdown("""
    <style>
    /* Tło całej aplikacji */
    .stApp { background-color: #f4f7f9; }
    
    /* Stylizacja 'kart' dla sekcji */
    div[data-testid="stVerticalBlock"] > div:has(div.element-container) {
        background-color: white;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        margin-bottom: 20px;
    }
    
    /* Ukrycie obramowania tabel */
    .stTable { border: none !important; }
    </style>
    """, unsafe_allow_html=True)

# --- MAPOWANIE CZASU ---
HOURS_RANGE = range(8, 20)
HOURS_LABELS = [f"{h:02d}:00" for h in HOURS_RANGE]
DAY_MAP_ENG_TO_PL = {"Mon": "Pon", "Tue": "Wt", "Wed": "Śr", "Thu": "Czw", "Fri": "Pt"}
DAYS_PL = ["Pon", "Wt", "Śr", "Czw", "Pt"]

# --- URUCHOMIENIE SILNIKA ---
@st.cache_data
def uruchom_silnik_i_pobierz_plan(sciezka_danych):
    start = time.time()
    
    with open(sciezka_danych, 'r', encoding='utf-8') as plik:
        surowe_dane = json.load(plik)
        
    # --- ZASTĘPSTWO ZA BRAKUJĄCĄ FUNKCJĘ W MODULE LLM ---
    dane_po_llm = surowe_dane.copy()
    for instructor in dane_po_llm.get('instructors', []):
        text = instructor.get('preferences_text', '')
        if text:
            # Wywołanie bezpośrednio dostępnej funkcji w modul3_llm
            matryca = modul3_llm.call_bielik_matrix_api(text)
            if matryca is None:
                matryca = modul3_llm.get_default_matrix()
            instructor['availability_matrix'] = matryca
            time.sleep(1) # Zabezpieczenie przed limitem API
        else:
            instructor['availability_matrix'] = modul3_llm.get_default_matrix()
    # ---------------------------------------------------
        
    # Parser wczytuje dane wzbogacone przez model AI
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

# --- ŁADOWANIE Z KOMUNIKATEM DLA PROWADZĄCEGO ---
with st.spinner("Sztuczna Inteligencja (Bielik) analizuje dane tekstowe i układa zoptymalizowany plan. To potrwa chwilę..."):
    SUKCES, LISTA_ZAJEC, PROWADZACY_DB, SALE_DB, PRZEDMIOTY_DB, CZAS_WYKONANIA, HISTORIA_KOSZTOW = uruchom_silnik_i_pobierz_plan("data/dane_testowe.json")

# --- SIDEBAR (Filtry i wybór perspektywy) ---
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
        context_name = st.selectbox("Wybierz grupę:", opcje_grup, key="sel_grup_main")
        context_title = f"Grupy {context_name}"
        wybrany_id = context_name
    elif perspektywa_typ == "Prowadzący":
        opcje_prof = {p_id: p.imie_nazwisko for p_id, p in PROWADZACY_DB.items()}
        wybrany_id = st.selectbox("Wybierz prowadzącego:", list(opcje_prof.keys()), format_func=lambda x: opcje_prof[x], key="sel_prof_main")
        context_title = PROWADZACY_DB[wybrany_id].imie_nazwisko if wybrany_id else ""
    else:
        opcje_sale = sorted(list(SALE_DB.keys()))
        wybrany_id = st.selectbox("Wybierz salę:", opcje_sale, key="sel_sala_main")
        context_title = f"Sali {wybrany_id}"
        
    st.divider()
    
    st.subheader("DODATKOWE FILTRY")
    lista_prow_nazwiska = ["Wszyscy"] + [p.imie_nazwisko for p in PROWADZACY_DB.values()]
    lista_sal = ["Wszystkie"] + sorted(list(SALE_DB.keys()))
    lista_grup = ["Wszystkie"] + sorted(list(set([z.grupa_id for z in LISTA_ZAJEC])))
    
    filtr_prow = st.selectbox("Prowadzący", lista_prow_nazwiska, key="filter_prow")
    filtr_sala = st.selectbox("Sala", lista_sal, key="filter_sala")
    filtr_grupa = st.selectbox("Grupa", lista_grup, key="filter_grupa")
    filtr_typ = st.selectbox("Typ zajęć", ["Wszystkie", "Wykład", "Ćwiczenia", "Lab", "Projekt"], key="filter_typ")
    
    if st.button("Zastosuj filtry", type="primary"):
        st.success("Zastosowano filtry!")
    st.button("Wyczyść filtry")

# --- FUNKCJE RENDERUJĄCE WIDOKI ---

def render_plan(typ_widoku, wybrany_identyfikator, tytul_naglowka):
    st.header(f"Plan zajęć - Widok: {tytul_naglowka}")
    
    macierz_planu = {dzien: ["—"] * len(HOURS_RANGE) for d_eng, dzien in DAY_MAP_ENG_TO_PL.items()}
    df_plan = pd.DataFrame(macierz_planu, index=HOURS_LABELS)
    godzina_do_indeksu = {h: i for i, h in enumerate(HOURS_RANGE)}
    
    for zajecia in LISTA_ZAJEC:
        if typ_widoku == "Grupa" and zajecia.grupa_id != wybrany_identyfikator: continue
        if typ_widoku == "Prowadzący" and zajecia.prowadzacy_id != wybrany_identyfikator: continue
        if typ_widoku == "Sala" and zajecia.przypisana_sala_id != wybrany_identyfikator: continue
        
        prof_obj = PROWADZACY_DB.get(zajecia.prowadzacy_id)
        if filtr_prow != "Wszyscy" and (prof_obj and prof_obj.imie_nazwisko != filtr_prow): continue
        if filtr_sala != "Wszystkie" and zajecia.przypisana_sala_id != filtr_sala: continue
        if filtr_grupa != "Wszystkie" and zajecia.grupa_id != filtr_grupa: continue
        if filtr_typ != "Wszystkie":
            if filtr_typ.lower() not in zajecia.wymagany_typ_sali.lower(): continue

        pl_dzien = DAY_MAP_ENG_TO_PL.get(zajecia.przypisany_dzien)
        if not pl_dzien: continue
        
        idx_start = godzina_do_indeksu.get(zajecia.przypisany_start_slot)
        
        for offset in range(zajecia.wymagane_godziny):
            if idx_start is not None and (idx_start + offset) < len(HOURS_LABELS):
                prof_nazwisko = prof_obj.imie_nazwisko if prof_obj else zajecia.prowadzacy_id
                info_text = f"{zajecia.przedmiot_id}, \nProwadzący: {prof_nazwisko}, \nSala: {zajecia.przypisana_sala_id}"
                df_plan.loc[HOURS_LABELS[idx_start + offset], pl_dzien] = info_text
                
    st.table(df_plan)


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
            mode = "gauge+number",
            value = 100 if SUKCES else 0,
            title = {'text': "Sukces (%)"},
            gauge = {'axis': {'range': [0, 100]}, 'bar': {'color': "#007bff"}}
        ))
        fig_gauge.update_layout(height=300, margin=dict(l=20, r=20, t=20, b=20))
        st.plotly_chart(fig_gauge, use_container_width=True)
        
    st.divider()
    
    col3, col4 = st.columns(2)
    
    with col3:
        st.subheader("Wykorzystanie sal (Heatmapa)")
        nazwy_sal = list(SALE_DB.keys())
        macierz_heat = np.zeros((len(nazwy_sal), len(DAYS_PL)))
        
        for zajecia in LISTA_ZAJEC:
            if zajecia.przypisana_sala_id in nazwy_sal:
                s_idx = nazwy_sal.index(zajecia.przypisana_sala_id)
                d_pl = DAY_MAP_ENG_TO_PL.get(zajecia.przypisany_dzien)
                if d_pl in DAYS_PL:
                    d_idx = DAYS_PL.index(d_pl)
                    macierz_heat[s_idx, d_idx] += zajecia.wymagane_godziny
                    
        fig_heat = px.imshow(macierz_heat, x=DAYS_PL, y=nazwy_sal, color_continuous_scale='Blues', labels=dict(x="Dzień", y="Sala", color="Godziny"))
        fig_heat.update_layout(height=300, margin=dict(l=20, r=20, t=20, b=20))
        st.plotly_chart(fig_heat, use_container_width=True)
        
    with col4:
        st.subheader("Obciążenie prowadzących")
        imiona_prof = [p.imie_nazwisko for p in PROWADZACY_DB.values()]
        godziny_przydzielone = [0] * len(imiona_prof)
        
        for zajecia in LISTA_ZAJEC:
            prof_obj = PROWADZACY_DB.get(zajecia.prowadzacy_id)
            if prof_obj:
                idx = list(PROWADZACY_DB.keys()).index(zajecia.prowadzacy_id)
                godziny_przydzielone[idx] += zajecia.wymagane_godziny
                
        fig_bar = px.bar(x=godziny_przydzielone, y=imiona_prof, orientation='h', labels={'x':'Suma godzin w tygodniu', 'y':''}, color_discrete_sequence=['#007bff'])
        fig_bar.update_layout(height=300, margin=dict(l=20, r=20, t=20, b=20))
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
        st.subheader("Wykaz Prowadzących")
        dane_prow = []
        for p_id, p in PROWADZACY_DB.items():
            godz_przydzielone = sum([z.wymagane_godziny for z in LISTA_ZAJEC if z.prowadzacy_id == p_id])
            dane_prow.append({
                "Imię i nazwisko": p.imie_nazwisko,
                "Liczba godzin (tyg)": godz_przydzielone,
                "Pensum": p.limit_slotow_tydzien,
                "Status": "Ok" if godz_przydzielone <= p.limit_slotow_tydzien else "Przekroczone"
            })
        st.dataframe(pd.DataFrame(dane_prow), use_container_width=True, hide_index=True)
        
    with col2:
        st.subheader("Wykaz Sal")
        dane_sal = []
        for s_id, s in SALE_DB.items():
            godz_sala = sum([z.wymagane_godziny for z in LISTA_ZAJEC if z.przypisana_sala_id == s_id])
            dane_sal.append({
                "Sala": s_id,
                "Typ": s.typ,
                "Pojemność": s.pojemnosc,
                "Zajętość (godz)": godz_sala
            })
        st.dataframe(pd.DataFrame(dane_sal), use_container_width=True, hide_index=True)


# --- GŁÓWNE ZAKŁADKI APLIKACJI ---
tab_plan, tab_opt, tab_stat = st.tabs(["Plan zajęć", "Optymalizacja", "Raport statystyczny"])

with tab_plan:
    render_plan(perspektywa_typ, wybrany_id, context_title)

with tab_opt:
    render_optimization()

with tab_stat:
    render_statistics()
