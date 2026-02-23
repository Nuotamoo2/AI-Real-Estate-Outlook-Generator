import streamlit as st, pandas as pd, altair as alt
from utils import setup_session_state, load_css, render_sidebar, display_ai_section, prepare_data_for_chart_aggregate, prepare_yearly_comparison_data, get_month_number, MONTH_ORDER, render_page_header
st.set_page_config(page_title="Rynek Pracy", layout="wide")
setup_session_state(); load_css(); render_sidebar()
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
        val_col, dyn_col = chart.get('val_col', 'Wartość'), chart.get('dyn_col', None)
        chart_data = prepare_data_for_chart_aggregate(chart['full_data'], val_col)
        if not chart_data.empty:
            is_wages = "wynagrodzenia" in chart['title'].lower()
            if val_col in chart_data.columns and not is_wages:
                try:
                    df_calc = chart_data.copy()
                    df_temp = df_calc.copy()
                    df_temp.index = pd.to_datetime(df_temp.index + '-01')
                    df_temp['prev_date'] = df_temp.index - pd.DateOffset(years=1)
                    date_val_map = df_temp[val_col].to_dict()
                    df_calc['Analogiczny okres roku poprzedniego'] = df_temp['prev_date'].map(date_val_map).values
                    if dyn_col and dyn_col in df_calc.columns:
                        df_calc[dyn_col] = pd.to_numeric(df_calc[dyn_col], errors='coerce')
                        calculated_prev = df_calc[val_col] / (df_calc[dyn_col] / 100.0)
                        df_calc['Analogiczny okres roku poprzedniego'] = df_calc['Analogiczny okres roku poprzedniego'].combine_first(calculated_prev.round(1))
                    df_plot = df_calc[[val_col, 'Analogiczny okres roku poprzedniego']].reset_index().melt('Okres', var_name='Wskaźnik', value_name='Wartość')
                    nearest = alt.selection_point(nearest=True, on='mouseover', fields=['Okres'], empty=False)
                    base = alt.Chart(df_plot).encode(x=alt.X('Okres', sort=None), y=alt.Y('Wartość', scale=alt.Scale(zero=False)), color=alt.Color('Wskaźnik', title='Legenda', legend=alt.Legend(labelLimit=0, titleLimit=0)))
                    lines, points = base.mark_line(point=True), base.mark_point().transform_filter(nearest)
                    rule = alt.Chart(df_plot).mark_rule(color='gray').encode(x='Okres').transform_filter(nearest)
                    selectors = base.mark_point().encode(opacity=alt.value(0), tooltip=['Okres', 'Wskaźnik', 'Wartość']).add_params(nearest)
                    text = lines.mark_text(align='left', dx=5, dy=-5).encode(text=alt.condition(nearest, 'Wartość:Q', alt.value(' ')))
                    st.altair_chart(alt.layer(lines, selectors, rule, points, text).interactive(), use_container_width=True)
                except: st.line_chart(chart_data)
            else:
                df_plot = chart_data.reset_index().melt('Okres', var_name='Wskaźnik', value_name='Wartość')
                st.altair_chart(alt.Chart(df_plot).mark_line(point=True).encode(x='Okres', y=alt.Y('Wartość', scale=alt.Scale(zero=False)), color='Wskaźnik').interactive(), use_container_width=True)
        years = sorted(chart['data'].keys(), reverse=True)
        for y in years:
            st.markdown(f"**Rok {y}**")
            df_display = chart['data'][y]['display'].copy()
            df_display['sort_idx'] = df_display['Miesiąc'].apply(get_month_number)
            st.markdown(df_display.sort_values('sort_idx', ascending=True).drop(columns=['sort_idx']).to_html(classes='gus-table', index=False, border=0), unsafe_allow_html=True)
            if is_wages:
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
else: st.warning("Najpierw pobierz dane w zakładce głównej!")