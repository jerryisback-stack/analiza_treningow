import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import google.generativeai as genai 

# --- KONFIGURACJA ---
# Twój oficjalny klucz API trenera (Jarek SK Team)
COACH_API_KEY = "236evlzcl4eiiqhsm9uciid2u" 
# ID Twojego zawodnika (Jarek Malinowski)
ATHLETE_ID = "i602684" 

st.set_page_config(page_title="CoachPro Dashboard", layout="wide")

# --- FUNKCJE API ---
def ms_to_pace(ms):
    if not ms or ms <= 0 or pd.isna(ms): return "-"
    pace_sec = 1000 / ms
    return f"{int(pace_sec // 60)}:{int(pace_sec % 60):02d}"

@st.cache_data(ttl=600)
def pobierz_liste_podopiecznych():
    url = "https://intervals.icu/api/v1/athletes"
    res = requests.get(url, auth=('API_KEY', COACH_API_KEY))
    if res.status_code == 200:
        return res.json()
    else:
        st.sidebar.error(f"🔴 Błąd pobierania listy podopiecznych: {res.status_code}")
        st.sidebar.write("Treść błędu:", res.text)
        return None

@st.cache_data(ttl=600)
def pobierz_liste_aktywnosci(athlete_id):
    url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/activities"
    res = requests.get(url, auth=('API_KEY', COACH_API_KEY), params={'oldest': '2026-01-01'})
    if res.status_code != 200:
        st.sidebar.error(f"🔴 Błąd API (Aktywności): {res.status_code}")
        return None
    return pd.DataFrame(res.json())

@st.cache_data(ttl=600)
def pobierz_wellness(athlete_id):
    url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/wellness"
    res = requests.get(url, auth=('API_KEY', COACH_API_KEY), params={'oldest': '2026-01-01'})
    if res.status_code != 200:
        st.sidebar.error(f"🔴 Błąd API (Wellness): {res.status_code}")
        return None
    return pd.DataFrame(res.json())

def pobierz_detale_aktywnosci(activity_id):
    url = f"https://intervals.icu/api/v1/activity/{activity_id}?intervals=true"
    res = requests.get(url, auth=('API_KEY', COACH_API_KEY))
    return res.json() if res.status_code == 200 else None

# --- KOMPONENTY DASHBOARDU ---
def renderuj_dashboard(df):
    col1, col2, col3 = st.columns(3)
    col1.metric("Fitness (CTL)", int(df['icu_ctl'].fillna(0).iloc[-1]) if 'icu_ctl' in df else 0)
    col2.metric("TSS (30 dni)", int(df.tail(30)['icu_training_load'].sum()))
    col3.metric("Liczba treningów", len(df))
    
    st.subheader("📈 Wykres obciążenia (PMC)")
    if 'icu_ctl' in df.columns:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df['start_date_local'], y=df['icu_ctl'], name='Fitness (CTL)', fill='tozeroy'))
        fig.add_trace(go.Scatter(x=df['start_date_local'], y=df['icu_atl'], name='Fatigue (ATL)', line=dict(dash='dot')))
        st.plotly_chart(fig, use_container_width=True)

# --- ZAAWANSOWANE ---
def renderuj_zaawansowane(df, df_wellness):
    st.subheader("🤖 Analiza Zaawansowana")
    
    st.markdown("#### 📅 Zakres analizy danych")
    min_date_limit = df['start_date_local'].min().date() if not df.empty else datetime.now().date() - timedelta(days=90)
    max_date_limit = df['start_date_local'].max().date() if not df.empty else datetime.now().date()
    
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        domyslny_start = max(min_date_limit, max_date_limit - timedelta(days=60))
        data_poczatek = st.date_input("Początek zakresu:", domyslny_start, min_value=min_date_limit, max_value=max_date_limit, key="zaawansowane_start")
    with col_d2:
        data_koniec = st.date_input("Koniec zakresu:", max_date_limit, min_value=min_date_limit, max_value=max_date_limit, key="zaawansowane_koniec")
        
    st.markdown("---")

    df_filtered = df[
        (df['start_date_local'].dt.date >= data_poczatek) & 
        (df['start_date_local'].dt.date <= data_koniec)
    ].copy()

    df_wellness_filtered = None
    if df_wellness is not None and not df_wellness.empty:
        df_wellness['date_parsed'] = pd.to_datetime(df_wellness['id']).dt.date
        df_wellness_filtered = df_wellness[
            (df_wellness['date_parsed'] >= data_poczatek) & 
            (df_wellness['date_parsed'] <= data_koniec)
        ].copy()

    c1, c2 = st.columns(2)
    
    with c1:
        col_title1, col_info1 = st.columns([0.85, 0.15])
        with col_title1:
            st.write("### 💓 Regeneracja: RHR, HRV vs TSS")
        with col_info1:
            with st.popover("ℹ️"):
                st.markdown("""
                ### 💓 Jak interpretować wykres regeneracji?
                Wykres nakłada Twoje tętno spoczynkowe (**RHR**), zmienność tętna (**HRV**) oraz obciążenie treningowe (**TSS**).
                *   **Idealny stan:** HRV rośnie, a RHR spada. Dobra adaptacja.
                *   **Sygnał ostrzegawczy:** Spadek HRV połączony ze wzrostem RHR po dniach o wysokim TSS. Zawodnik potrzebuje odpoczynku.
                """)

        if df_wellness_filtered is not None:
            df_filtered['date'] = df_filtered['start_date_local'].dt.normalize()
            df_wellness_filtered['date'] = pd.to_datetime(df_wellness_filtered['id'])
            
            kolumny_wellness = ['date']
            if 'restingHR' in df_wellness_filtered.columns: kolumny_wellness.append('restingHR')
            if 'hrv' in df_wellness_filtered.columns: kolumny_wellness.append('hrv')
            
            df_merged = pd.merge(df_filtered[['date', 'icu_training_load']], 
                                 df_wellness_filtered[kolumny_wellness], 
                                 on='date', how='outer')
            
            df_merged = df_merged.sort_values('date')
            
            if 'restingHR' in df_merged.columns:
                df_merged['restingHR'] = df_merged['restingHR'].replace(0, pd.NA)
            if 'hrv' in df_merged.columns:
                df_merged['hrv'] = df_merged['hrv'].replace(0, pd.NA)

            fig_rhr = go.Figure()
            if 'restingHR' in df_merged.columns:
                fig_rhr.add_trace(go.Scatter(x=df_merged['date'], y=df_merged['restingHR'], name='RHR (Bpm)', 
                                             line=dict(color='green', width=2), connectgaps=True))
            if 'hrv' in df_merged.columns:
                fig_rhr.add_trace(go.Scatter(x=df_merged['date'], y=df_merged['hrv'], name='HRV (ms)', 
                                             line=dict(color='blue', width=2), connectgaps=True))
            
            fig_rhr.add_trace(go.Scatter(x=df_merged['date'], y=df_merged['icu_training_load'], name='TSS', 
                                         yaxis='y2', line=dict(color='orange', width=1.5)))
            
            fig_rhr.update_layout(
                yaxis=dict(title="Tętno / HRV (Zmienność)"),
                yaxis2=dict(title="TSS", overlaying='y', side='right'),
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_rhr, use_container_width=True)
        else:
            st.info("Brak danych wellness.")

        col_title2, col_info2 = st.columns([0.85, 0.15])
        with col_title2:
            st.write("### 🏃‍♂️ Wskaźnik Wydajności Aerobowej (EF)")
        with col_info2:
            with st.popover("ℹ️"):
                st.markdown("""
                ### 🏃‍♂️ Jak patrzeć na Efficiency Factor (EF)?
                Wskaźnik EF to stosunek wykonanej pracy (mocy lub tempa) do kosztu fizjologicznego (tętna średniego).
                *   **Trend rosnący (W górę):** Zawodnik przy tym samym tętnie generuje więcej watów lub biega szybciej (Lepsza ekonomia wysiłku).
                """)

        if 'icu_efficiency_factor' in df_filtered.columns:
            df_ef = df_filtered[df_filtered['icu_efficiency_factor'] > 0].copy()
            if not df_ef.empty:
                fig_ef = px.scatter(df_ef, x='start_date_local', y='icu_efficiency_factor', trendline="ols")
                st.plotly_chart(fig_ef, use_container_width=True)
            else:
                st.info("Brak danych EF (wymaga tętna i mocy/tempa w wybranym okresie).")
        else:
            st.info("Brak kolumny icu_efficiency_factor.")

    with c2:
        col_title3, col_info3 = st.columns([0.85, 0.15])
        with col_title3:
            st.write("### ⚡ Variability Index (VI)")
        with col_info3:
            with st.popover("ℹ️"):
                st.markdown("""
                ### ⚡ Jak oceniać płynność treningu (VI)?
                Wskaźnik VI to stosunek Normalized Power do mocy średniej. Pokazuje, jak bardzo "szarpany" był trening.
                *   **VI bliskie 1.0 (1.00 - 1.05):** Trening płaski, jednostajny (Prawidłowy dla tlenów, bazy, jazdy na czas).
                *   **VI wysokie (1.10 - 1.20):** Trening o charakterze zmiennym (np. zabawy biegowe, podbiegi).
                """)

        if 'icu_variability_index' in df_filtered.columns:
            if not df_filtered.empty:
                fig_vi = px.scatter(df_filtered, x='start_date_local', y='icu_variability_index', trendline="ols")
                st.plotly_chart(fig_vi, use_container_width=True)
            else:
                st.info("Brak danych w wybranym okresie.")
        else:
            st.info("Brak danych VI.")
            
        col_title4, col_info4 = st.columns([0.85, 0.15])
        with col_title4:
            st.write("### 📊 Polaryzacja: Czas w strefach (minuty)")
        with col_info4:
            with st.popover("ℹ️"):
                st.markdown("""
                ### 📊 Jak oceniać strukturę stref tętna?
                Wykres warstwowy pokazuje, ile czasu (w minutach) zawodnik spędza w strefach od Z1 do Z5 w kolejnych treningach.
                *   **Z1 i Z2:** Powinny stanowić ok. 80% całkowitej objętości (baza tlenowa i regeneracja).
                *   **Z4 i Z5:** Powinny tworzyć wyraźne, kontrolowane "szczyty" w dniach interwałowych.
                """)

        if 'icu_hr_zone_times' in df_filtered.columns:
            zones_list = []
            for _, row in df_filtered.iterrows():
                z = row['icu_hr_zone_times']
                if isinstance(z, list) and len(z) >= 5:
                    zones_list.append({
                        'date': row['start_date_local'],
                        'Z1 (Regen)': z[0]/60,
                        'Z2 (Tlen)': z[1]/60,
                        'Z3 (Tempo)': z[2]/60,
                        'Z4 (Próg)': z[3]/60,
                        'Z5 (Anatlen)': z[4]/60
                    })
            if zones_list:
                df_zones = pd.DataFrame(zones_list)
                fig_zones = px.area(df_zones, x='date', y=['Z1 (Regen)', 'Z2 (Tlen)', 'Z3 (Tempo)', 'Z4 (Próg)', 'Z5 (Anatlen)'],
                                    color_discrete_sequence=px.colors.sequential.RdBu[::-1])
                st.plotly_chart(fig_zones, use_container_width=True)
            else:
                st.info("Brak danych o strefach tętna w wybranym okresie.")
        else:
            st.info("Brak kolumny icu_hr_zone_times.")

    if df_wellness_filtered is not None and not df_wellness_filtered.empty:
        with st.expander("🕵️ Podgląd danych zdrowotnych (Wellness)"):
            st.write("Dostępne pomiary tętna i HRV w wybranym okresie:")
            st.dataframe(df_wellness_filtered[['date', 'restingHR', 'hrv']].dropna(subset=['restingHR', 'hrv'], how='all').tail(15))

def renderuj_interwaly(df, df_plan):
    st.subheader("🎯 Analiza Odcinków (Plan vs Wykonanie)")
    df_f = df[df['icu_training_load'] > 0].sort_values(by='start_date_local', ascending=False)
    
    opcje = {f"{row['start_date_local'].date()} - {row['name']}": row['id'] for _, row in df_f.iterrows()}
    wybrane = st.selectbox("Wybierz trening:", list(opcje.keys()))
    
    if wybrane:
        detale = pobierz_detale_aktywnosci(opcje[wybrane])
        if isinstance(detale, list): detale = detale[0]
        
        if detale and 'icu_intervals' in detale:
            rows = []
            for i, inter in enumerate(detale['icu_intervals']):
                speed = inter.get('average_speed', 0)
                w_step = inter.get('workout_step', {})
                target_speed = inter.get('target_speed') or w_step.get('target_speed', 0)
                
                rows.append({
                    "Nr": i+1, "Typ": inter.get('type'),
                    "Czas": f"{int(inter.get('elapsed_time',0)//60)}:{int(inter.get('elapsed_time',0)%60):02d}",
                    "Plan (Cel)": ms_to_pace(target_speed),
                    "Tempo (Wyk)": ms_to_pace(speed),
                    "Moc (W)": inter.get('average_watts', 0)
                })
            st.table(pd.DataFrame(rows))
        else:
            st.warning("Brak danych interwałowych.")

# --- ASYSTENT AI GEMINI (Z DETALICZNĄ ANALIZĄ TRENINGÓW I WYBOREM DAT) ---
def renderuj_gemini(df, df_wellness, gemini_key, nazwa_zawodnika):
    st.subheader("🧠 Inteligentny Asystent AI (Google Gemini)")
    st.write("Moduł analizuje surowe dane fizjologiczne oraz szczegółową listę treningów w wybranym okresie i generuje pisemny raport.")
    
    # 1. FILTR DAT DLA AI
    st.markdown("#### 📅 Wybierz zakres dat do analizy raportu AI")
    min_date_limit = df['start_date_local'].min().date() if not df.empty else datetime.now().date() - timedelta(days=90)
    max_date_limit = df['start_date_local'].max().date() if not df.empty else datetime.now().date()
    
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        domyslny_start = max(min_date_limit, max_date_limit - timedelta(days=14)) # domyślnie ostatnie 2 tygodnie
        data_poczatek_ai = st.date_input("Początek okresu raportu:", domyslny_start, min_value=min_date_limit, max_value=max_date_limit, key="ai_start")
    with col_d2:
        data_koniec_ai = st.date_input("Koniec okresu raportu:", max_date_limit, min_value=min_date_limit, max_value=max_date_limit, key="ai_koniec")
    
    st.markdown("---")

    if not gemini_key:
        st.warning("⚠️ Wklej swój darmowy klucz API Gemini w pasku bocznym po lewej stronie, aby odblokować asystenta AI.")
        return
        
    if st.button("🚀 Wygeneruj Raport AI dla Zawodnika"):
        with st.spinner("Gemini analizuje dane fizjologiczne i historię treningów..."):
            try:
                # 2. Filtrowanie aktywności i wellness na wybrany okres
                df_filtered_ai = df[
                    (df['start_date_local'].dt.date >= data_poczatek_ai) & 
                    (df['start_date_local'].dt.date <= data_koniec_ai)
                ].sort_values(by='start_date_local', ascending=False)
                
                if df_filtered_ai.empty:
                    st.warning("Brak aktywności w wybranym okresie dat. Wybierz inny zakres.")
                    return

                # Pobieramy końcowe wartości fizjologiczne z wybranego okresu
                ctl = int(df_filtered_ai['icu_ctl'].fillna(0).iloc[0]) if 'icu_ctl' in df_filtered_ai.columns else 0
                atl = int(df_filtered_ai['icu_atl'].fillna(0).iloc[0]) if 'icu_atl' in df_filtered_ai.columns else 0
                tsb = int(df_filtered_ai['icu_tsb'].fillna(0).iloc[0]) if 'icu_tsb' in df_filtered_ai.columns else 0
                tss_total = int(df_filtered_ai['icu_training_load'].sum()) if 'icu_training_load' in df_filtered_ai.columns else 0
                
                # Wellness w okresie AI
                avg_rhr = "-"
                avg_hrv = "-"
                if df_wellness is not None and not df_wellness.empty:
                    df_wellness['date_parsed'] = pd.to_datetime(df_wellness['id']).dt.date
                    df_w_filtered = df_wellness[
                        (df_wellness['date_parsed'] >= data_poczatek_ai) & 
                        (df_wellness['date_parsed'] <= data_koniec_ai)
                    ]
                    if not df_w_filtered.empty:
                        if 'restingHR' in df_w_filtered.columns:
                            avg_rhr = round(df_w_filtered['restingHR'].dropna().mean(), 1)
                        if 'hrv' in df_w_filtered.columns:
                            avg_hrv = round(df_w_filtered['hrv'].dropna().mean(), 1)

                # 3. Wyciąganie szczegółowej listy treningów (maksymalnie 10 z okresu)
                lista_treningow_tekst = []
                for _, row in df_filtered_ai.head(10).iterrows():
                    parametr_specjalny = ""
                    # Jeśli to bieg, wyciągamy tempo
                    if row.get('type') == 'Run':
                        parametr_specjalny = f"Tempo śr: {ms_to_pace(row.get('average_speed', 0))}/km"
                    # Jeśli rower, średnią moc
                    elif row.get('type') in ['Ride', 'VirtualRide'] and row.get('average_watts'):
                        parametr_specjalny = f"Moc śr: {int(row['average_watts'])}W"
                    
                    opcjonalne_hr = f"Śr. HR: {int(row['average_heartrate'])} bpm" if row.get('average_heartrate') else ""
                    
                    lista_treningow_tekst.append(
                        f"* {row['start_date_local'].date()} - {row['name']} ({row['type']}) | "
                        f"Czas: {int(row.get('moving_time', 0)//60)} min | "
                        f"TSS: {int(row.get('icu_training_load', 0))} | "
                        f"{opcjonalne_hr} {parametr_specjalny}"
                    )
                treningi_prompt_text = "\n".join(lista_treningow_tekst)

                # 4. Budowa zaawansowanego promptu
                prompt = f"""
                Jesteś wybitnym trenerem sportów wytrzymałościowych i fizjologiem sportu.
                Przeanalizuj poniższe dane Twojego zawodnika ({nazwa_zawodnika}) za okres od {data_poczatek_ai} do {data_koniec_ai}.
                
                METRYKI NA KONIEC OKRESU:
                - Fitness (CTL): {ctl} (ogólna wydolność)
                - Fatigue (ATL): {atl} (zmęczenie ostre)
                - Form (TSB): {tsb} (świeżość/forma)
                - Łączne obciążenie TSS z całego okresu: {tss_total}
                
                DANE ZDROWOTNE (ŚREDNIE Z TEGO OKRESU):
                - Tętno spoczynkowe (RHR): {avg_rhr} bpm
                - Zmienność tętna (HRV, rMSSD): {avg_hrv} ms
                
                WYKAZ NAJWAŻNIEJSZYCH TRENINGÓW W TYM OKRESIE (Maksymalnie 10):
                {treningi_prompt_text}
                
                Napisz profesjonalny, konkretny i szczegółowy raport trenerski w języku polskim.
                Twoja odpowiedź musi zawierać:
                1. EVALUACJA TRENINGÓW: Przeanalizuj wykonane treningi z listy (zwróć uwagę na ich intensywność, TSS, tempo/moc). Jak te konkretne jednostki wpłynęły na zmęczenie zawodnika.
                2. REAKCJA FIZJOLOGICZNA: Jak na te treningi zareagował organizm zawodnika (czy RHR i HRV korelują z obciążeniami, czy widać udaną adaptację, czy może symptomy przetrenowania).
                3. PRAKTYCZNY PLAN NA KOLEJNY MIKROCYKL: Dokładne zalecenia na najbliższe 3-4 dni. Napisz wprost, czy zawodnik ma odpoczywać (delodad), czy możesz mu dołożyć mocniejsze interwały (i jakiego typu).
                
                Pisz zwięźle, profesjonalnym językiem trenerskim, używając punktów. Unikaj ogólników.
                """
                
                # 5. Wywołanie Gemini
                genai.configure(api_key=gemini_key)
                model = genai.GenerativeModel('gemini-2.5-flash')
                response = model.generate_content(prompt)
                
                st.success("✅ Raport wygenerowany pomyślnie!")
                st.markdown("---")
                st.markdown(response.text)
                st.markdown("---")
                st.caption(f"Raport wygenerowany automatycznie dla okresu {data_poczatek_ai} - {data_koniec_ai} przez model Gemini-2.5-Flash.")
                
            except Exception as e:
                st.error(f"Nie udało się wygenerować raportu: {e}")

# --- MAIN ---
def main():
    st.sidebar.title("🛠️ CoachPro v1.0")
    plik_tp = st.sidebar.file_uploader("Wgraj plan (.csv)", type=['csv'], key='plan_uploader')
    df_plan = pd.read_csv(plik_tp) if plik_tp else None
    gemini_key = st.sidebar.text_input("🔑 Klucz API Gemini", type="password", key="gemini_api_key")

    # 1. Pobieranie listy podopiecznych
    with st.spinner('Pobieram listę zawodników...'):
        lista_podopiecznych = pobierz_liste_podopiecznych()
    
    selected_athlete_id = None
    selected_athlete_name = "Zawodnik"
    if lista_podopiecznych:
        opcje_zawodnikow = {}
        for p in lista_podopiecznych:
            a_id = p.get('id') or (p.get('athlete') and p['athlete'].get('id')) or p.get('athlete_id')
            a_name = p.get('name') or (p.get('athlete') and p['athlete'].get('name')) or p.get('athlete_name') or f"Zawodnik {a_id}"
            if a_id:
                opcje_zawodnikow[f"{a_name} ({a_id})"] = (a_id, a_name)
        
        if opcje_zawodnikow:
            wybrany_tekst = st.sidebar.selectbox("Wybierz zawodnika:", list(opcje_zawodnikow.keys()))
            selected_athlete_id, selected_athlete_name = opcje_zawodnikow[wybrany_tekst]

    if not selected_athlete_id:
        st.sidebar.warning("Używam ID domyślnego Jarka Malinowskiego.")
        selected_athlete_id = "i602684"
        selected_athlete_name = "Jarek Malinowski"

    # 2. Pobieranie danych
    df = pobierz_liste_aktywnosci(selected_athlete_id)
    df_wellness = pobierz_wellness(selected_athlete_id)
    
    if df is not None:
        df['start_date_local'] = pd.to_datetime(df['start_date_local'])
        st.title("🚀 Dashboard Trenera")
        tab1, tab2, tab3, tab4 = st.tabs(["📈 Analiza Formy", "🎯 Analiza Interwałów", "🤖 Zaawansowane", "🧠 Asystent AI Gemini"])
        with tab1: renderuj_dashboard(df)
        with tab2: renderuj_interwaly(df, df_plan)
        with tab3: renderuj_zaawansowane(df, df_wellness)
        with tab4: renderuj_gemini(df, df_wellness, gemini_key, selected_athlete_name)
    else:
        st.error("Błąd połączenia z Intervals.icu. Wyczyść cache (klawisz C).")

if __name__ == "__main__":
    main()