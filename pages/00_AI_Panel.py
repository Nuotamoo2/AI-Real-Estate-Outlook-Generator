import streamlit as st
import pandas as pd
import altair as alt
import os
import glob
import re
import json
import requests
import io
from utils import setup_session_state, load_css, render_sidebar, clean_url, clean_ai_json_output, ai_analyze_custom_sheets

st.set_page_config(page_title="Studio Zakładek", layout="wide")
setup_session_state()
load_css()
render_sidebar()

os.makedirs("archive", exist_ok=True)
os.makedirs("pages", exist_ok=True)

st.title("🛠️ Studio Zakładek i Menedżer Raportów")

tab_kreator, tab_menedzer = st.tabs(["🪄 Kreator (Nowa / Edycja)", "🗄️ Zarządzanie i Archiwum"])

with tab_kreator:
    st.info("Podaj bazowy link. Stworzysz z niego szablon logiki, który na zawsze zapisze się jako zakładka. Będziesz mógł podmieniać jego link w panelu bocznym!")
    
    if 'builder_step' not in st.session_state: st.session_state.builder_step = 1
    if 'builder_excel' not in st.session_state: st.session_state.builder_excel = None
    if 'builder_sheets' not in st.session_state: st.session_state.builder_sheets = []
    
    link_universal = st.text_input("🔗 1. Wklej bazowy link do pliku GUS:", value=st.session_state.get('builder_link', ''))

    if st.button("Pobierz strukturę i pokaż arkusze"):
        if link_universal:
            try:
                resp = requests.get(clean_url(link_universal), headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
                if resp.status_code == 200:
                    excel = pd.ExcelFile(io.BytesIO(resp.content))
                    st.session_state.builder_excel = resp.content
                    st.session_state.builder_sheets = excel.sheet_names
                    st.session_state.builder_link = link_universal
                    st.session_state.builder_step = 2
                    st.success(f"Plik wczytany! Odnaleziono {len(excel.sheet_names)} arkuszy.")
                else: st.error("Błąd pobierania pliku.")
            except Exception as e: st.error(f"Błąd odczytu pliku: {e}")

    if st.session_state.builder_step >= 2:
        st.divider()
        st.subheader("2. Wybór arkuszy do analizy")
        def_sheets = [s for s in st.session_state.builder_sheets if not any(k in s.lower() for k in ['spis', 'uwag'])]
        selected_sheets = st.multiselect("Zaznacz arkusze z danymi (AI je odczyta i ustali kolumny):", st.session_state.builder_sheets, default=def_sheets)
        st.session_state.builder_selected_sheets = selected_sheets
        
        if st.button("Uruchom AI na wybranych arkuszach", type="primary"):
            if not st.session_state.gemini_key: st.error("Wymagany klucz API w panelu bocznym!")
            elif not selected_sheets: st.warning("Wybierz chociaż jeden arkusz.")
            else:
                try:
                    with st.spinner("AI analizuje struktury i buduje tabele... To potrwa kilka sekund."):
                        excel = pd.ExcelFile(io.BytesIO(st.session_state.builder_excel))
                        csv_text = "".join([f"\n--- ZAKŁADKA: {s} ---\n{pd.read_excel(excel, sheet_name=s, header=None).dropna(how='all', axis=0).dropna(how='all', axis=1).head(50).to_csv(index=False)}" for s in selected_sheets])
                        
                        parsed = ai_analyze_custom_sheets(csv_text, st.session_state.gemini_key, st.session_state.model_name)
                        if parsed and "tables" in parsed:
                            st.session_state.builder_data = parsed["tables"]
                            st.session_state.builder_step = 3
                        else: st.error("AI nie odnalazło tabel w pliku. Wybierz inne arkusze.")
                except Exception as e:
                    st.error(f"Wystąpił błąd AI. Sprawdź swój klucz. Komunikat: {e}")

    if st.session_state.builder_step == 3 and st.session_state.get('builder_data'):
        st.divider()
        st.subheader("3. Edytor Układu i Danych (Tworzenie Szablonu)")
        
        tab_name = st.text_input("Nazwa nowej zakładki w menu (Oraz tytuł w raporcie):", value=st.session_state.get('edit_tab_name', "Nowy Raport"))
        tab_desc = st.text_input("Opis ścieżki:", value=st.session_state.get('edit_tab_desc', "Obszary tematyczne -> ..."))
        
        for idx, table in enumerate(st.session_state.builder_data):
            st.markdown(f"#### Element {idx+1}: {table.get('dataset_name', 'Brak nazwy')}")
            new_table_name = st.text_input(f"Tytuł powyższej sekcji", value=table.get("dataset_name", f"Tabela {idx+1}"), key=f"t_name_{idx}")
            st.session_state.builder_data[idx]["dataset_name"] = new_table_name
            
            df = pd.DataFrame(table.get("data", []))
            if df.empty: continue
            kolumny = df.columns.tolist()
            
            st.markdown("**Zmiana nazw kolumn (zmieni się na stałe w szablonie):**")
            new_cols = {}
            col_layout = st.columns(min(len(kolumny), 4) if len(kolumny) > 0 else 1)
            for i, col in enumerate(kolumny):
                with col_layout[i % len(col_layout)]:
                    new_cols[col] = st.text_input(f"Zmień '{col}':", value=col, key=f"rn_{idx}_{col}")
            df = df.rename(columns=new_cols)
            kolumny = df.columns.tolist() 
            
            c1, c2 = st.columns([1, 2])
            with c1:
                t_chart = st.selectbox(f"Typ wykresu", ["line", "bar", "pie", "scatter", "area", "none"], index=["line", "bar", "pie", "scatter", "area", "none"].index(table.get("recommended_chart", "none")) if table.get("recommended_chart") in ["line", "bar", "pie", "scatter", "area", "none"] else 0, key=f"c_{idx}")
                t_x = st.selectbox(f"Oś X (Kategorie/Czas)", kolumny, index=kolumny.index(new_cols.get(table.get("x_axis_column"), kolumny[0])) if new_cols.get(table.get("x_axis_column")) in kolumny else 0, key=f"x_{idx}")
                def_y = [new_cols.get(y) for y in table.get("y_axis_columns", []) if new_cols.get(y) in kolumny]
                t_y = st.multiselect(f"Oś Y (Wartości liczbowe)", kolumny, default=def_y, key=f"y_{idx}")
                
                k_up, k_dw, k_del = st.columns(3)
                if k_up.button("⬆️ Wyżej", key=f"u_{idx}") and idx > 0:
                    st.session_state.builder_data.insert(idx-1, st.session_state.builder_data.pop(idx)); st.rerun()
                if k_dw.button("⬇️ Niżej", key=f"d_{idx}") and idx < len(st.session_state.builder_data)-1:
                    st.session_state.builder_data.insert(idx+1, st.session_state.builder_data.pop(idx)); st.rerun()
                if k_del.button("❌ Usuń tabelę", key=f"del_{idx}"):
                    st.session_state.builder_data.pop(idx); st.rerun()
                    
            with c2:
                st.caption("Poniżej możesz dodawać/usuwać wiersze z tabeli lub poprawiać liczby!")
                edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True, key=f"ed_{idx}")
                st.session_state.builder_data[idx]['data'] = edited_df.to_dict('records')
                st.session_state.builder_data[idx]['recommended_chart'] = t_chart
                st.session_state.builder_data[idx]['x_axis_column'] = t_x
                st.session_state.builder_data[idx]['y_axis_columns'] = t_y
                
                if t_chart != "none" and t_x and t_y:
                    try:
                        df_plot = edited_df.melt(id_vars=[t_x], value_vars=t_y, var_name='Legenda', value_name='Wartość')
                        if t_chart == "line": c = alt.Chart(df_plot).mark_line(point=True).encode(x=alt.X(t_x, sort=None), y='Wartość', color='Legenda')
                        elif t_chart == "bar": c = alt.Chart(df_plot).mark_bar().encode(x=alt.X(t_x, sort='-y'), y='Wartość', color='Legenda')
                        elif t_chart == "scatter": c = alt.Chart(df_plot).mark_circle(size=60).encode(x=alt.X(t_x, sort=None), y='Wartość', color='Legenda')
                        elif t_chart == "area": c = alt.Chart(df_plot).mark_area(opacity=0.5).encode(x=alt.X(t_x, sort=None), y='Wartość', color='Legenda')
                        elif t_chart == "pie": c = alt.Chart(edited_df).mark_arc().encode(color=t_x, theta=t_y[0], tooltip=[t_x, t_y[0]])
                        st.altair_chart(c.interactive(), use_container_width=True)
                    except: st.warning("Zły dobór osi do wykresu. Oś Y musi być liczbą.")
        
        st.divider()
        if st.button("💾 ZAPISZ TĘ ZAKŁADKĘ DO APLIKACJI (KOD)", type="primary", use_container_width=True):
            safe_name = re.sub(r'[^a-zA-Z0-9]', '_', tab_name)
            existing_file = st.session_state.get('edit_file_target')
            
            if existing_file:
                py_file = existing_file
            else:
                files = glob.glob("pages/*.py")
                max_num = 8
                for f in files:
                    m = re.search(r'(\d+)_', f)
                    if m: max_num = max(max_num, int(m.group(1)))
                next_num = str(max_num + 1).zfill(2)
                py_file = f"pages/{next_num}_{safe_name}.py"
            
            meta_data = {
                "tab_name": tab_name, 
                "tab_desc": tab_desc, 
                "link": st.session_state.builder_link, 
                "selected_sheets": st.session_state.get("builder_selected_sheets", []),
                "tables": st.session_state.builder_data
            }
            
            meta_json_str = json.dumps(meta_data, ensure_ascii=False)
            
            kod = f'''import streamlit as st, pandas as pd, altair as alt, json, os, re
from utils import setup_session_state, load_css, render_sidebar, render_dynamic_section

st.set_page_config(page_title="{tab_name}", layout="wide")
setup_session_state(); load_css(); render_sidebar()

# === META START ===
META_JSON = r"""{meta_json_str}"""
# === META END ===

try:
    meta = json.loads(META_JSON)
    render_dynamic_section(meta, __file__, is_in_app=False)
except Exception as e:
    st.error(f"Błąd ładowania danych zakładki: {{e}}")
'''
            with open(py_file, "w", encoding="utf-8") as f: f.write(kod)
            st.session_state.edit_file_target = None
            st.success(f"✅ Zapisano zakładkę! Użyj opcji 'Odśwież' z prawego górnego rogu przeglądarki (klawisz F5).")

with tab_menedzer:
    col_akt, col_arch = st.columns(2)
    with col_akt:
        st.subheader("🟢 Aktywne Zakładki (Widoczne w lewym panelu)")
        pliki = sorted([f for f in glob.glob("pages/*.py") if "00_AI_Panel" not in f])
        
        for p in pliki:
            nazwa = os.path.basename(p)
            c1, c2 = st.columns([3, 1])
            c1.write(f"📄 {nazwa}")
            if c2.button("📦 Archiwizuj", key=f"arch_{nazwa}"):
                import shutil
                shutil.move(p, f"archive/{nazwa}")
                st.rerun()

    with col_arch:
        st.subheader("📦 Zarchiwizowane (Ukryte z lewego panelu)")
        zarch = sorted(glob.glob("archive/*.py"))
        
        for p in zarch:
            nazwa = os.path.basename(p)
            c1, c2, c3 = st.columns([2, 1, 1])
            c1.write(f"📁 {nazwa}")
            if c2.button("♻️ Przywróć", key=f"rest_{nazwa}"):
                import shutil
                shutil.move(p, f"pages/{nazwa}")
                st.rerun()
            if c3.button("❌ Usuń trwale", key=f"del_{nazwa}"):
                os.remove(p)
                st.rerun()