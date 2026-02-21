import streamlit as st
from utils import setup_session_state, load_css, render_sidebar

st.set_page_config(page_title="Raport Nieruchomości", layout="wide", page_icon="🏗️")

setup_session_state()
load_css()
render_sidebar()

if st.session_state.data_loaded:
    st.title(f"Raport Rynku Nieruchomości: {st.session_state.miesiac} {st.session_state.rok}")
    st.markdown("Wybierz zakładkę z menu po lewej stronie, aby zobaczyć interaktywne wykresy i tabele.")
    
    # Obliczanie KPI
    ref_rate_val = st.session_state.nbp_df.iloc[0]['Wartość (%)'] if st.session_state.nbp_df is not None else "-"
    placa_val, placa_delta, zatr_val, zatr_delta = "-", None, "-", None
    if st.session_state.gus_praca:
        if st.session_state.gus_praca['kpi_placa']: placa_val = f"{st.session_state.gus_praca['kpi_placa']:,.2f} PLN".replace(',', ' ')
        if st.session_state.gus_praca['kpi_placa_dyn']: placa_delta = f"{st.session_state.gus_praca['kpi_placa_dyn']:+.1f}% r/r"
        if st.session_state.gus_praca['kpi_zatr']: zatr_val = f"{int(st.session_state.gus_praca['kpi_zatr'] * 1000):,}".replace(',', ' ')
        if st.session_state.gus_praca['kpi_zatr_dyn']: zatr_delta = f"{st.session_state.gus_praca['kpi_zatr_dyn']:+.1f}% r/r"
    
    mieszkania_val, rozpoczete_val, pozwolenia_val, budowa_date_label = "-", "-", "-", ""
    if st.session_state.gus_budowa and st.session_state.gus_budowa["time_series"] is not None and not st.session_state.gus_budowa["time_series"].empty:
        r = st.session_state.gus_budowa["time_series"].iloc[0]
        budowa_date_label = f"{r.get('Miesiąc', '')} {r.get('Rok', '')}"
        if r.get('Oddane do użytkowania'): mieszkania_val = f"{r.get('Oddane do użytkowania'):,.0f}".replace(',', ' ')
        if r.get('Rozpoczęte budowy'): rozpoczete_val = f"{r.get('Rozpoczęte budowy'):,.0f}".replace(',', ' ')
        if r.get('Wydane pozwolenia'): pozwolenia_val = f"{r.get('Wydane pozwolenia'):,.0f}".replace(',', ' ')
        
    inflacja_val, inflacja_date_label = "-", ""
    if st.session_state.inflacja and st.session_state.inflacja['kpi_inflacja']: inflacja_val = f"{st.session_state.inflacja['kpi_inflacja']:.1f}%"
    if st.session_state.inflacja and st.session_state.inflacja['df'] is not None and not st.session_state.inflacja['df'].empty:
        inflacja_date_label = f"{st.session_state.inflacja['df'].iloc[0]['Miesiąc Nazwa']} {st.session_state.inflacja['df'].iloc[0]['Rok']}"

    st.markdown("### 📊 Kluczowe Wskaźniki Efektywności (KPI)")
    k1, k2, k3, k4, k5, k6, k7 = st.columns(7)
    k1.markdown(f"<span class='kpi-icon'>🏦</span> **Stopa NBP**", unsafe_allow_html=True); k1.metric("Stopa", f"{ref_rate_val}%", label_visibility="collapsed"); k1.caption(f"Od: {st.session_state.nbp_date}")
    k2.markdown(f"<span class='kpi-icon'>📈</span> **Inflacja CPI**", unsafe_allow_html=True); k2.metric("Inflacja", inflacja_val, label_visibility="collapsed"); k2.caption(inflacja_date_label)
    k3.markdown(f"<span class='kpi-icon'>💰</span> **Średnia Płaca**", unsafe_allow_html=True); k3.metric("Płaca", placa_val, delta=placa_delta, label_visibility="collapsed"); k3.caption("Przedsiębiorstwa")
    k4.markdown(f"<span class='kpi-icon'>👥</span> **Zatrudnienie**", unsafe_allow_html=True); k4.metric("Zatrudnienie", zatr_val, delta=zatr_delta, label_visibility="collapsed")
    k5.markdown(f"<span class='kpi-icon'>🏠</span> **Oddane**", unsafe_allow_html=True); k5.metric("Oddane", mieszkania_val, label_visibility="collapsed"); k5.caption(budowa_date_label)
    k6.markdown(f"<span class='kpi-icon'>🏗️</span> **Rozpoczęte**", unsafe_allow_html=True); k6.metric("Rozpoczęte", rozpoczete_val, label_visibility="collapsed"); k6.caption(budowa_date_label)
    k7.markdown(f"<span class='kpi-icon'>📝</span> **Pozwolenia**", unsafe_allow_html=True); k7.metric("Pozwolenia", pozwolenia_val, label_visibility="collapsed"); k7.caption(budowa_date_label)
else:
    st.info("👈 Wpisz klucz API w menu po lewej i kliknij 'POBIERZ DANE DO RAPORTU'.")