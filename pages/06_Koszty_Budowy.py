import streamlit as st
import pandas as pd
from utils import setup_session_state, load_css, render_sidebar, display_ai_section, clean_number_formatting

st.set_page_config(page_title="Koszty Budowy", layout="wide")
setup_session_state()
load_css()
render_sidebar()

st.header("6. Koszty Budowy (GUS - AI Parser)")
if st.session_state.data_loaded and st.session_state.ceny_bud and st.session_state.ceny_bud['data'] is not None:
    display_ai_section('koszty', st.session_state.ceny_bud['data'].to_string())
    
    headers = st.session_state.ceny_bud['headers']
    data = st.session_state.ceny_bud['data']
    
    h1, h2 = headers[0], headers[1]
    html = '<table class="gus-table"><thead><tr>'
    
    if "Kategoria" in data.columns and (not h1 or len(h1) < 2):
        for col in data.columns: html += f'<th>{col}</th>'
        html += '</tr></thead><tbody>'
        for _, row in data.iterrows():
            html += '<tr>'
            html += f'<td style="text-align:left;">{row.iloc[0]}</td>'
            for idx in range(1, len(data.columns)): html += f'<td>{clean_number_formatting(row.iloc[idx])}</td>'
            html += '</tr>'
    else:
        html += '<th rowspan="2" style="vertical-align:middle;">Wyszczególnienie</th>'
        col_indices = []
        i = 1
        while i < len(h1):
            val1, val2 = str(h1[i]).replace('nan', '').strip(), str(h2[i]).replace('nan', '').strip()
            if not val1 and not val2:
                i += 1; continue
            col_indices.append(i)
            colspan = 1
            if val1 and i + 1 < len(h1):
                if not str(h1[i+1]).replace('nan', '').strip():
                    colspan = 2
                    col_indices.append(i+1)
            if val1: html += f'<th colspan="{colspan}">{val1}</th>'
            i += colspan if val1 else 1
        html += '</tr><tr>'
        j = 0
        while j < len(col_indices):
            idx = col_indices[j]
            val = str(h2[idx]).replace('nan', '').strip()
            colspan = 1
            if j + 1 < len(col_indices):
                if not str(h2[col_indices[j+1]]).replace('nan', '').strip(): colspan = 2
            if colspan == 2:
                html += f'<th colspan="2">{val}</th>'
                j += 2
            else:
                html += f'<th>{val}</th>'
                j += 1
        html += '</tr></thead><tbody>'
        for _, row in data.iterrows():
            html += f'<tr><td style="text-align:left;">{row.iloc[0]}</td>'
            for idx in col_indices:
                if idx < len(row): html += f'<td>{clean_number_formatting(row.iloc[idx])}</td>'
            html += '</tr>'
            
    html += '</tbody></table>'
    st.markdown(html, unsafe_allow_html=True)
else:
    st.warning("Najpierw pobierz dane w zakładce głównej!")