import streamlit as st
import pandas as pd
import numpy as np
import requests
import io
import xml.etree.ElementTree as ET
import altair as alt
import re
import json
import os
import glob

try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

MONTH_ORDER = ['Styczeń', 'Luty', 'Marzec', 'Kwiecień', 'Maj', 'Czerwiec', 'Lipiec', 'Sierpień', 'Wrzesień', 'Październik', 'Listopad', 'Grudzień']

def ensure_system_prompts():
    os.makedirs("prompts/active", exist_ok=True)
    os.makedirs("prompts/archive", exist_ok=True)
    
    p_analiza = "prompts/active/00_SYSTEM_Analiza_v3.txt"
    if not os.path.exists(p_analiza):
        with open(p_analiza, "w", encoding="utf-8") as f:
            f.write('Zanalizuj PRÓBKĘ danych CSV (tylko 15 wierszy) i wygeneruj strukturę raportu. {custom_instruction}\nOczekiwany format: {"report_title": "Główny tytuł", "tables": [ {"dataset_name": "Nazwa", "recommended_chart": "line", "x_axis_column": "KolX", "y_axis_columns": ["KolY"], "column_mapping": {"0": "KolX", "1": "KolY", "2": "InnaKolumna"}, "data": [] } ]}. Typy wykresów: line, bar, pie, scatter, area, none.\nUWAGA KRYTYCZNA 1: Pole "data" MUSI być PUSTĄ TABLICĄ []. System samodzielnie zaciągnie w to miejsce pełne dane. Nie trać tokenów na przepisywanie wierszy!\nUWAGA KRYTYCZNA 2: Musisz podać "column_mapping", w którym zamienisz surowe indeksy kolumn z CSV (np. "0", "1") na czytelne nazwy zgodne z danymi, które staną się osiami wykresu.\nDANE:\n{csv_content}')
            
    p_rebuild = "prompts/active/00_SYSTEM_Odswiezanie_v3.txt"
    if not os.path.exists(p_rebuild):
        with open(p_rebuild, "w", encoding="utf-8") as f:
            f.write('SZABLON JSON:\n{template_json}\n\nNOWA PRÓBKA CSV:\n{csv_content}\n\nZaktualizuj SZABLON JSON na podstawie struktury nowych danych. {custom_instruction}\nZASADA 1: Pole "data" MUSI pozostać całkowicie PUSTE ([]). My wstrzykniemy pełne dane w tle.\nZASADA 2: Zachowaj istniejące "column_mapping" z szablonu, chyba że nowe dane mają ewidentnie inną strukturę i wymagają nowych nazw. Zwróć nienaganny JSON.')

def setup_session_state():
    ensure_system_prompts()
    if 'data_loaded' not in st.session_state:
        st.session_state.data_loaded = False
        domyslny_klucz = ""
        if os.path.exists("api_key.txt"):
            try:
                with open("api_key.txt", "r", encoding="utf-8") as f:
                    domyslny_klucz = f.read().strip()
            except Exception: pass
        
        st.session_state.gemini_key = domyslny_klucz
        st.session_state.model_name = "gemini-2.5-flash"
        st.session_state.length_mode = "Standardowy"
        st.session_state.custom_prompt = ""
        st.session_state.rok = 2025
        st.session_state.miesiac = "Grudzień"
        st.session_state.nbp_df = None
        st.session_state.nbp_date = None
        st.session_state.fetch_limit = 300
    if 'descriptions' not in st.session_state:
        st.session_state.descriptions = {k: '' for k in ['nbp', 'bik']}

def load_css():
    st.markdown("""
        <style>
            .block-container {padding-top: 2rem; padding-bottom: 5rem;}
            .gus-table { width: 100%; border-collapse: collapse; font-family: 'Segoe UI', Arial, sans-serif; font-size: 13px; margin-bottom: 20px; color: #333; background-color: #ffffff; }
            .gus-table th { background-color: #e6e6e6; border: 1px solid #a0a0a0; padding: 8px; text-align: center; font-weight: bold; }
            .gus-table td { border: 1px solid #d0d0d0; padding: 8px; text-align: center; }
            .gus-table td:first-child { text-align: left; font-weight: 600; min-width: 180px; }
        </style>
    """, unsafe_allow_html=True)

def clean_url(raw_url):
    if not raw_url: return ""
    match = re.search(r'(https?://[^\s\'"<>]+)', str(raw_url))
    return match.group(1) if match else str(raw_url).strip()

def render_page_header(title, is_dynamic=False, meta=None, file_path=None):
    col1, col2 = st.columns([3, 1])
    with col1:
        st.header(title)
    with col2:
        safe_title = re.sub(r'\W+', '_', title)
        uid = ""
        if file_path:
            uid = re.sub(r'^\d+_', '', os.path.basename(file_path)).replace('.py', '')
            
        btn_key = f"btn_edit_{safe_title}_{uid}"
        
        if st.button("⚙️ Edytuj układ zakładki", key=btn_key, use_container_width=True):
            if is_dynamic and meta and file_path:
                st.session_state.builder_link = meta.get("link", "")
                st.session_state.builder_data = meta.get("tables", [])
                st.session_state.builder_step = 3
                st.session_state.edit_tab_name = meta.get("tab_name", "")
                st.session_state.edit_report_title = meta.get("report_title", meta.get("tab_name", ""))
                st.session_state.extraction_instruction = meta.get("extraction_instruction", "")
                st.session_state.fetch_limit = meta.get("fetch_limit", 300)
                st.session_state.edit_tab_desc = meta.get("tab_desc", "")
                st.session_state.edit_file_target = file_path
                st.switch_page("pages/00_AI_Panel.py")

def render_dynamic_section(meta, file_path, is_in_app=False):
    tab_name = meta.get("tab_name", "Raport")
    report_title = meta.get("report_title", tab_name)
    
    slug = re.sub(r'^\d+_', '', os.path.basename(file_path)).replace('.py', '')
    tables_to_render = st.session_state.get(f"dynamic_data_{slug}", meta.get("tables", []))
    
    render_page_header(report_title, is_dynamic=True, meta=meta, file_path=file_path)
        
    for idx, table in enumerate(tables_to_render):
        df_base = pd.DataFrame(table.get("data", []))
        if df_base.empty: continue

        applied_commands = table.get("applied_commands", [])
        if not applied_commands and table.get("pandas_code"):
            applied_commands = [c.strip() for c in table.get("pandas_code").split('\n') if c.strip()]

        df_mod = df_base.copy()
        for cmd in applied_commands:
            try:
                local_vars = {"df": df_mod, "pd": pd, "np": np}
                exec(cmd, globals(), local_vars)
                df_mod = local_vars["df"]
            except Exception: pass
        df = df_mod

        split_col = table.get("split_by_column", "")
        if split_col and split_col in df.columns:
            unique_vals = sorted(df[split_col].dropna().unique())
            df_list = [(f"{table.get('dataset_name', '')} - {val}", df[df[split_col] == val]) for val in unique_vals]
        else:
            df_list = [(table.get('dataset_name', f'Tabela {idx+1}'), df)]

        for sub_title, sub_df in df_list:
            if sub_df.empty: continue
            st.markdown(f"#### {sub_title}")
            t_chart = table.get("recommended_chart", "none")
            t_x = table.get("x_axis_column")
            t_y = table.get("y_axis_columns", [])
            
            if t_chart != "none" and t_x and t_y and t_x in sub_df.columns and all(y in sub_df.columns for y in t_y):
                try:
                    df_plot = sub_df.melt(id_vars=[t_x], value_vars=t_y, var_name='Legenda', value_name='Wartość')
                    c = alt.Chart(df_plot)
                    if t_chart == "line": c = c.mark_line(point=True).encode(x=alt.X(t_x, sort=None), y='Wartość', color='Legenda')
                    elif t_chart == "bar": c = c.mark_bar().encode(x=alt.X(t_x, sort='-y'), y='Wartość', color='Legenda')
                    elif t_chart == "scatter": c = c.mark_circle(size=60).encode(x=alt.X(t_x, sort=None), y='Wartość', color='Legenda')
                    elif t_chart == "area": c = c.mark_area(opacity=0.5).encode(x=alt.X(t_x, sort=None), y='Wartość', color='Legenda')
                    elif t_chart == "pie": c = alt.Chart(sub_df).mark_arc().encode(color=t_x, theta=t_y[0], tooltip=[t_x, t_y[0]])
                    st.altair_chart(c.interactive(), use_container_width=True)
                except Exception: pass
            
            st.markdown(sub_df.to_html(classes='gus-table', index=False, border=0), unsafe_allow_html=True)
            
        display_ai_section(f"{slug}_{idx}", df.to_string())

def clean_ai_json_output(text):
    text = text.strip()
    text = re.sub(r'^```(?:json)?[a-zA-Z]*\n', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\n```$', '', text).strip()
    start_idx = text.find('{')
    if start_idx == -1: start_idx = text.find('[')
    
    end_idx = text.rfind('}')
    if end_idx == -1 or text.rfind(']') > end_idx: end_idx = text.rfind(']')
        
    if start_idx != -1 and end_idx != -1: 
        text = text[start_idx:end_idx+1]
        
    text = re.sub(r',\s*([\]}])', r'\1', text)
    text = re.sub(r'\}\s*\{', r'}, {', text)
    return text

def parse_and_repair_json(json_str):
    try:
        return json.loads(json_str)
    except Exception as e:
        try:
            fixed_str = re.sub(r',\s*$', '', json_str) 
            return json.loads(fixed_str + "]}]}")
        except:
            raise ValueError(f"AI zwróciło totalnie uszkodzony JSON. Spróbuj ponownie. Błąd: {str(e)}")

def ai_analyze_custom_sheets(csv_content, api_key, model_name, custom_instruction="", raw_dfs=None):
    genai.configure(api_key=api_key)
    instr_text = f"DODATKOWA INSTRUKCJA UŻYTKOWNIKA DO EKSTRAKCJI: {custom_instruction}\n\n" if custom_instruction else ""
    
    try:
        with open("prompts/active/00_SYSTEM_Analiza_v3.txt", "r", encoding="utf-8") as f:
            prompt_template = f.read()
    except Exception:
        prompt_template = 'Zanalizuj próbkę CSV do JSON. {custom_instruction}\nOczekiwany format: {"report_title": "Tytuł", "tables": [ {"dataset_name": "Nazwa", "recommended_chart": "line", "x_axis_column": "X", "y_axis_columns": ["Y"], "column_mapping": {"0": "X", "1": "Y"}, "data": [] } ]}. DANE:\n{csv_content}'
        
    prompt = prompt_template.replace("{custom_instruction}", instr_text).replace("{csv_content}", csv_content)
    
    response = genai.GenerativeModel(model_name).generate_content(prompt, generation_config={"response_mime_type": "application/json", "max_output_tokens": 8192})
    cleaned_text = clean_ai_json_output(response.text)
    parsed = parse_and_repair_json(cleaned_text)
    
    if raw_dfs and isinstance(parsed, dict) and "tables" in parsed:
        for idx, table in enumerate(parsed["tables"]):
            sheet_name = list(raw_dfs.keys())[idx] if idx < len(raw_dfs) else list(raw_dfs.keys())[0]
            df = raw_dfs[sheet_name].copy()
            
            mapping = table.get("column_mapping", {})
            if mapping:
                mapping_clean = {int(k) if str(k).isdigit() else k: str(v) for k, v in mapping.items()}
                df.rename(columns=mapping_clean, inplace=True)
                
            table["data"] = df.to_dict(orient="records")
            
    return parsed

def ai_rebuild_from_template(csv_content, template_json, api_key, model_name, custom_instruction="", raw_dfs=None):
    genai.configure(api_key=api_key)
    for t in template_json: 
        t.pop("pandas_code", None)
        t.pop("applied_commands", None)
        t["data"] = []
        
    instr_text = f"DODATKOWA INSTRUKCJA UŻYTKOWNIKA (MUSISZ JEJ PRZESTRZEGAĆ!): {custom_instruction}\n\n" if custom_instruction else ""
    
    try:
        with open("prompts/active/00_SYSTEM_Odswiezanie_v3.txt", "r", encoding="utf-8") as f:
            prompt_template = f.read()
    except Exception:
        prompt_template = 'SZABLON JSON:\n{template_json}\n\nNOWA PRÓBKA CSV:\n{csv_content}\n\nZaktualizuj układ SZABLONU JSON. {custom_instruction}\nZwróć idealny JSON.'
        
    prompt = prompt_template.replace("{template_json}", json.dumps(template_json, ensure_ascii=False)).replace("{csv_content}", csv_content).replace("{custom_instruction}", instr_text)
    
    response = genai.GenerativeModel(model_name).generate_content(prompt, generation_config={"response_mime_type": "application/json", "max_output_tokens": 8192})
    cleaned_text = clean_ai_json_output(response.text)
    parsed = parse_and_repair_json(cleaned_text)
    new_tables = parsed["tables"] if isinstance(parsed, dict) and "tables" in parsed else parsed
    
    if raw_dfs and isinstance(new_tables, list):
        for idx, table in enumerate(new_tables):
            sheet_name = list(raw_dfs.keys())[idx] if idx < len(raw_dfs) else list(raw_dfs.keys())[0]
            df = raw_dfs[sheet_name].copy()
            
            mapping = table.get("column_mapping", {})
            if not mapping and idx < len(template_json):
                mapping = template_json[idx].get("column_mapping", {})
                
            if mapping:
                mapping_clean = {int(k) if str(k).isdigit() else k: str(v) for k, v in mapping.items()}
                df.rename(columns=mapping_clean, inplace=True)
                
            table["data"] = df.to_dict(orient="records")
            
    return new_tables

def generate_ai_description(key, data_context, api_key, model_name, length_mode, custom_prompt=""):
    if not HAS_GENAI or not api_key: return
    try:
        genai.configure(api_key=api_key)
        length_inst = custom_prompt if length_mode == "Własna instrukcja (Custom)" else "Napisz komentarz analityczny."
        response = genai.GenerativeModel(model_name).generate_content(f"Jesteś ekspertem. {length_inst}\nDANE:\n{data_context}")
        st.session_state.descriptions[key] = response.text
    except Exception: pass

def display_ai_section(key, data_context):
    st.subheader("🤖 Komentarz AI do sekcji")
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button(f"Generuj opis", key=f"btn_desc_{key}"):
            with st.spinner("Generowanie..."):
                generate_ai_description(key, str(data_context)[:10000], st.session_state.gemini_key, st.session_state.model_name, st.session_state.length_mode, st.session_state.custom_prompt)
            st.rerun()
    st.session_state.descriptions[key] = st.text_area("Edytuj opis:", value=st.session_state.descriptions.get(key, ''), height=100, key=f"txt_{key}")

def render_bik_section(title, url):
    clean_url_b = f"{clean_url(url)}?:showVizHome=no&:embed=true&:toolbar=no&:size=1200,1100"
    st.markdown(f'<div style="margin-bottom: 40px;"><h4 style="margin: 0 0 10px 0;">{title}</h4><iframe src="{clean_url_b}" width="100%" height="1150" style="border:none; overflow:hidden;" scrolling="no"></iframe></div>', unsafe_allow_html=True)

def render_sidebar():
    with st.sidebar:
        st.header("⚙️ Konfiguracja")
        st.session_state.gemini_key = st.text_input("Klucz API Gemini (Wymagany do AI)", value=st.session_state.get('gemini_key', ''), type="password")
        st.session_state.model_name = st.selectbox("Wybierz Model AI", [
            "gemini-2.5-flash", "gemini-3.1-pro-preview", "gemini-3-pro-preview", "gemini-3-flash-preview", "gemini-2.5-pro", "gemini-2.0-flash", "gemini-1.5-pro"
        ])
        st.session_state.rok = st.number_input("Rok raportu", value=st.session_state.get('rok', 2025))
        st.session_state.miesiac = st.selectbox("Miesiąc raportu", MONTH_ORDER, index=MONTH_ORDER.index(st.session_state.get('miesiac', 'Grudzień')))
        
        st.markdown("---")
        st.info("Twoje Dynamiczne Moduły (Linki):")
        
        dodatkowe = [f for f in glob.glob("pages/*.py") if re.search(r'\d{2}_', f) and "00_AI_Panel" not in f and "NBP" not in f and "Rynek_Kredytowy" not in f]
        lista_plikow_ai = []
        for plik in sorted(dodatkowe):
            try:
                with open(plik, "r", encoding="utf-8") as file: content = file.read()
                meta_match = re.search(r'# === META START ===\nMETA_JSON = r"""(.*?)"""\n# === META END ===', content, re.DOTALL)
                if meta_match:
                    meta = json.loads(meta_match.group(1))
                    slug = re.sub(r'^\d+_', '', os.path.basename(plik)).replace('.py', '')
                    if meta.get("tab_desc"): st.caption(f"📍 {meta.get('tab_desc')}")
                    st.session_state[f"link_{slug}"] = st.text_input(f"{meta.get('tab_name')}", value=st.session_state.get(f"link_{slug}", meta.get("link", "")))
                    lista_plikow_ai.append({"slug": slug, "meta": meta, "link": st.session_state[f"link_{slug}"]})
            except: pass

        st.markdown("---")
        if st.button("🚀 POBIERZ GŁÓWNE DANE DO RAPORTU", type="primary"):
            if not st.session_state.gemini_key: 
                st.error("❗ Wpisz Klucz API Gemini (AI)!")
                return
            try:
                r = requests.get("https://static.nbp.pl/dane/stopy/stopy_procentowe_archiwum.xml", headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
                root = ET.fromstring(r.content)
                najnowsza = root.findall('pozycje')[-1]
                st.session_state.nbp_date = najnowsza.get('obowiazuje_od')
                mapa_nazw = {'ref': 'Stopa referencyjna', 'lom': 'Stopa lombardowa', 'dep': 'Stopa depozytowa'}
                st.session_state.nbp_df = pd.DataFrame([{"Rodzaj Stopy": mapa_nazw[c.get('id')], "Wartość (%)": f"{float(c.get('oprocentowanie').replace(',', '.')):.2f}".replace('.', ',')} for c in najnowsza if c.get('id') in mapa_nazw])
            except: pass
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for idx, item in enumerate(lista_plikow_ai):
                status_text.text(f"Zaciąganie i analiza przez AI: {item['meta'].get('tab_name')}...")
                progress_bar.progress((idx) / len(lista_plikow_ai))
                dyn_link = item['link']
                if dyn_link and str(dyn_link).strip() != "":
                    try:
                        resp = requests.get(clean_url(dyn_link), headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
                        if resp.status_code == 200:
                            excel = pd.ExcelFile(io.BytesIO(resp.content))
                            sheets_to_use = item['meta'].get("selected_sheets", excel.sheet_names)
                            f_limit = item['meta'].get("fetch_limit", st.session_state.get('fetch_limit', 300))
                            
                            raw_dfs = {}
                            csv_text = ""
                            for s in sheets_to_use:
                                if s in excel.sheet_names:
                                    df_raw = pd.read_excel(excel, sheet_name=s, header=None).dropna(how='all', axis=0).dropna(how='all', axis=1).head(f_limit)
                                    raw_dfs[s] = df_raw
                                    csv_text += f"\n--- ZAKŁADKA: {s} ---\n{df_raw.head(15).to_csv(index=False)}"
                            
                            new_tables = ai_rebuild_from_template(csv_text, item['meta'].get("tables", []), st.session_state.gemini_key, st.session_state.model_name, item['meta'].get("extraction_instruction", ""), raw_dfs)
                            if new_tables:
                                for n_tab, old_tab in zip(new_tables, item['meta'].get("tables", [])):
                                    if "applied_commands" in old_tab: n_tab["applied_commands"] = old_tab["applied_commands"]
                                    elif "pandas_code" in old_tab: n_tab["pandas_code"] = old_tab["pandas_code"]
                                    if "split_by_column" in old_tab: n_tab["split_by_column"] = old_tab["split_by_column"]
                                st.session_state[f"dynamic_data_{item['slug']}"] = new_tables
                    except Exception as e:
                        st.error(f"Błąd analizy AI dla {item['meta'].get('tab_name')}: {e}")
            
            progress_bar.progress(1.0)
            status_text.text("Sukces! Wszystkie moduły zaktualizowane.")
            st.session_state.data_loaded = True