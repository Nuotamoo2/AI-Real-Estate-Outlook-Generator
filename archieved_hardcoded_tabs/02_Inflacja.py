import streamlit as st
import altair as alt
from datetime import timedelta
from utils import setup_session_state, load_css, render_sidebar, display_ai_section, format_with_indicator

st.set_page_config(page_title="Inflacja", layout="wide")
setup_session_state()
load_css()
render_sidebar()

st.header("2. Inflacja (GUS)")
if st.session_state.data_loaded and st.session_state.inflacja and st.session_state.inflacja['df'] is not None:
    df = st.session_state.inflacja['df']
    display_ai_section('inflacja', df.head(24).to_string())
    
    max_date = df['Date'].max()
    min_zoom_date = max_date - timedelta(days=365*5)
    
    base = alt.Chart(df).encode(x=alt.X('Date', title='Data', axis=alt.Axis(format='%Y-%m'), scale=alt.Scale(domain=[min_zoom_date, max_date])), y=alt.Y('Inflacja %', title='Zmiana %', scale=alt.Scale(zero=False)), color=alt.Color('Metoda', title='Sposób prezentacji', legend=alt.Legend(orient='bottom', columns=1)))
    nearest = alt.selection_point(nearest=True, on='mouseover', fields=['Date'], empty=False)
    lines = base.mark_line(point=True, clip=True)
    selectors = base.mark_point().encode(opacity=alt.value(0)).add_params(nearest)
    points = base.mark_point().encode(opacity=alt.condition(nearest, alt.value(1), alt.value(0)))
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
        html += f'<td style="background-color:#ffffff; text-align:left; font-weight:600;">{row["Miesiąc Nazwa"]}</td><td style="background-color:#ffffff;">{format_with_indicator(row["Inflacja %"], inverse=True)}</td></tr>'
    html += '</tbody></table>'
    st.markdown(html, unsafe_allow_html=True)
else:
    st.warning("Najpierw pobierz dane w zakładce głównej!")