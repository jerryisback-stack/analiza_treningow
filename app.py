import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

# =======================================================
# 1. KONFIGURACJA (TWOJE DANE TRENERA)
# =======================================================
# Twój oficjalny klucz API trenera (Jarek SK Team)
COACH_API_KEY = "236evlzcl4eiiqhsm9uciid2u" 

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

# --- ZAAWANSOWANE (PEŁNE 4 WYKRESY) ---
def renderuj_zaawansowane(df, df_wellness):
    st.subheader("🤖 Analiza Zaawansowana")
    c1, c2 = st.columns(2)
    
    with c1:
        # WYKRES 1: RHR, HRV vs TSS
        st.write("### 💓 Monitorowanie Regeneracji: RHR, HRV vs TSS")
        if df_wellness is not None:
            df['date'] = df['start_date_local'].dt.normalize()
            df_wellness['date'] = pd.to_datetime(df_wellness['id'])
            
            kolumny_wellness = ['date']
            if 'restingHR' in df_wellness.columns: kolumny_wellness.append('restingHR')
            if 'hrv' in df_wellness.columns: kolumny_wellness.append('hrv')
            
            df_merged = pd.merge(df[['date', 'icu_training_load']], 
                                 df_wellness[kolumny_wellness], 
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
                yaxis=dict(title="Tętno / HRV"),
                yaxis2=dict(title="TSS", overlaying='y', side='right'),
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_rhr, use_container_width=True)
        else:
            st.info("Brak danych wellness.")

        # WYKRES 2: Wydajność Aerobowa (EF)
        st.write("### 🏃‍♂️ Wskaźnik Wydajności Aerobowej (EF)")
        if 'icu_efficiency_factor' in df.columns:
            df_ef = df[df['icu_efficiency_factor'] > 0].copy()
            if not df_ef.empty:
                fig_ef = px.scatter(df_ef, x='start_date_local', y='icu_efficiency_factor', 
                                    trendline="ols", labels={'icu_efficiency_factor': 'Efficiency Factor'},
                                    title="Wzrost EF = Lepsza ekonomia wysiłku")
                st.plotly_chart(fig_ef, use_container_width=True)
            else:
                st.info("Brak danych EF (wymaga tętna i mocy/tempa).")
        else:
            st.info("Brak kolumny icu_efficiency_factor.")

    with c2:
        # WYKRES 3: Variability Index
        st.write("### ⚡ Variability Index (VI)")
        if 'icu_variability_index' in df.columns:
            fig_vi = px.scatter(df, x='start_date_local', y='icu_variability_index', trendline="ols",
                                title="Cel: ~1.0 dla jednostajnych, >1.1 dla szarpanych")
            st.plotly_chart(fig_vi, use_container_width=True)
        else:
            st.info("Brak danych VI.")
            
        # WYKRES 4: Polaryzacja tętna (strefy)
        st.write("### 📊 Polaryzacja: Czas w strefach tętna (minuty)")
        if 'icu_hr_zone_times' in df.columns:
            zones_list = []
            for _, row in df.iterrows():
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
                                    title="Czas w strefach tętna w kolejnych dniach")
                st.plotly_chart(fig_zones, use_container_width=True)
            else:
                st.info("Brak danych o strefach tętna.")
        else:
            st.info("Brak kolumny icu_hr_zone_times.")

    # Panel diagnostyczny na dole
    if df_wellness is not None:
        with st.expander("🕵️ Podgląd danych zdrowotnych (Wellness)"):
            st.write("Dostępne pomiary tętna i HRV w bazie:")
            st.dataframe(df_wellness[['date', 'restingHR', 'hrv']].dropna(subset=['restingHR', 'hrv'], how='all').tail(15))

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

# --- MAIN ---
def main():
    st.sidebar.title("🛠️ CoachPro v1.0")
    plik_tp = st.sidebar.file_uploader("Wgraj plan (.csv)", type=['csv'], key='plan_uploader')
    df_plan = pd.read_csv(plik_tp) if plik_tp else None

    # 1. Pobieranie listy podopiecznych
    with st.spinner('Pobieram listę zawodników...'):
        lista_podopiecznych = pobierz_liste_podopiecznych()
    
    selected_athlete_id = None
    if lista_podopiecznych:
        opcje_zawodnikow = {}
        for p in lista_podopiecznych:
            a_id = p.get('id') or (p.get('athlete') and p['athlete'].get('id')) or p.get('athlete_id')
            a_name = p.get('name') or (p.get('athlete') and p['athlete'].get('name')) or p.get('athlete_name') or f"Zawodnik {a_id}"
            if a_id:
                opcje_zawodnikow[f"{a_name} ({a_id})"] = a_id
        
        if opcje_zawodnikow:
            wybrany_tekst = st.sidebar.selectbox("Wybierz zawodnika:", list(opcje_zawodnikow.keys()))
            selected_athlete_id = opcje_zawodnikow[wybrany_tekst]

    # Bezpiecznik rezerwowy na wypadek gdyby lista była pusta
    if not selected_athlete_id:
        st.sidebar.warning("Używam ID domyślnego Jarka Malinowskiego.")
        selected_athlete_id = "i602684"

    # 2. Pobieranie danych
    df = pobierz_liste_aktywnosci(selected_athlete_id)
    df_wellness = pobierz_wellness(selected_athlete_id)
    
    if df is not None:
        df['start_date_local'] = pd.to_datetime(df['start_date_local'])
        st.title("🚀 Dashboard Trenera")
        tab1, tab2, tab3 = st.tabs(["📈 Analiza Formy", "🎯 Analiza Interwałów", "🤖 Zaawansowane"])
        with tab1: renderuj_dashboard(df)
        with tab2: renderuj_interwaly(df, df_plan)
        with tab3: renderuj_zaawansowane(df, df_wellness)
    else:
        st.error("Błąd połączenia z Intervals.icu. Wyczyść cache (klawisz C).")

if __name__ == "__main__":
    main()