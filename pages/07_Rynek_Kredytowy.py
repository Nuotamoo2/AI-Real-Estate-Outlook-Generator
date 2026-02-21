import streamlit as st
from utils import setup_session_state, load_css, render_sidebar, display_ai_section, render_bik_section

st.set_page_config(page_title="Rynek Kredytowy", layout="wide")
setup_session_state()
load_css()
render_sidebar()

st.header("7. Rynek Kredytowy (BIK)")
if st.session_state.data_loaded:
    display_ai_section('bik', "Dane BIK są interaktywnymi iFrame'ami pobieranymi z Tableau Public.")
    render_bik_section("Sprzedaż Kredytów", "https://public.tableau.com/views/BIKKIkolory1170BIKPreview/SprzedaKIokno")
    render_bik_section("Portfel Kredytów", "https://public.tableau.com/views/BIKKIkolory1170BIKPreview/PortfelKIokno")
    render_bik_section("Kredytobiorcy", "https://public.tableau.com/views/BIKKIkolory1170BIKPreview/KlienciBIKKIokno")
else:
    st.warning("Najpierw pobierz dane w zakładce głównej!")