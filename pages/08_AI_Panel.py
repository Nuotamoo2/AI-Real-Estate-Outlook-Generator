import streamlit as st
import pandas as pd
import altair as alt
import os
import glob
import re
from utils import setup_session_state, load_css, render_sidebar, get_universal_data_ai

st.set_page_config(page_title="Magiczny Panel AI", layout="wide")
setup_session_state()
load_css()
render_sidebar()

st.header("🪄 Studio Tworzenia Zakładek (Magiczny Panel AI)")
st.markdown("Wklej link, dostosuj dane i układ, a następnie wygeneruj nową zakładkę w swoim raporcie!")

# KROK 1: POBIERANIE DANYCH
link_universal = st.text_input("1. Wklej link do dowolnego Excela z GUS:", value="")

if st.button("Pobierz i Przeanalizuj za pomocą AI"):
    if not st.session_state.gemini_key:
        st.error("Wymagany klucz API w panelu bocznym!")
    elif link_universal:
        with st.spinner("AI analizuje plik i wyciąga strukturę..."):
            dane = get_universal_data_ai(link_universal, st.session_state.gemini_key, st.session_state.model_name)
            if dane and "tables" in dane and len(dane["tables"]) > 0:
                # Bierzemy pierwszą znalezioną tabelę do kreatora
                st.session_state.builder_data = dane["tables"][0]
                st.session_state.builder_df = pd.DataFrame(st.session_state.builder_data["data"])
                st.session_state.builder_link = link_universal
            else:
                st.error("Nie udało się odczytać tabeli.")

# KROK 2: KREATOR (Pokazuje się tylko, jeśli mamy pobrane dane)
if st.session_state.get('builder_df') is not None and not st.session_state.builder_df.empty:
    st.divider()
    st.subheader("2. Edytor i Podgląd")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.markdown("**Konfiguracja Wykresu**")
        df = st.session_state.builder_df
        kolumny = df.columns.tolist()
        
        # UI do wyboru typu wykresu
        chart_type = st.selectbox("Typ wykresu", ["line (Liniowy)", "bar (Słupkowy)", "none (Tylko tabela)"])
        chart_type_clean = chart_type.split(" ")[0]
        
        # Wybór osi X i Y
        x_col = st.selectbox("Oś X (Kategorie/Czas)", kolumny)
        y_cols = st.multiselect("Oś Y (Wartości liczbowe)", kolumny, default=[c for c in kolumny if c != x_col])
        
        st.markdown("**Metadane Nowej Zakładki**")
        tab_name = st.text_input("Krótka nazwa zakładki (np. Ceny Mleka)", value=st.session_state.builder_data.get("dataset_name", "Nowy Raport"))
        tab_desc = st.text_input("Instrukcja/Ścieżka (wyświetlana pod tytułem)", value="Obszary tematyczne -> ...")
        
    with col2:
        st.markdown("**Podgląd Wykresu**")
        # Rysowanie podglądu na żywo
        if chart_type_clean != "none" and x_col and y_cols:
            try:
                df_plot = df.melt(id_vars=[x_col], value_vars=y_cols, var_name='Legenda', value_name='Wartość')
                if chart_type_clean == "line":
                    c = alt.Chart(df_plot).mark_line(point=True).encode(x=alt.X(x_col, sort=None), y='Wartość', color='Legenda').interactive()
                else:
                    c = alt.Chart(df_plot).mark_bar().encode(x=alt.X(x_col, sort='-y'), y='Wartość', color='Legenda').interactive()
                st.altair_chart(c, use_container_width=True)
            except Exception as e:
                st.warning("Nie można narysować wykresu. Upewnij się, że na osi Y są liczby.")
        else:
            st.info("Wybrano opcję 'Tylko tabela' lub brak kolumn.")
            
        st.markdown("**Dane (Możesz je edytować przed zapisem!)**")
        # INTERAKTYWNY EDYTOR DANYCH
        edited_df = st.data_editor(df, use_container_width=True, num_rows="dynamic")
        
    # KROK 3: GENERATOR KODU PYTHON
    st.divider()
    if st.button("💾 UTWÓRZ ZAKŁADKĘ Z TYM RAPORTEM", type="primary", use_container_width=True):
        # 1. Znajdź następny numer pliku dla nowej zakładki
        files = glob.glob("pages/*.py")
        max_num = 8
        for f in files:
            m = re.search(r'(\d+)_', f)
            if m: max_num = max(max_num, int(m.group(1)))
        next_num = str(max_num + 1).zfill(2)
        
        # Bezpieczna nazwa pliku (bez spacji i znaków specjalnych)
        safe_name = re.sub(r'[^a-zA-Z0-9]', '_', tab_name)
        file_name = f"pages/{next_num}_{safe_name}.py"
        
        # 2. Tworzymy kod w Pythonie, który zostanie zapisany w nowym pliku!
        # Używamy szablonu, w który wklejamy wybory użytkownika.
        
        kod_pythona = f'''import streamlit as st
import pandas as pd
import altair as alt
import json
from utils import setup_session_state, load_css, render_sidebar, display_ai_section, ai_extract_table

st.set_page_config(page_title="{tab_name}", layout="wide")
setup_session_state()
load_css()
render_sidebar()

st.header("{tab_name}")

# Możliwość edycji opisu przez użytkownika (zapisywane w session_state na czas trwania sesji)
if 'desc_{safe_name}' not in st.session_state:
    st.session_state['desc_{safe_name}'] = "{tab_desc}"
    
nowy_opis = st.text_input("Opis ścieżki (możesz go zmienić w każdej chwili):", value=st.session_state['desc_{safe_name}'])
st.session_state['desc_{safe_name}'] = nowy_opis

link = st.text_input("Link do najnowszych danych GUS:", value="{st.session_state.builder_link}")

# Instrukcja generowana dla AI
instrukcja_ai = "Wyciągnij tabelę. Zachowaj kolumny dokładnie w takiej formie."
oczekiwane_kolumny = {kolumny}

if st.button("Pobierz i wygeneruj wykresy"):
    if not st.session_state.gemini_key:
        st.error("Wymagany klucz API w panelu bocznym!")
    else:
        with st.spinner("AI czyta nową tabelę z linku..."):
            # Używamy naszego silnika z utils.py
            nowe_dane = ai_extract_table(link, instrukcja_ai, oczekiwane_kolumny, st.session_state.gemini_key, st.session_state.model_name, "{tab_name}")
            if nowe_dane is not None:
                st.session_state['data_{safe_name}'] = nowe_dane

# Renderowanie widoku jeśli mamy zapisane dane
if st.session_state.get('data_{safe_name}') is not None:
    df = st.session_state['data_{safe_name}']
    
    st.markdown("**Tabela Danych (możesz korygować liczby w locie)**")
    df = st.data_editor(df, use_container_width=True, num_rows="dynamic")
    
    chart_type = "{chart_type_clean}"
    x_col = "{x_col}"
    y_cols = {y_cols}
    
    if chart_type != "none" and x_col in df.columns:
        try:
            # Rysowanie wybranego typu wykresu
            df_plot = df.melt(id_vars=[x_col], value_vars=[y for y in y_cols if y in df.columns], var_name='Legenda', value_name='Wartość')
            if chart_type == "line":
                c = alt.Chart(df_plot).mark_line(point=True).encode(x=alt.X(x_col, sort=None), y='Wartość', color='Legenda').interactive()
            else:
                c = alt.Chart(df_plot).mark_bar().encode(x=alt.X(x_col, sort='-y'), y='Wartość', color='Legenda').interactive()
            st.altair_chart(c, use_container_width=True)
        except Exception as e:
            st.warning("Oś Y musi zawierać wartości liczbowe.")
            
    display_ai_section('{safe_name}', df.to_string())
'''

        # 3. Zapis pliku na dysk
        try:
            with open(file_name, "w", encoding="utf-8") as f:
                f.write(kod_pythona)
            st.success(f"✅ Sukces! Utworzono nową zakładkę. Odśwież stronę przeglądarki (F5), aby pojawiła się w menu po lewej.")
            # Czyścimy bufor
            st.session_state.builder_df = None
            st.session_state.builder_data = None
        except Exception as e:
            st.error(f"Nie udało się zapisać pliku: {e}")