import streamlit as st
import pandas as pd
import altair as alt
from utils import setup_session_state, load_css, render_sidebar, display_ai_section

st.set_page_config(page_title="Magiczny Panel AI", layout="wide")
setup_session_state()
load_css()
render_sidebar()

st.header("🪄 Magiczny Panel AI")
st.info("Tutaj lądują wszystkie tabele z uniwersalnego linku (wpisanego w bocznym panelu), które AI samodzielnie rozszyfrowało i nadało im kształt!")

if st.session_state.data_loaded and st.session_state.universal_data:
    ud = st.session_state.universal_data
    if "tables" in ud:
        display_ai_section('universal', str(ud))
        
        for idx, table in enumerate(ud["tables"]):
            st.subheader(table.get("dataset_name", f"Znaleziona Tabela {idx+1}"))
            df = pd.DataFrame(table.get("data", []))
            
            if not df.empty:
                chart_type = table.get("recommended_chart", "none")
                x_col = table.get("x_axis_column")
                y_cols = table.get("y_axis_columns", [])
                
                # Zobacz jak AI samo decyduje co nam narysować!
                if chart_type == "line" and x_col and y_cols:
                    df_plot = df.melt(id_vars=[x_col], value_vars=y_cols, var_name='Legenda', value_name='Wartość')
                    st.altair_chart(alt.Chart(df_plot).mark_line(point=True).encode(x=alt.X(x_col, sort=None), y='Wartość', color='Legenda').interactive(), use_container_width=True)
                elif chart_type == "bar" and x_col and y_cols:
                    df_plot = df.melt(id_vars=[x_col], value_vars=y_cols, var_name='Legenda', value_name='Wartość')
                    st.altair_chart(alt.Chart(df_plot).mark_bar().encode(x=alt.X(x_col, sort='-y'), y='Wartość', color='Legenda', tooltip=[x_col, 'Wartość', 'Legenda']).interactive(), use_container_width=True)
                elif chart_type == "pie" and x_col and y_cols:
                    base = alt.Chart(df).encode(theta=alt.Theta(y_cols[0], stack=True))
                    pie = base.mark_arc(outerRadius=120).encode(color=alt.Color(x_col, legend=alt.Legend(title=x_col)), tooltip=[x_col, y_cols[0]])
                    st.altair_chart(pie, use_container_width=True)
                elif chart_type == "none":
                    st.info("💡 Zgodnie z decyzją AI, te dane to zwykła tablica poglądowa - wyświetlam tylko tabelę bez wykresu.")
                
                st.markdown(df.to_html(classes='gus-table', index=False), unsafe_allow_html=True)
else:
    st.warning("Najpierw wklej dodatkowy link w lewym panelu i kliknij 'POBIERZ DANE DO RAPORTU'!")