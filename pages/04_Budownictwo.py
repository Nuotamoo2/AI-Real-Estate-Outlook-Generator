import streamlit as st
import altair as alt
from utils import setup_session_state, load_css, render_sidebar, display_ai_section, prepare_data_for_chart_aggregate, clean_number_formatting, get_month_number, MONTH_ORDER, parse_float_safe

st.set_page_config(page_title="Budownictwo", layout="wide")
setup_session_state()
load_css()
render_sidebar()

st.header("4. Budownictwo Mieszkaniowe (GUS)")
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
                nearest = alt.selection_point(nearest=True, on='mouseover', fields=['Okres'], empty=False)
                base = alt.Chart(df_plot).encode(x=alt.X('Okres', sort=None), y=alt.Y('Wartość', scale=alt.Scale(zero=False)), color=alt.Color('Kategoria', title='Legenda', legend=alt.Legend(labelLimit=0, titleLimit=0)))
                lines = base.mark_line(point=True)
                points = base.mark_point().transform_filter(nearest)
                rule = alt.Chart(df_plot).mark_rule(color='gray').encode(x='Okres').transform_filter(nearest)
                selectors = base.mark_point().encode(opacity=alt.value(0), tooltip=['Okres', 'Kategoria', 'Wartość']).add_params(nearest)
                text = lines.mark_text(align='left', dx=5, dy=-5).encode(text=alt.condition(nearest, 'Wartość:Q', alt.value(' ')))
                st.altair_chart(alt.layer(lines, selectors, rule, points, text).interactive(), use_container_width=True)
                
        # Tabele od najnowszego roku pętlowo z osobnymi wykresami
        if 'Rok' in ts.columns:
            years = sorted(ts['Rok'].unique(), reverse=True)
            for y in years:
                st.subheader(f"Rok {y}")
                df_year = ts[ts['Rok'] == y].drop(columns=['Rok'])
                df_display = df_year.copy()
                for col in df_display.columns:
                    if col != "Miesiąc": df_display[col] = df_display[col].apply(clean_number_formatting)
                df_display['sort_idx'] = df_display['Miesiąc'].apply(get_month_number)
                df_display = df_display.sort_values('sort_idx', ascending=True).drop(columns=['sort_idx'])
                st.markdown(df_display.to_html(classes='gus-table', index=False, border=0), unsafe_allow_html=True)
                
                chart_year = df_year.copy()
                chart_year['sort_idx'] = chart_year['Miesiąc'].apply(get_month_number)
                chart_year = chart_year.sort_values('sort_idx').set_index('Miesiąc').drop(columns=['sort_idx'])
                if not chart_year.empty:
                    cols_to_plot = [c for c in ['Oddane do użytkowania', 'Rozpoczęte budowy', 'Wydane pozwolenia'] if c in chart_year.columns]
                    if cols_to_plot:
                        df_plot_y = chart_year[cols_to_plot].reset_index().melt(chart_year.index.name, var_name='Kategoria', value_name='Wartość')
                        # Zabezpieczenie przed błędem łączenia typów String i Int
                        df_plot_y['month_id'] = df_plot_y[chart_year.index.name].apply(get_month_number).astype(str)
                        nearest_y = alt.selection_point(nearest=True, on='mouseover', empty=False)
                        base_y = alt.Chart(df_plot_y).encode(x=alt.X(chart_year.index.name, sort=MONTH_ORDER, title=''), y=alt.Y('Wartość', scale=alt.Scale(zero=False)), color=alt.Color('Kategoria', title='Legenda', legend=alt.Legend(labelLimit=0, titleLimit=0)))
                        lines_y = base_y.mark_line(point=True)
                        points_y = base_y.mark_point().transform_filter(nearest_y)
                        rule_y = alt.Chart(df_plot_y).mark_rule(color='gray').encode(x=alt.X(chart_year.index.name, sort=MONTH_ORDER)).transform_filter(nearest_y)
                        selectors_y = base_y.mark_point().encode(opacity=alt.value(0), tooltip=[chart_year.index.name, 'Kategoria', 'Wartość']).add_params(nearest_y)
                        text_y = lines_y.mark_text(align='left', dx=5, dy=-5).encode(text=alt.condition(nearest_y, 'Wartość:Q', alt.value(' ')))
                        st.altair_chart(alt.layer(lines_y, selectors_y, rule_y, points_y, text_y).interactive(), use_container_width=True)
                        
        if bd["regional"] is not None:
            st.subheader("Dane Regionalne (Województwa i Miasta)")
            st.markdown("**Wykres Regionalny**")
            df_reg_chart = bd["regional"].copy()
            cols_num = ["Pozwolenia wydane", "Rozpoczęte budowy", "Oddane do użytkowania"]
            for c in cols_num: df_reg_chart[c] = df_reg_chart[c].apply(parse_float_safe)
            df_reg_chart = df_reg_chart[~df_reg_chart['Obszar'].str.contains('POLSKA', case=False, na=False)]
            df_melt = df_reg_chart.melt('Obszar', var_name='Kategoria', value_name='Wartość')
            chart_reg = alt.Chart(df_melt).mark_bar().encode(x=alt.X('Obszar', sort='-y', title='Województwo'), y=alt.Y('Wartość', title='Liczba mieszkań'), color=alt.Color('Kategoria', title='Legenda'), tooltip=['Obszar', 'Kategoria', 'Wartość']).interactive()
            st.altair_chart(chart_reg, use_container_width=True)
            st.markdown("**Tabela szczegółowa**")
            st.markdown(bd["regional"].to_html(classes='gus-table', index=False, border=0), unsafe_allow_html=True)
else:
    st.warning("Najpierw pobierz dane w zakładce głównej!")