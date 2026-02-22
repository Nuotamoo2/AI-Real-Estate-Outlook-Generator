import streamlit as st
import pandas as pd
import altair as alt
import base64
import glob
import re
import json
from datetime import timedelta
from utils import (
    setup_session_state, load_css, render_sidebar, generate_full_html_report,
    render_dynamic_section, display_ai_section, MONTH_ORDER,
    format_with_indicator, prepare_data_for_chart_aggregate,
    prepare_yearly_comparison_data, get_month_number, parse_float_safe,
    render_bik_section, clean_number_formatting, render_page_header
)

st.set_page_config(page_title="Raport Nieruchomości", layout="wide", page_icon="🏗️")

setup_session_state()
load_css()
render_sidebar()

# ==========================================
# DEFINICJE WIDOKÓW 1:1 Z ZAKŁADEK
# ==========================================

def render_01_nbp():
    st.header("1. Stopy Procentowe NBP")
    if st.session_state.data_loaded and st.session_state.nbp_df is not None:
        st.caption(f"Tabela obowiązuje od dnia: **{st.session_state.nbp_date}**")
        display_ai_section('nbp', st.session_state.nbp_df.to_string())
        st.markdown(st.session_state.nbp_df.to_html(classes='gus-table', index=False, border=0), unsafe_allow_html=True)
    else:
        st.warning("Najpierw pobierz dane w zakładce głównej!")

def render_02_inflacja():
    st.header("2. Inflacja (GUS)")
    if st.session_state.data_loaded and st.session_state.inflacja and st.session_state.inflacja['df'] is not None:
        df = st.session_state.inflacja['df']
        display_ai_section('inflacja', df.head(24).to_string())
        
        max_date = df['Date'].max()
        min_zoom_date = max_date - timedelta(days=365*5)
        
        base = alt.Chart(df).encode(x=alt.X('Date', title='Data', axis=alt.Axis(format='%Y-%m'), scale=alt.Scale(domain=[min_zoom_date, max_date])), y=alt.Y('Inflacja %', title='Zmiana %', scale=alt.Scale(zero=False)), color=alt.Color('Metoda', title='Sposób prezentacji', legend=alt.Legend(orient='bottom', columns=1)))
        nearest = alt.selection_point(nearest=True, on='mouseover', fields=['Date'], empty=False)
        lines = base.mark_line(point=True, clip=True)
        selectors = alt.Chart(df).mark_point().encode(x='Date', opacity=alt.value(0), tooltip=['Date', 'Metoda', 'Inflacja %']).add_params(nearest)
        points = lines.mark_point().encode(opacity=alt.condition(nearest, alt.value(1), alt.value(0)))
        text = base.mark_text(align='left', dx=5, dy=-5).encode(text=alt.condition(nearest, alt.Text('Inflacja %:Q', format='.1f'), alt.value(' ')))
        rule = base.mark_rule(color='gray').encode(x='Date').transform_filter(nearest)
        chart = alt.layer(lines, selectors, points, rule, text).interactive()
        
        st.altair_chart(chart, use_container_width=True)
        
        # Tabela Inflacji z połączonymi komórkami
        df_table = df[df['Metoda'].str.contains("analogiczny miesiąc", case=False, na=False)].copy()[['Rok', 'Miesiąc Nazwa', 'Inflacja %']]
        html = '<table class="gus-table"><thead><tr><th>Rok</th><th>Miesiąc</th><th>Inflacja r/r (%)</th></tr></thead><tbody>'
        year_counts, rendered_years = df_table['Rok'].value_counts().to_dict(), set()
        for _, row in df_table.iterrows():
            year = row['Rok']
            html += '<tr>'
            if year not in rendered_years:
                html += f'<td rowspan="{year_counts[year]}" style="font-weight:bold; background-color:#ffffff; text-align:center; vertical-align:middle;">{year}</td>'
                rendered_years.add(year)
            html += f'<td style="background-color:#ffffff;">{row["Miesiąc Nazwa"]}</td><td style="background-color:#ffffff;">{format_with_indicator(row["Inflacja %"], inverse=True)}</td></tr>'
        html += '</tbody></table>'
        st.markdown(html, unsafe_allow_html=True)

def render_03_praca():
    render_page_header("3. Rynek Pracy (GUS)", "")
    if st.session_state.data_loaded and st.session_state.gus_praca:
        praca = st.session_state.gus_praca
        data_str = praca['tablica_1'].to_string() if praca['tablica_1'] is not None else ""
        for c in praca['wykresy']: data_str += f"\n\n{c['title']}:\n{c['full_data'].tail(12).to_string()}"
        display_ai_section('praca', data_str)
        st.subheader("Tablica 1: Przeciętne zatrudnienie i wynagrodzenie")
        if praca['tablica_1'] is not None: st.markdown(praca['tablica_1'].to_html(classes='gus-table', border=0, na_rep=""), unsafe_allow_html=True)
        for chart in praca['wykresy']:
            st.subheader(chart['title'])
            val_col, dyn_col = chart['val_col'], chart['dyn_col']
            y = str(st.session_state.rok)
            if chart['data'] and y in chart['data']:
                chart_year = chart['data'][y]['chart'].copy()
                chart_year['sort_idx'] = chart_year['Miesiąc'].apply(get_month_number)
                chart_year = chart_year.sort_values('sort_idx').set_index('Miesiąc').drop(columns=['sort_idx'])
                if val_col in chart_year.columns: chart_year = chart_year[[val_col]]
            else: chart_year = prepare_yearly_comparison_data(chart['full_data'], y, val_col, dyn_col)
            if not chart_year.empty:
                df_plot_y = chart_year.reset_index().melt(chart_year.index.name, var_name='Seria', value_name='Wartość')
                base_y = alt.Chart(df_plot_y).encode(x=alt.X(chart_year.index.name, sort=MONTH_ORDER, title=''), y=alt.Y('Wartość', scale=alt.Scale(zero=False)), color=alt.Color('Seria', title='Legenda', legend=alt.Legend(labelLimit=0, titleLimit=0)))
                lines_y, nearest_y = base_y.mark_line(point=True), alt.selection_point(nearest=True, on='mouseover', empty=False)
                points_y = base_y.mark_point().transform_filter(nearest_y)
                rule_y = alt.Chart(df_plot_y).mark_rule(color='gray').encode(x=alt.X(chart_year.index.name, sort=MONTH_ORDER)).transform_filter(nearest_y)
                selectors_y = base_y.mark_point().encode(opacity=alt.value(0), tooltip=[chart_year.index.name, 'Seria', 'Wartość']).add_params(nearest_y)
                text_y = lines_y.mark_text(align='left', dx=5, dy=-5).encode(text=alt.condition(nearest_y, 'Wartość:Q', alt.value(' ')))
                st.altair_chart(alt.layer(lines_y, selectors_y, rule_y, points_y, text_y).interactive(), use_container_width=True)
                
            chart_all = prepare_data_for_chart_aggregate(chart['full_data'], val_col)
            if not chart_all.empty:
                df_plot_all = chart_all.reset_index().melt(chart_all.index.name, var_name='Kategoria', value_name='Wartość')
                base_a = alt.Chart(df_plot_all).encode(x=alt.X(chart_all.index.name, title=''), y=alt.Y('Wartość', scale=alt.Scale(zero=False)), color=alt.Color('Kategoria', title='Legenda', legend=alt.Legend(labelLimit=0, titleLimit=0)))
                lines_a, nearest_a = base_a.mark_line(point=True), alt.selection_point(nearest=True, on='mouseover', empty=False)
                points_a = base_a.mark_point().transform_filter(nearest_a)
                rule_a = alt.Chart(df_plot_all).mark_rule(color='gray').encode(x=alt.X(chart_all.index.name)).transform_filter(nearest_a)
                selectors_a = base_a.mark_point().encode(opacity=alt.value(0), tooltip=[chart_all.index.name, 'Kategoria', 'Wartość']).add_params(nearest_a)
                text_a = lines_a.mark_text(align='left', dx=5, dy=-5).encode(text=alt.condition(nearest_a, 'Wartość:Q', alt.value(' ')))
                st.altair_chart(alt.layer(lines_a, selectors_a, rule_a, points_a, text_a).interactive(), use_container_width=True)

def render_04_budownictwo():
    render_page_header("4. Budownictwo Mieszkaniowe (GUS)", "")
    if st.session_state.data_loaded and st.session_state.gus_budowa:
        bd = st.session_state.gus_budowa
        ts = bd["time_series"]
        if ts is not None:
            display_ai_section('budownictwo', ts.tail(24).to_string())
            st.subheader("Wykres zbiorczy (Cały okres)")
            chart_all = prepare_data_for_chart_aggregate(ts, None)
            if not chart_all.empty:
                chart_all = chart_all.iloc[::-1] 
                cols_to_plot = [c for c in ['Oddane do użytkowania', 'Rozpoczęte budowy', 'Wydane pozwolenia'] if c in chart_all.columns]
                if cols_to_plot:
                    df_plot = chart_all[cols_to_plot].reset_index().melt('Okres', var_name='Kategoria', value_name='Wartość')
                    nearest = alt.selection_point(nearest=True, on='mouseover', empty=False)
                    base = alt.Chart(df_plot).encode(x=alt.X('Okres', title='Data'), y=alt.Y('Wartość', title='Ilość', scale=alt.Scale(zero=False)), color='Kategoria')
                    lines = base.mark_line(point=True)
                    selectors = base.mark_point().encode(opacity=alt.value(0), tooltip=['Okres', 'Kategoria', 'Wartość']).add_params(nearest)
                    points = lines.mark_point().encode(opacity=alt.condition(nearest, alt.value(1), alt.value(0)))
                    rule = alt.Chart(df_plot).mark_rule(color='gray').encode(x='Okres').transform_filter(nearest)
                    text = lines.mark_text(align='left', dx=5, dy=-5).encode(text=alt.condition(nearest, 'Wartość:Q', alt.value(' ')))
                    st.altair_chart(alt.layer(lines, selectors, rule, points, text).interactive(), use_container_width=True)
            
            y = str(st.session_state.rok)
            st.subheader(f"Porównanie r/r ({y} vs {int(y)-1})")
            cols_compare = [c for c in ['Oddane do użytkowania', 'Rozpoczęte budowy', 'Wydane pozwolenia'] if c in ts.columns]
            for col in cols_compare:
                st.markdown(f"**{col}**")
                chart_year = prepare_yearly_comparison_data(ts, y, col, None)
                if not chart_year.empty:
                    df_plot_y = chart_year.reset_index().melt(chart_year.index.name, var_name='Kategoria', value_name='Wartość')
                    base_y = alt.Chart(df_plot_y).encode(x=alt.X(chart_year.index.name, sort=MONTH_ORDER, title=''), y=alt.Y('Wartość', scale=alt.Scale(zero=False)), color='Kategoria')
                    nearest_y = alt.selection_point(nearest=True, on='mouseover', empty=False)
                    lines_y = base_y.mark_line(point=True)
                    points_y = base_y.mark_point().transform_filter(nearest_y)
                    rule_y = alt.Chart(df_plot_y).mark_rule(color='gray').encode(x=alt.X(chart_year.index.name, sort=MONTH_ORDER)).transform_filter(nearest_y)
                    selectors_y = base_y.mark_point().encode(opacity=alt.value(0), tooltip=[chart_year.index.name, 'Kategoria', 'Wartość']).add_params(nearest_y)
                    text_y = lines_y.mark_text(align='left', dx=5, dy=-5).encode(text=alt.condition(nearest_y, 'Wartość:Q', alt.value(' ')))
                    st.altair_chart(alt.layer(lines_y, selectors_y, rule_y, points_y, text_y).interactive(), use_container_width=True)
        if bd["regional"] is not None:
            st.subheader("Dane Regionalne (Województwa i Miasta)")
            df_reg_chart = bd["regional"].copy()
            for c in ["Pozwolenia wydane", "Rozpoczęte budowy", "Oddane do użytkowania"]: df_reg_chart[c] = df_reg_chart[c].apply(parse_float_safe)
            df_reg_chart = df_reg_chart[~df_reg_chart['Obszar'].str.contains('POLSKA', case=False, na=False)]
            df_melt = df_reg_chart.melt('Obszar', var_name='Kategoria', value_name='Wartość')
            st.altair_chart(alt.Chart(df_melt).mark_bar().encode(x=alt.X('Obszar', sort='-y', title=''), y='Wartość', color='Kategoria', tooltip=['Obszar', 'Kategoria', 'Wartość']).interactive(), use_container_width=True)
            st.markdown(bd["regional"].to_html(classes='gus-table', index=False), unsafe_allow_html=True)

def render_05_kwartalne():
    st.header("5. Budownictwo Kwartalne (GUS)")
    if st.session_state.data_loaded and st.session_state.gus_kwartalne:
        gk = st.session_state.gus_kwartalne
        
        data_str = (f"MAPA: {gk['mapa']['data'].to_string()}\n" if gk['mapa'] else "")
        for c in gk['wykresy']: data_str += f"\n{c['title']}:\n{c['data'].to_string()}"
        display_ai_section('kwartalne', data_str)
        
        if gk['mapa'] is not None:
            st.subheader(gk['mapa']['title'])
            df_map = gk['mapa']['data'].copy().sort_values('Wartość', ascending=False)
            chart_map = alt.Chart(df_map).mark_bar().encode(
                x=alt.X('Województwo', sort='-y'), y=alt.Y('Wartość', title='Mieszkania / 1000 ludności'),
                color=alt.Color('Wartość', scale=alt.Scale(scheme='blues')), tooltip=['Województwo', 'Wartość']
            ).interactive()
            st.altair_chart(chart_map, use_container_width=True)
            st.markdown(df_map.to_html(classes='gus-table', index=False), unsafe_allow_html=True)
            
        for chart in gk['wykresy']:
            st.subheader(chart['title'])
            df = chart['data']
            if chart['type'] == 'pie':
                base = alt.Chart(df).encode(theta=alt.Theta("Udział:Q", stack=True), color=alt.Color("Kategoria:N", legend=alt.Legend(orient="bottom", columns=2)))
                pie = base.mark_arc(outerRadius=120).encode(tooltip=["Kategoria", "Udział"])
                text = base.mark_text(radius=140).encode(text=alt.Text("Udział", format=".1f"), order=alt.Order("Udział", sort="descending"), color=alt.value("black"))
                st.altair_chart(pie + text, use_container_width=True)
                st.markdown(df.to_html(classes='gus-table', index=False), unsafe_allow_html=True)
            elif chart['type'] == 'compare':
                df_html = df.copy()
                if "Zmiana" in df_html.columns: df_html["Zmiana"] = df_html["Zmiana"].apply(format_with_indicator)
                st.markdown(df_html.to_html(classes='gus-table', index=False, escape=False), unsafe_allow_html=True)
                if "Okres Bieżący" in df.columns:
                    df_bar = df.copy()[~df.copy()['Województwo'].str.contains('POLSKA', case=False)]
                    st.altair_chart(alt.Chart(df_bar).mark_bar().encode(x=alt.X('Województwo', sort='-y'), y='Okres Bieżący', tooltip=['Województwo', 'Okres Bieżący', 'Zmiana']).interactive(), use_container_width=True)
            elif chart['type'] == 'bar':
                df_bar = df.copy()[~df.copy()['Województwo'].str.contains('POLSKA', case=False)]
                st.altair_chart(alt.Chart(df_bar).mark_bar().encode(x=alt.X('Województwo', sort='-y'), y='Wartość', tooltip=['Województwo', 'Wartość']).interactive(), use_container_width=True)
                st.markdown(df.to_html(classes='gus-table', index=False), unsafe_allow_html=True)

def render_06_koszty():
    render_page_header("6. Koszty Budowy (GUS - AI Parser)", "")
    if st.session_state.data_loaded:
        if st.session_state.ceny_bud and st.session_state.ceny_bud.get('data') is not None:
            display_ai_section('koszty', st.session_state.ceny_bud['data'].to_string())
            headers = st.session_state.ceny_bud['headers']
            data = st.session_state.ceny_bud['data']
            h1, h2 = headers[0], headers[1]
            html = '<table class="gus-table"><thead><tr>'
            if "Kategoria" in data.columns and (not h1 or len(h1) < 2):
                for col in data.columns: html += f'<th>{col}</th>'
                html += '</tr></thead><tbody>'
                for _, row in data.iterrows():
                    html += f'<tr><td style="text-align:left;">{row.iloc[0]}</td>'
                    for idx in range(1, len(data.columns)): html += f'<td>{clean_number_formatting(row.iloc[idx])}</td>'
                    html += '</tr>'
            else:
                col_indices, i = [], 0
                while i < len(h1):
                    val1, val2 = str(h1[i]).replace('nan', '').strip(), str(h2[i]).replace('nan', '').strip()
                    if not val1 and not val2: i += 1; continue
                    col_indices.append(i); colspan = 1
                    if val1 and i + 1 < len(h1) and not str(h1[i+1]).replace('nan', '').strip(): colspan = 2; col_indices.append(i+1)
                    if val1: html += f'<th colspan="{colspan}">{val1}</th>'
                    i += colspan if val1 else 1
                html += '</tr><tr>'
                j = 0
                while j < len(col_indices):
                    idx = col_indices[j]; val = str(h2[idx]).replace('nan', '').strip(); colspan = 1
                    if j + 1 < len(col_indices) and not str(h2[col_indices[j+1]]).replace('nan', '').strip(): colspan = 2
                    if colspan == 2: html += f'<th colspan="2">{val}</th>'; j += 2
                    else: html += f'<th>{val}</th>'; j += 1
                html += '</tr></thead><tbody>'
                for _, row in data.iterrows():
                    html += f'<tr><td style="text-align:left;">{row.iloc[0]}</td>'
                    for idx in col_indices:
                        if idx < len(row): html += f'<td>{clean_number_formatting(row.iloc[idx])}</td>'
                    html += '</tr>'
            html += '</tbody></table>'
            st.markdown(html, unsafe_allow_html=True)

def render_07_kredyty():
    st.header("7. Rynek Kredytowy (BIK)")
    if st.session_state.data_loaded:
        display_ai_section('bik', "Dane BIK są interaktywnymi iFrame'ami pobieranymi z Tableau Public.")
        render_bik_section("Sprzedaż Kredytów", "https://public.tableau.com/views/BIKKIkolory1170BIKPreview/SprzedaKIokno")
        render_bik_section("Portfel Kredytów", "https://public.tableau.com/views/BIKKIkolory1170BIKPreview/PortfelKIokno")
        render_bik_section("Kredytobiorcy", "https://public.tableau.com/views/BIKKIkolory1170BIKPreview/KlienciBIKKIokno")
    else:
        st.warning("Najpierw pobierz dane w zakładce głównej!")

# ==========================================
# RENDEROWANIE GŁÓWNEGO WIDOKU
# ==========================================

if st.session_state.data_loaded:
    st.title(f"Raport Rynku Nieruchomości: {st.session_state.miesiac} {st.session_state.rok}")
    st.markdown("Poniżej znajduje się pełny podgląd 1:1 wszystkich pobranych modułów, tabel i interaktywnych wykresów.")
    
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
    st.divider()

    # Generator Pełnego HTML / PDF
    html_report = generate_full_html_report(st.session_state)
    b64 = base64.b64encode(html_report.encode('utf-8')).decode()
    st.markdown(f'<a href="data:file/html;base64,{b64}" download="Pelny_Raport_Nieruchomosci.html" style="text-decoration:none;"><button style="background:#FF4B4B; color:white; padding:15px; border:none; border-radius:8px; width:100%; cursor:pointer; font-size:16px; font-weight:bold;">📥 POBIERZ PEŁNY RAPORT W HTML/PDF (Zawiera wszystkie Tabele i Wykresy!)</button></a>', unsafe_allow_html=True)
    st.divider()

    st.markdown("## 📊 ZBIORCZY PODGLĄD ZAKŁADEK 1:1")

    render_01_nbp()
    st.markdown("---")
    
    render_02_inflacja()
    st.markdown("---")
    
    render_03_praca()
    st.markdown("---")
    
    render_04_budownictwo()
    st.markdown("---")
    
    render_05_kwartalne()
    st.markdown("---")
    
    render_06_koszty()
    st.markdown("---")
    
    render_07_kredyty()
    
    dodatkowe = sorted([f for f in glob.glob("pages/*.py") if re.search(r'\d{2}_', f) and "00_AI_Panel" not in f and int(re.search(r'\d{2}', f).group()) > 7])
    if dodatkowe:
        st.divider()
        st.markdown("## 🤖 TWOJE DYNAMICZNE MODUŁY AI")
        for plik in dodatkowe:
            try:
                with open(plik, "r", encoding="utf-8") as file: content = file.read()
                meta_match = re.search(r'# === META START ===\nMETA_JSON = r"""(.*?)"""\n# === META END ===', content, re.DOTALL)
                if meta_match:
                    meta = json.loads(meta_match.group(1))
                    render_dynamic_section(meta, plik, is_in_app=True)
                    st.markdown("---")
            except: pass
else:
    st.info("👈 Wpisz klucz API w menu po lewej i kliknij 'POBIERZ GŁÓWNE DANE DO RAPORTU'.")