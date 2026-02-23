import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import base64
import glob
import re
import json
from utils import (
    setup_session_state, load_css, render_sidebar, render_dynamic_section, display_ai_section, render_bik_section
)

st.set_page_config(page_title="Raport Nieruchomości AI", layout="wide", page_icon="🏗️")

setup_session_state()
load_css()
render_sidebar()

def get_chart_script(chart, div_id):
    if chart is None: return ""
    return f"<div id='{div_id}' style='margin-bottom: 30px; display: flex; justify-content: center;'></div><script>vegaEmbed('#{div_id}', {chart.to_json()});</script>"

def generate_full_html_report(session_state):
    html = """
    <!DOCTYPE html>
    <html lang="pl">
    <head>
        <meta charset="UTF-8">
        <script src="https://cdn.jsdelivr.net/npm/vega@5"></script>
        <script src="https://cdn.jsdelivr.net/npm/vega-lite@5"></script>
        <script src="https://cdn.jsdelivr.net/npm/vega-embed@6"></script>
        <style>
            body { font-family: 'Segoe UI', Arial, sans-serif; margin: 40px; color: #333; }
            h1 { border-bottom: 3px solid #2c3e50; padding-bottom: 10px; color: #2c3e50; }
            h2 { margin-top: 40px; border-bottom: 2px solid #eee; padding-bottom: 5px; color: #34495e; }
            .gus-table { width: 100%; border-collapse: collapse; font-size: 13px; margin-bottom: 30px; }
            .gus-table th { background-color: #e6e6e6; border: 1px solid #a0a0a0; padding: 8px; }
            .gus-table td { border: 1px solid #d0d0d0; padding: 8px; text-align: center; }
            .print-btn { background:#FF4B4B; color:white; padding:15px; border:none; border-radius:8px; width:100%; cursor:pointer; font-size:18px; font-weight:bold; margin-bottom: 30px; }
            @media print { .print-btn { display: none; } body { margin: 0; } }
        </style>
    </head>
    <body>
        <button class="print-btn" onclick="window.print()">🖨️ DRUKUJ / ZAPISZ JAKO PDF</button>
        <h1>Inteligentny Raport Rynku Nieruchomości</h1>
    """

    if session_state.nbp_df is not None:
        html += "<h2>Stopy Procentowe NBP</h2>"
        html += session_state.nbp_df.to_html(classes='gus-table', index=False)

    dodatkowe = sorted([f for f in glob.glob("pages/*.py") if re.search(r'\d{2}_', f) and "00_AI_Panel" not in f])
    for i, plik in enumerate(dodatkowe):
        try:
            with open(plik, "r", encoding="utf-8") as file: content = file.read()
            meta_match = re.search(r'# === META START ===\nMETA_JSON = r"""(.*?)"""\n# === META END ===', content, re.DOTALL)
            if meta_match:
                meta = json.loads(meta_match.group(1))
                safe_name = re.sub(r'\W+', '_', meta.get("tab_name", "")).strip('_')
                html += f"<h2>{meta.get('tab_name')}</h2>"
                
                for j, table in enumerate(session_state.get(f"dynamic_data_{safe_name}", meta.get("tables", []))):
                    df = pd.DataFrame(table.get("data", []))
                    if df.empty: continue
                    
                    pandas_code = table.get("pandas_code", "")
                    if pandas_code:
                        try:
                            local_vars = {"df": df, "pd": pd, "np": np}
                            exec(pandas_code, globals(), local_vars)
                            df = local_vars["df"]
                        except Exception: pass
                        
                    split_col = table.get("split_by_column", "")
                    if split_col and split_col in df.columns:
                        unique_vals = sorted(df[split_col].dropna().unique())
                        df_list = [(f"{table.get('dataset_name', '')} - {val}", df[df[split_col] == val]) for val in unique_vals]
                    else:
                        df_list = [(table.get('dataset_name', ''), df)]
                        
                    for sub_idx, (sub_title, sub_df) in enumerate(df_list):
                        if sub_df.empty: continue
                        html += f"<h3>{sub_title}</h3>"
                        t_chart, t_x, t_y = table.get("recommended_chart", "none"), table.get("x_axis_column"), table.get("y_axis_columns", [])
                        if t_chart != "none" and t_x and t_y and t_x in sub_df.columns and all(y in sub_df.columns for y in t_y):
                            df_plot = sub_df.melt(id_vars=[t_x], value_vars=t_y, var_name='Legenda', value_name='Wartość')
                            c = alt.Chart(df_plot)
                            if t_chart == "line": c = c.mark_line(point=True).encode(x=alt.X(t_x, sort=None), y='Wartość', color='Legenda')
                            elif t_chart == "bar": c = c.mark_bar().encode(x=alt.X(t_x, sort='-y'), y='Wartość', color='Legenda')
                            elif t_chart == "pie": c = alt.Chart(sub_df).mark_arc().encode(color=t_x, theta=t_y[0])
                            html += f"<div id='chart_{i}_{j}_{sub_idx}'></div><script>vegaEmbed('#chart_{i}_{j}_{sub_idx}', {c.to_json()});</script>"
                        html += sub_df.to_html(classes='gus-table', index=False)
        except: pass
            
    html += "</body></html>"
    return html

if st.session_state.data_loaded:
    st.title(f"Inteligentny Raport Rynku: {st.session_state.miesiac} {st.session_state.rok}")
    st.markdown("Ten pulpit jest generowany w 100% dynamicznie przez Sztuczną Inteligencję na podstawie Twoich szablonów.")
    
    html_report = generate_full_html_report(st.session_state)
    b64 = base64.b64encode(html_report.encode('utf-8')).decode()
    st.markdown(f'<a href="data:file/html;base64,{b64}" download="Pelny_Raport_Nieruchomosci_AI.html" style="text-decoration:none;"><button style="background:#FF4B4B; color:white; padding:15px; border:none; border-radius:8px; width:100%; cursor:pointer; font-size:16px; font-weight:bold;">📥 POBIERZ PEŁNY RAPORT W HTML/PDF (Wszystkie Moduły AI!)</button></a>', unsafe_allow_html=True)
    st.divider()

    st.markdown("## 🏦 DANE STAŁE (NBP / BIK)")
    
    st.header("Stopy Procentowe NBP")
    if st.session_state.nbp_df is not None:
        st.caption(f"Tabela obowiązuje od dnia: **{st.session_state.nbp_date}**")
        st.markdown(st.session_state.nbp_df.to_html(classes='gus-table', index=False, border=0), unsafe_allow_html=True)
        display_ai_section('nbp', st.session_state.nbp_df.to_string())

    st.markdown("---")

    st.header("Rynek Kredytowy (BIK)")
    render_bik_section("Sprzedaż Kredytów", "https://public.tableau.com/views/BIKKIkolory1170BIKPreview/SprzedaKIokno")
    display_ai_section('bik', "Dane BIK są interaktywnymi iFrame'ami pobieranymi z Tableau Public.")

    st.divider()
    st.markdown("## 🤖 MODUŁY WYGENEROWANE PRZEZ AI (GUS)")
    st.info("Poniżej renderują się wszystkie Twoje zakładki w kolejności ustalonej w Magicznym Panelu.")
    
    dodatkowe = sorted([f for f in glob.glob("pages/*.py") if re.search(r'\d{2}_', f) and "00_AI_Panel" not in f and "NBP" not in f and "Rynek_Kredytowy" not in f])
    
    if dodatkowe:
        for plik in dodatkowe:
            try:
                with open(plik, "r", encoding="utf-8") as file: content = file.read()
                meta_match = re.search(r'# === META START ===\nMETA_JSON = r"""(.*?)"""\n# === META END ===', content, re.DOTALL)
                if meta_match:
                    meta = json.loads(meta_match.group(1))
                    render_dynamic_section(meta, plik, is_in_app=True)
                    st.markdown("---")
            except Exception as e:
                pass
    else:
        st.warning("Nie stworzyłeś jeszcze żadnych własnych zakładek z danych GUS! Przejdź do zakładki '00_AI_Panel' i dodaj swoje szablony.")
else:
    st.info("👈 Wpisz klucz API w menu po lewej i kliknij 'POBIERZ GŁÓWNE DANE DO RAPORTU'.")