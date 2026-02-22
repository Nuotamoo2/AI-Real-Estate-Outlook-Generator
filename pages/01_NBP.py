import streamlit as st
from utils import setup_session_state, load_css, render_sidebar, display_ai_section

st.set_page_config(page_title="NBP", layout="wide")
setup_session_state()
load_css()
render_sidebar()

st.header("1. Stopy Procentowe NBP")
if st.session_state.data_loaded and st.session_state.nbp_df is not None:
    st.caption(f"Tabela obowiązuje od dnia: **{st.session_state.nbp_date}**")
    display_ai_section('nbp', st.session_state.nbp_df.to_string())
    st.markdown(st.session_state.nbp_df.to_html(classes='gus-table', index=False, border=0), unsafe_allow_html=True)
else:
    st.warning("Najpierw pobierz dane w zakładce głównej!")