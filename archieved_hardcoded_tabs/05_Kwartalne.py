import streamlit as st
import altair as alt
from utils import setup_session_state, load_css, render_sidebar, display_ai_section, format_with_indicator

st.set_page_config(page_title="Budownictwo Kwartalne", layout="wide")
setup_session_state()
load_css()
render_sidebar()

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
            color=alt.Color('Wartość', scale=alt.Scale(scheme='blues'), legend=None), tooltip=['Województwo', 'Wartość']
        ).interactive()
        st.altair_chart(chart_map, use_container_width=True)
        st.markdown(df_map.to_html(classes='gus-table', index=False), unsafe_allow_html=True)
        
    for chart in gk['wykresy']:
        st.subheader(chart['title'])
        df = chart['data']
        if chart['type'] == 'pie':
            base = alt.Chart(df).encode(theta=alt.Theta("Udział", stack=True))
            pie = base.mark_arc(outerRadius=120).encode(color=alt.Color("Kategoria", legend=alt.Legend(orient="left", columns=1, labelLimit=300)), order=alt.Order("Udział", sort="descending"), tooltip=["Kategoria", "Udział"])
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
else:
    st.warning("Najpierw pobierz dane w zakładce głównej!")