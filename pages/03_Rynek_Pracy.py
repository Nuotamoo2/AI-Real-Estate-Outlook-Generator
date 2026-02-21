import streamlit as st
import altair as alt
from utils import setup_session_state, load_css, render_sidebar, display_ai_section, prepare_data_for_chart_aggregate

setup_session_state()
load_css()
render_sidebar()

st.header("3. Rynek Pracy (GUS)")
if st.session_state.data_loaded and st.session_state.gus_praca:
    display_ai_section('praca', st.session_state.gus_praca['tablica_1'])
    if st.session_state.gus_praca['tablica_1'] is not None:
        st.markdown(st.session_state.gus_praca['tablica_1'].to_html(classes='gus-table', border=0, na_rep=""), unsafe_allow_html=True)
        
    for chart in st.session_state.gus_praca['wykresy']:
        st.subheader(chart['title'])
        val_col = chart.get('val_col', 'Wartość')
        chart_data = prepare_data_for_chart_aggregate(chart['full_data'], val_col)
        
        if not chart_data.empty:
            df_plot = chart_data.reset_index().melt('Okres', var_name='Wskaźnik', value_name='Wartość')
            st.altair_chart(alt.Chart(df_plot).mark_line(point=True).encode(x='Okres', y=alt.Y('Wartość', scale=alt.Scale(zero=False)), color='Wskaźnik').interactive(), use_container_width=True)
            
        for y, data in chart['data'].items():
            st.markdown(f"**Rok {y}**")
            st.markdown(data['display'].to_html(classes='gus-table', index=False, border=0), unsafe_allow_html=True)
else:
    st.warning("Najpierw pobierz dane na stronie głównej!")