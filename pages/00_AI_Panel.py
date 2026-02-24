import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import os
import glob
import re
import json
import requests
import io
import shutil
import uuid
from utils import setup_session_state, load_css, render_sidebar, clean_url, clean_ai_json_output, ai_analyze_custom_sheets

st.set_page_config(page_title="Studio Zakładek", layout="wide")
setup_session_state() # Tutaj aplikacja upewnia się, że pliki systemowe istnieją
load_css()
render_sidebar()

os.makedirs("archive", exist_ok=True)
os.makedirs("pages", exist_ok=True)
os.makedirs("prompts/active", exist_ok=True)
os.makedirs("prompts/archive", exist_ok=True)

st.title("🛠️ Studio Zakładek i Menedżer Raportów")

tab_kreator, tab_menedzer, tab_prompty = st.tabs(["🪄 Kreator (Nowa / Edycja)", "🗄️ Zarządzanie i Kolejność", "🧠 Główne Prompty (Silnik AI)"])

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
        
        st.markdown("### 🧠 Instrukcje czytania tabeli dla AI (Opcjonalne)")
        extraction_instruction = st.text_area(
            "Jeśli plik jest zawiły (np. pytania w wierszach, dziwne nagłówki), powiedz AI jak ma to potraktować:", 
            value=st.session_state.get('extraction_instruction', ''),
            placeholder="np. Tabela ma sekcje podzielone wierszami z pytaniami..."
        )
        st.session_state.extraction_instruction = extraction_instruction
        
        if st.button("Uruchom AI na wybranych arkuszach", type="primary"):
            if not st.session_state.gemini_key: st.error("Wymagany klucz API w panelu bocznym!")
            elif not selected_sheets: st.warning("Wybierz chociaż jeden arkusz.")
            else:
                try:
                    with st.spinner("AI analizuje struktury i buduje tabele... To potrwa kilka sekund."):
                        excel = pd.ExcelFile(io.BytesIO(st.session_state.builder_excel))
                        csv_text = "".join([f"\n--- ZAKŁADKA: {s} ---\n{pd.read_excel(excel, sheet_name=s, header=None).dropna(how='all', axis=0).dropna(how='all', axis=1).head(60).to_csv(index=False)}" for s in selected_sheets])
                        
                        parsed = ai_analyze_custom_sheets(csv_text, st.session_state.gemini_key, st.session_state.model_name, extraction_instruction)
                        if parsed and "tables" in parsed:
                            st.session_state.builder_data = parsed["tables"]
                            st.session_state.builder_report_title = parsed.get("report_title", "Raport z GUS")
                            st.session_state.builder_step = 3
                        else: st.error("AI nie odnalazło tabel w pliku. Wybierz inne arkusze.")
                except Exception as e:
                    st.error(f"Wystąpił błąd AI. Sprawdź swój klucz. Komunikat: {e}")

    if st.session_state.builder_step == 3 and st.session_state.get('builder_data'):
        st.divider()
        st.subheader("3. Edytor Układu i Danych (Tworzenie Szablonu)")
        
        col_title1, col_title2 = st.columns(2)
        with col_title1:
            tab_name = st.text_input("Nazwa nowej zakładki (w panelu po lewej):", value=st.session_state.get('edit_tab_name', "Nowy Raport"))
        with col_title2:
            default_report_title = st.session_state.get('edit_report_title', st.session_state.get('builder_report_title', "Nowy Raport"))
            report_title = st.text_input("Tytuł w raporcie (główny nagłówek strony):", value=default_report_title)
            
        tab_desc = st.text_input("Opis ścieżki (Instrukcja wyświetlana TYLKO w lewym menu nad linkiem):", value=st.session_state.get('edit_tab_desc', "GUS -> Obszary tematyczne -> ..."))
        
        for idx, table in enumerate(st.session_state.builder_data):
            st.markdown(f"#### Element {idx+1}: {table.get('dataset_name', 'Brak nazwy')}")
            new_table_name = st.text_input(f"Tytuł powyższej sekcji", value=table.get("dataset_name", f"Tabela {idx+1}"), key=f"t_name_{idx}")
            st.session_state.builder_data[idx]["dataset_name"] = new_table_name
            
            df_base = pd.DataFrame(table.get("data", []))
            if df_base.empty: continue
            
            if "applied_commands" not in table:
                old_code = table.get("pandas_code", "")
                table["applied_commands"] = [c.strip() for c in old_code.split('\n') if c.strip()]
                if "pandas_code" in table: del table["pandas_code"]

            with st.expander("🛠️ Pełna władza nad danymi (Historia operacji, Matematyka, Filtry)"):
                st.markdown("### 📜 Historia Zastosowanych Zmian")
                
                if not table["applied_commands"]:
                    st.caption("Brak zastosowanych zmian. Tabela jest w oryginalnym formacie.")
                else:
                    for i, cmd in enumerate(table["applied_commands"]):
                        c_cmd, c_del = st.columns([5, 1])
                        c_cmd.code(cmd, language="python")
                        
                        del_key = f"del_confirm_{idx}_{i}"
                        if st.session_state.get(del_key, False):
                            c_del.warning("Na pewno?")
                            c_y, c_n = c_del.columns(2)
                            if c_y.button("✔️", key=f"y_{idx}_{i}"):
                                table["applied_commands"].pop(i)
                                st.session_state[del_key] = False
                                st.rerun()
                            if c_n.button("❌", key=f"n_{idx}_{i}"):
                                st.session_state[del_key] = False
                                st.rerun()
                        else:
                            if c_del.button("🗑️ Usuń", key=f"del_{idx}_{i}", use_container_width=True):
                                st.session_state[del_key] = True
                                st.rerun()

                st.markdown("---")
                st.markdown("### ➕ Dodaj nową operację")
                new_cmd = st.text_area("Wpisz komendę Python (Twoja tabela to zmienna `df`):", height=68, key=f"new_cmd_{idx}")
                
                if st.button("▶️ Dodaj i Oblicz nową operację", key=f"btn_add_cmd_{idx}", type="primary"):
                    if new_cmd.strip():
                        table["applied_commands"].append(new_cmd.strip())
                        st.rerun()

            df_mod = df_base.copy()
            for cmd in table["applied_commands"]:
                try:
                    local_vars = {"df": df_mod, "pd": pd, "np": np}
                    exec(cmd, globals(), local_vars)
                    df_mod = local_vars["df"]
                except Exception as e:
                    st.error(f"⚠️ Błąd wykonania komendy: `{cmd}`\nSzczegóły: {e}")
            df = df_mod

            kolumny = df.columns.tolist()
            split_cols = ["Brak"] + kolumny
            split_val = table.get("split_by_column", "Brak")
            
            c_s1, c_s2 = st.columns([1, 1])
            with c_s1:
                split_sel = st.selectbox("🗂️ Grupuj/Podziel tabele według kolumny (np. Rok):", split_cols, index=split_cols.index(split_val) if split_val in split_cols else 0, key=f"split_{idx}")
                st.session_state.builder_data[idx]["split_by_column"] = "" if split_sel == "Brak" else split_sel

            if split_sel != "Brak" and split_sel in df.columns:
                unique_vals = sorted(df[split_sel].dropna().unique())
                with c_s2:
                    st.info(f"**Podział Dynamiczny Aktywny.** W raporcie powstaną automatycznie {len(unique_vals)} wykresy (dla: {', '.join(map(str, unique_vals))}). Szablon sam dostosuje się do nowych lat w przyszłości.")
                
                if st.button("✂️ Fizycznie rozbij tę tabelę na osobne niezależne bloki (Rozdziel i pozwól mi każdy konfigurować z osobna!)", key=f"phys_{idx}"):
                    new_blocks = []
                    for val in unique_vals:
                        new_block = table.copy()
                        new_block['dataset_name'] = f"{table.get('dataset_name', '')} - {val}"
                        new_block['data'] = df_base[df_base[split_sel] == val].to_dict('records') if split_sel in df_base.columns else df_base.to_dict('records')
                        new_block['split_by_column'] = "" 
                        new_blocks.append(new_block)
                    st.session_state.builder_data = st.session_state.builder_data[:idx] + new_blocks + st.session_state.builder_data[idx+1:]
                    st.rerun()

            st.markdown("---")
            c1, c2 = st.columns([1, 2])
            with c1:
                t_chart = st.selectbox(f"Typ wykresu", ["line", "bar", "pie", "scatter", "area", "none"], index=["line", "bar", "pie", "scatter", "area", "none"].index(table.get("recommended_chart", "none")) if table.get("recommended_chart") in ["line", "bar", "pie", "scatter", "area", "none"] else 0, key=f"c_{idx}")
                t_x = st.selectbox(f"Oś X (Kategorie/Czas)", kolumny, index=kolumny.index(table.get("x_axis_column", kolumny[0])) if table.get("x_axis_column") in kolumny else 0, key=f"x_{idx}")
                def_y = [y for y in table.get("y_axis_columns", []) if y in kolumny]
                t_y = st.multiselect(f"Oś Y (Wartości liczbowe)", kolumny, default=def_y, key=f"y_{idx}")
                
                k_up, k_dw, k_del = st.columns(3)
                if k_up.button("⬆️ Wyżej", key=f"u_{idx}") and idx > 0:
                    st.session_state.builder_data.insert(idx-1, st.session_state.builder_data.pop(idx)); st.rerun()
                if k_dw.button("⬇️ Niżej", key=f"d_{idx}") and idx < len(st.session_state.builder_data)-1:
                    st.session_state.builder_data.insert(idx+1, st.session_state.builder_data.pop(idx)); st.rerun()
                if k_del.button("❌ Usuń sekcję", type="primary", key=f"del_{idx}"):
                    st.session_state.builder_data.pop(idx); st.rerun()
                    
            with c2:
                if split_sel != "Brak" and split_sel in df.columns:
                    st.caption(f"Podgląd (Pokazuję tylko pierwszy element z podziału: {unique_vals[0]})")
                    df_preview = df[df[split_sel] == unique_vals[0]]
                else:
                    df_preview = df

                st.dataframe(df_preview, use_container_width=True)
                
                st.session_state.builder_data[idx]['recommended_chart'] = t_chart
                st.session_state.builder_data[idx]['x_axis_column'] = t_x
                st.session_state.builder_data[idx]['y_axis_columns'] = t_y
                
                if t_chart != "none" and t_x and t_y:
                    try:
                        df_plot = df_preview.melt(id_vars=[t_x], value_vars=t_y, var_name='Legenda', value_name='Wartość')
                        if t_chart == "line": c = alt.Chart(df_plot).mark_line(point=True).encode(x=alt.X(t_x, sort=None), y='Wartość', color='Legenda')
                        elif t_chart == "bar": c = alt.Chart(df_plot).mark_bar().encode(x=alt.X(t_x, sort='-y'), y='Wartość', color='Legenda')
                        elif t_chart == "scatter": c = alt.Chart(df_plot).mark_circle(size=60).encode(x=alt.X(t_x, sort=None), y='Wartość', color='Legenda')
                        elif t_chart == "area": c = alt.Chart(df_plot).mark_area(opacity=0.5).encode(x=alt.X(t_x, sort=None), y='Wartość', color='Legenda')
                        elif t_chart == "pie": c = alt.Chart(df_preview).mark_arc().encode(color=t_x, theta=t_y[0], tooltip=[t_x, t_y[0]])
                        st.altair_chart(c.interactive(), use_container_width=True)
                    except: st.warning("Błąd podglądu wykresu. Upewnij się, że przypisane osie Y zawierają wyłącznie liczby.")
            st.markdown("---")
            
        if st.button("💾 ZAPISZ TĘ ZAKŁADKĘ DO APLIKACJI (KOD)", type="primary", use_container_width=True):
            safe_name_base = re.sub(r'\W+', '_', tab_name).strip('_')
            existing_file = st.session_state.get('edit_file_target')
            
            if existing_file:
                py_file = existing_file
            else:
                uid = str(uuid.uuid4().hex)[:4]
                safe_name = f"{safe_name_base}_{uid}"
                files = glob.glob("pages/*.py")
                max_num = 0
                for f in files:
                    m = re.search(r'\\(\d+)_', f) or re.search(r'/(\d+)_', f)
                    if m: max_num = max(max_num, int(m.group(1)))
                next_num = str(max_num + 1).zfill(2)
                py_file = f"pages/{next_num}_{safe_name}.py"
            
            meta_data = {
                "tab_name": tab_name, 
                "report_title": report_title,
                "tab_desc": tab_desc, 
                "link": st.session_state.builder_link, 
                "selected_sheets": st.session_state.get("builder_selected_sheets", []),
                "extraction_instruction": st.session_state.get('extraction_instruction', ''),
                "tables": st.session_state.builder_data
            }
            
            meta_json_str = json.dumps(meta_data, ensure_ascii=False)
            
            kod = f'''import streamlit as st, pandas as pd, numpy as np, altair as alt, json, os, re
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
    def move_file(index, direction, files_list):
        if direction == "up" and index > 0:
            files_list[index], files_list[index-1] = files_list[index-1], files_list[index]
        elif direction == "down" and index < len(files_list) - 1:
            files_list[index], files_list[index+1] = files_list[index+1], files_list[index]
            
        temp_files = []
        for i, f_path in enumerate(files_list):
            dir_name = os.path.dirname(f_path)
            base_name = os.path.basename(f_path)
            name_no_prefix = re.sub(r'^\d+_', '', base_name)
            temp_path = os.path.join(dir_name, f"temp_{i}_{name_no_prefix}")
            os.rename(f_path, temp_path)
            temp_files.append((temp_path, name_no_prefix))
            
        for i, (temp_path, name_no_prefix) in enumerate(temp_files):
            new_prefix = str(i + 1).zfill(2)
            final_path = os.path.join(os.path.dirname(temp_path), f"{new_prefix}_{name_no_prefix}")
            os.rename(temp_path, final_path)
            
        st.rerun()

    col_akt, col_arch = st.columns(2)
    with col_akt:
        st.subheader("🟢 Kolejność w Menu (Aktywne)")
        st.caption("Użyj strzałek aby zmienić kolejność zakładek w lewym pasku nawigacji.")
        pliki = sorted([f for f in glob.glob("pages/*.py") if "00_AI_Panel" not in f])
        for i, p in enumerate(pliki):
            nazwa = os.path.basename(p)
            c1, c2, c3, c4 = st.columns([5, 1, 1, 2])
            c1.write(f"📄 **{nazwa}**")
            if c2.button("⬆️", key=f"up_{nazwa}", disabled=(i == 0)): move_file(i, "up", pliki)
            if c3.button("⬇️", key=f"dw_{nazwa}", disabled=(i == len(pliki)-1)): move_file(i, "down", pliki)
            if c4.button("📦 Archiwizuj", key=f"arch_{nazwa}"):
                shutil.move(p, f"archive/{nazwa}")
                st.rerun()

    with col_arch:
        st.subheader("📦 Zarchiwizowane (Ukryte)")
        zarch = sorted(glob.glob("archive/*.py"))
        for p in zarch:
            nazwa = os.path.basename(p)
            c1, c2, c3 = st.columns([3, 1, 1])
            c1.write(f"📁 {nazwa}")
            if c2.button("♻️ Przywróć", key=f"rest_{nazwa}"):
                shutil.move(p, f"pages/{nazwa}")
                st.rerun()
            if c3.button("❌ Usuń trwale", key=f"del_{nazwa}"):
                os.remove(p)
                st.rerun()

# --- ZMIANA: ZAKŁADKA TYLKO I WYŁĄCZNIE DLA GŁÓWNYCH PROMPTÓW ---
with tab_prompty:
    st.subheader("⚙️ Główne Instrukcje Systemowe (Mózg AI)")
    st.info("Tutaj znajdują się instrukcje wysyłane do API Google 'pod spodem'. Możesz je edytować, jeśli chcesz zmienić zachowanie modelu. Pamiętaj, aby zostawić tagi `{custom_instruction}` i `{csv_content}` - to w ich miejsce wklejane są pliki!")
    
    def move_file_generic(src, dst):
        shutil.move(src, dst)
        st.rerun()
        
    for p in glob.glob("prompts/active/00_SYSTEM_*.txt"):
        name = os.path.basename(p)
        with st.expander(f"📄 Edytuj: {name}"):
            with open(p, "r", encoding="utf-8") as f: content = f.read()
            new_content = st.text_area("Treść Promptu Systemowego:", value=content, height=250, key=f"sys_{name}")
            
            c1, c2 = st.columns([1, 1])
            if c1.button("💾 Zapisz Zmiany", key=f"s_{name}", type="primary"):
                with open(p, "w", encoding="utf-8") as f: f.write(new_content)
                st.success("Zapisano pomyślnie!")
            if c2.button("♻️ Zarchiwizuj i Resetuj do Fabrycznych", key=f"a_{name}", help="To przeniesie Twoją modyfikację do archiwum na dole, a w to miejsce wygeneruje bezpieczny, oryginalny prompt."):
                move_file_generic(p, f"prompts/archive/{name}_{uuid.uuid4().hex[:4]}.txt")
                
    st.divider()
    st.subheader("📦 Archiwum (Kopie zapasowe Promptów)")
    
    zarch_prompty = glob.glob("prompts/archive/*.txt")
    if not zarch_prompty:
        st.caption("Brak zarchiwizowanych promptów.")
    else:
        for p in zarch_prompty:
            name = os.path.basename(p)
            c1, c2, c3 = st.columns([3, 1, 1])
            c1.write(f"📁 {name}")
            if c2.button("♻️ Przywróć", key=f"ur_{name}"):
                # Oczyszczanie nazwy z kodu archiwizacji
                restore_name = re.sub(r'_[a-f0-9]{4}\.txt$', '.txt', name)
                # Zanim przywrócimy, warto usunąć ten aktywny, żeby go zastąpić
                active_path = f"prompts/active/{restore_name}"
                if os.path.exists(active_path): os.remove(active_path)
                move_file_generic(p, active_path)
            if c3.button("❌ Usuń trwale", key=f"ux_{name}"):
                os.remove(p)
                st.rerun()