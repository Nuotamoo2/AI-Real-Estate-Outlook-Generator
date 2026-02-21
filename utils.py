import streamlit as st
import pandas as pd
import requests
import io
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import altair as alt
import base64
import re
import json

try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

MONTH_ORDER = ['Styczeń', 'Luty', 'Marzec', 'Kwiecień', 'Maj', 'Czerwiec', 'Lipiec', 'Sierpień', 'Wrzesień', 'Październik', 'Listopad', 'Grudzień']
MONTH_MAP = {i: m for i, m in enumerate(MONTH_ORDER, 1)}
MONTH_NAMES_LOWER = {m.lower(): i for i, m in enumerate(MONTH_ORDER, 1)}

# ==========================================
# KONFIGURACJA I CSS
# ==========================================
def setup_session_state():
    if 'data_loaded' not in st.session_state:
        st.session_state.data_loaded = False
        st.session_state.gemini_key = ""
        st.session_state.model_name = "gemini-2.5-flash"
        st.session_state.length_mode = "Standardowy"
        st.session_state.rok = 2025
        st.session_state.miesiac = "Grudzień"
        for k in ['nbp_df', 'nbp_date', 'gus_praca', 'gus_budowa', 'inflacja', 'ceny_bud', 'gus_kwartalne', 'universal_data']: 
            st.session_state[k] = None
    if 'descriptions' not in st.session_state:
        st.session_state.descriptions = {k: '' for k in ['nbp', 'inflacja', 'praca', 'budownictwo', 'kwartalne', 'koszty', 'bik', 'universal']}

def load_css():
    st.markdown("""
        <style>
            .block-container {padding-top: 2rem; padding-bottom: 5rem;}
            h1, h2, h3 {font-family: 'Arial', sans-serif;}
            h4 {color: #555; margin-top: 25px; margin-bottom: 10px; border-bottom: 1px solid #eee;}
            .gus-table { width: 100%; border-collapse: collapse; font-family: 'Segoe UI', Arial, sans-serif; font-size: 13px; margin-bottom: 20px; color: #333; background-color: #ffffff; }
            .gus-table th { background-color: #e6e6e6; border: 1px solid #a0a0a0; padding: 8px; text-align: center; font-weight: bold; vertical-align: middle; }
            .gus-table td { border: 1px solid #d0d0d0; padding: 8px; text-align: center; vertical-align: middle; background-color: #ffffff; }
            .gus-table td:first-child { text-align: left; font-weight: 600; min-width: 180px; }
            .footer { position: fixed; left: 0; bottom: 0; width: 100%; background-color: #f1f1f1; color: #555; text-align: center; padding: 10px; font-size: 12px; border-top: 1px solid #ccc; z-index: 999; }
            .ai-comment { background-color: #f0f8ff; border-left: 5px solid #0078ff; padding: 15px; margin: 15px 0; font-style: italic; color: #333; page-break-inside: avoid; }
            .trend-up { color: #27ae60; font-weight: bold; }
            .trend-down { color: #c0392b; font-weight: bold; }
            .trend-neutral { color: #7f8c8d; }
            .kpi-container { display: flex; gap: 15px; margin-bottom: 30px; flex-wrap: wrap; }
            .kpi-box { background: #f8f9fa; padding: 15px; border-radius: 8px; min-width: 120px; border: 1px solid #ddd; text-align: center; flex: 1; }
            .kpi-val { font-size: 18px; font-weight: bold; color: #2c3e50; }
        </style>
    """, unsafe_allow_html=True)

# ==========================================
# FUNKCJE POMOCNICZE
# ==========================================
def clean_url(raw_url):
    if not raw_url: return ""
    match = re.search(r'(https?://[^\s\'"<>]+)', str(raw_url))
    return match.group(1) if match else str(raw_url).strip()

def format_month_name(val):
    s = str(val).strip()
    try:
        f = float(s.replace(',', '.'))
        m_int = int(f)
        if 1 <= m_int <= 12: return MONTH_MAP[m_int]
    except: pass
    s_lower = s.lower()
    for name, num in MONTH_NAMES_LOWER.items():
        if name in s_lower: return MONTH_MAP[num]
    return s

def clean_number_formatting(val):
    if pd.isna(val) or val == "": return ""
    try:
        if isinstance(val, (int, float)):
            if isinstance(val, float) and val.is_integer(): val = int(val)
            parts = str(val).split('.')
            int_part = "{:,}".format(int(parts[0])).replace(',', ' ')
            if len(parts) > 1: return f"{int_part},{parts[1]}"
            return int_part
    except: pass
    return str(val)

def format_with_indicator(val, inverse=False):
    if pd.isna(val) or val == "": return "-"
    try:
        v = float(val)
        parts = str(v).split('.')
        int_part = "{:,}".format(int(parts[0])).replace(',', ' ')
        formatted_v = f"{int_part},{parts[1]}" if len(parts) > 1 else int_part
        if v > 0: return f'<span class="{"trend-down" if inverse else "trend-up"}">▲ {formatted_v}</span>'
        elif v < 0: return f'<span class="{"trend-up" if inverse else "trend-down"}">▼ {formatted_v}</span>'
        else: return f'<span class="trend-neutral">● {formatted_v}</span>'
    except: return str(val)

def parse_float_safe(val):
    if pd.isna(val) or val is None: return None
    if isinstance(val, (int, float)): return float(val)
    val_str = str(val).replace('\xa0', '').replace(' ', '').replace(',', '.')
    val_str = re.sub(r'[^\d.-]', '', val_str)
    try: return float(val_str)
    except: return None

def get_month_number(val):
    s = str(val).strip()
    match = re.match(r'^(\d+)', s)
    if match: return int(match.group(1))
    for name, num in MONTH_NAMES_LOWER.items():
        if name in s.lower(): return num
    return 0

def prepare_data_for_chart_aggregate(df, value_col_name):
    chart_df = df.copy()
    if 'Rok' not in chart_df.columns or 'Miesiąc' not in chart_df.columns: return chart_df
    def make_date(row):
        try:
            y = int(float(str(row['Rok']).replace(',', '.')))
            m = get_month_number(row['Miesiąc'])
            if m > 0: return datetime(y, m, 1)
        except: pass
        return None
    chart_df['Date'] = chart_df.apply(make_date, axis=1)
    chart_df = chart_df.dropna(subset=['Date']).sort_values('Date')
    chart_df['Okres'] = chart_df['Date'].apply(lambda x: x.strftime('%Y-%m'))
    chart_df = chart_df.set_index('Okres').drop(columns=[c for c in ['Rok', 'Miesiąc', 'Date'] if c in chart_df.columns])
    for col in chart_df.columns: chart_df[col] = chart_df[col].apply(parse_float_safe)
    if value_col_name is None: return chart_df.select_dtypes(include=['number']).dropna(how='all')
    if value_col_name and value_col_name in chart_df.columns: return chart_df.select_dtypes(include=['number']).dropna(how='all')
    elif len(chart_df.columns) > 0: return chart_df.iloc[:, 0:1].dropna()
    return chart_df

def prepare_yearly_comparison_data(full_data, year, val_col, dyn_col):
    if full_data is None or full_data.empty: return pd.DataFrame()
    df_current = full_data[full_data['Rok'] == str(year)].copy()
    if df_current.empty: return pd.DataFrame()
    prev_values = []
    for _, row in df_current.iterrows():
        prev_val = None
        curr_val = parse_float_safe(row[val_col])
        prev_year = str(int(year) - 1)
        month = row['Miesiąc']
        hist_row = full_data[(full_data['Rok'] == prev_year) & (full_data['Miesiąc'] == month)]
        if not hist_row.empty:
            val = parse_float_safe(hist_row.iloc[0][val_col])
            if val is not None: prev_val = val 
        if prev_val is None:
            dyn_val = parse_float_safe(row.get(dyn_col))
            if curr_val is not None and dyn_val:
                try: prev_val = round(curr_val / (dyn_val / 100.0), 1)
                except: pass
        prev_values.append(prev_val)
    df_current['Analogiczny okres roku poprzedniego'] = prev_values
    df_current['sort_idx'] = df_current['Miesiąc'].apply(get_month_number)
    return df_current.sort_values('sort_idx').set_index('Miesiąc')[[val_col, 'Analogiczny okres roku poprzedniego']]

def process_gus_header(df, header_row_idx):
    row1 = df.iloc[header_row_idx].astype(str).replace('nan', '').tolist()
    row2 = df.iloc[header_row_idx + 1].astype(str).replace('nan', '').tolist()
    clean_row1, last_val = [], ""
    for val in row1:
        if val.strip(): last_val = val
        clean_row1.append(last_val)
    tuples = []
    for r1, r2 in zip(clean_row1, row2):
        if r1 == "WYSZCZEGÓLNIENIE": tuples.append((r1, ""))
        elif r2: tuples.append((r1, r2))
        else: tuples.append((r1, ""))
    return pd.MultiIndex.from_tuples(tuples)

def process_chart_table(df):
    header_idx, title, value_col_name, dyn_col_name = None, "", "Wartość", "Dynamika (r/r)"
    if len(df) > 0 and "Wykres" in str(df.iloc[0, 0]): title = str(df.iloc[0, 0])
    for idx, row in df.iterrows():
        if "WYSZCZEGÓLNIENIE" in str(row.values[0]):
            header_idx = idx
            if len(row) > 2 and pd.notna(row.values[2]) and str(row.values[2]).strip() != 'nan': value_col_name = str(row.values[2]).strip().replace('\n', ' ')
            if len(row) > 3 and pd.notna(row.values[3]) and str(row.values[3]).strip() != 'nan': dyn_col_name = str(row.values[3]).strip().replace('\n', ' ')
            break
    if header_idx is None: return None, None, None, None, None
    data = df.iloc[header_idx+1:].dropna(axis=1, how='all')
    new_cols = ['Rok', 'Miesiąc', value_col_name]
    if len(data.columns) >= 4:
        new_cols.append(dyn_col_name)
        data = data.iloc[:, :4]
    else: data = data.iloc[:, :3]
    data.columns = new_cols
    data['Rok'] = data['Rok'].ffill()
    data = data[data['Rok'].apply(lambda x: 2000 < float(str(x).replace(',', '.')) < 2100 if parse_float_safe(x) else False)]
    data['Rok'] = data['Rok'].apply(lambda x: str(int(float(str(x).replace(',', '.')))))
    data['Miesiąc'] = data['Miesiąc'].apply(format_month_name)
    years_dict = {}
    for year in data['Rok'].unique():
        df_year = data[data['Rok'] == year].drop(columns=['Rok'])
        df_display = df_year.copy()
        for col in df_display.columns:
            if col != "Miesiąc": df_display[col] = df_display[col].apply(clean_number_formatting)
        years_dict[year] = {"display": df_display, "chart": df_year.copy(), "val_col": value_col_name}
    return title, years_dict, data, value_col_name, dyn_col_name

# ==========================================
# PARSOWANIE AI (WYMUSZENIE JSON MODE)
# ==========================================
def clean_ai_json_output(text):
    text = text.strip()
    text = re.sub(r'^```[a-zA-Z]*\n', '', text)
    text = re.sub(r'\n```$', '', text).strip()
    start_idx = text.find('[') if text.startswith('[') else text.find('{')
    end_idx = text.rfind(']') if text.endswith(']') else text.rfind('}')
    if start_idx != -1 and end_idx != -1: return text[start_idx:end_idx+1]
    return text

def ai_extract_table(csv_content, instructions, expected_columns, api_key, model_name, debug_context=""):
    if not api_key: return None
    try:
        genai.configure(api_key=api_key)
        prompt = f"Zwróć wynik jako płaską listę obiektów (Array of Objects).\nINSTRUKCJE:\n{instructions}\nWYMAGANE KLUCZE w JSON:\n{expected_columns}\nZASADY: Liczby używają kropki. NIE ZAOKRĄGLAJ.\nDANE:\n{csv_content}"
        response = genai.GenerativeModel(model_name).generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        return pd.DataFrame(json.loads(clean_ai_json_output(response.text)))
    except Exception as e:
        st.error(f"❌ Błąd AI ({debug_context}): {str(e)}")
        return None

def ai_extract_complex_table(csv_content, instructions, api_key, model_name, debug_context=""):
    if not api_key: return None
    try:
        genai.configure(api_key=api_key)
        prompt = f"Zwróć format JSON: {{\"headers\":[[\"H1\"],[\"Sub1\"]], \"data\":[[\"Cat\", 1.1]]}}\nINSTRUKCJE: {instructions}\nNIE ZAOKRĄGLAJ!\nCSV:\n{csv_content}"
        response = genai.GenerativeModel(model_name).generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        return json.loads(clean_ai_json_output(response.text))
    except Exception as e:
        st.error(f"❌ Błąd AI ({debug_context}): {str(e)}")
        return None

@st.cache_data
def get_universal_data_ai(url, api_key, model_name):
    if not url: return None
    try:
        resp = requests.get(clean_url(url), headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        if resp.status_code != 200: return None
        excel = pd.ExcelFile(io.BytesIO(resp.content))
        invalid_keywords = ['spis', 'uwag', 'tytu', 'metod', 'info']
        valid_sheets = [s for s in excel.sheet_names if not any(k in s.lower() for k in invalid_keywords)] or excel.sheet_names
        csv_text = "".join([f"\n--- {s} ---\n{pd.read_excel(excel, sheet_name=s, header=None).dropna(how='all', axis=0).dropna(how='all', axis=1).head(60).to_csv(index=False)}" for s in valid_sheets[:2]])
        
        genai.configure(api_key=api_key)
        prompt = f"Zwróć JSON: {{\"tables\": [{{\"dataset_name\": \"Tytuł\", \"recommended_chart\": \"line\", \"x_axis_column\": \"X\", \"y_axis_columns\": [\"Y1\"], \"data\": [{{\"X\": \"A\", \"Y1\": 10}}]}}]}}\nNIE ZAOKRĄGLAJ.\nCSV: {csv_text}"
        response = genai.GenerativeModel(model_name).generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        return json.loads(clean_ai_json_output(response.text))
    except Exception as e: return None

# ==========================================
# FUNKCJE AI (OPISY)
# ==========================================
def generate_ai_description(key, data_context, api_key, model_name, length_mode):
    if not HAS_GENAI or not api_key: return
    try:
        genai.configure(api_key=api_key)
        length_inst = "Napisz krótki komentarz." if length_mode == "Zwięzły" else "Napisz komentarz analityczny."
        prompt = f"Jesteś ekspertem. Skup się na trendach r/r. Nie pisz wstępów.\n{length_inst}\nDANE:\n{data_context}"
        response = genai.GenerativeModel(model_name).generate_content(prompt)
        st.session_state.descriptions[key] = response.text
    except Exception as e: pass

def display_ai_section(key, data_context):
    st.markdown("---")
    st.subheader("🤖 Komentarz")
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button(f"Generuj opis", key=f"btn_{key}"):
            with st.spinner("Generowanie..."):
                generate_ai_description(key, str(data_context)[:15000], st.session_state.gemini_key, st.session_state.model_name, st.session_state.length_mode)
            st.rerun()
    st.session_state.descriptions[key] = st.text_area("Edytuj opis:", value=st.session_state.descriptions[key], height=150, key=f"txt_{key}")

# ==========================================
# POBIERANIE DANYCH (GŁÓWNE)
# ==========================================

@st.cache_data
def get_nbp_full_table():
    url = "https://static.nbp.pl/dane/stopy/stopy_procentowe_archiwum.xml"
    try:
        headers = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/xml, text/xml, */*'}
        r = requests.get(clean_url(url), headers=headers, timeout=10)
        if r.status_code == 200:
            root = ET.fromstring(r.content)
            najnowsza = root.findall('pozycje')[-1]
            data_obowiazywania = najnowsza.get('obowiazuje_od')
            mapa_nazw = {'ref': 'Stopa referencyjna', 'lom': 'Stopa lombardowa', 'dep': 'Stopa depozytowa', 'red': 'Stopa redyskontowa weksli', 'dys': 'Stopa dyskontowa weksli'}
            dane = [{"Rodzaj Stopy": mapa_nazw[child.get('id')], "Wartość (%)": f"{float(child.get('oprocentowanie').replace(',', '.')):.2f}".replace('.', ',')} for child in najnowsza if child.get('id') in mapa_nazw]
            return pd.DataFrame(dane), data_obowiazywania
        return None, None
    except Exception: return None, None

@st.cache_data
def get_inflation_data(url):
    wyniki = {"kpi_inflacja": None, "df": None}
    try:
        resp = requests.get(clean_url(url), headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        if resp.status_code != 200: return wyniki
        df = pd.read_excel(io.BytesIO(resp.content), sheet_name=0, header=None)
        if df.shape[1] < 6: return wyniki
        data = df.iloc[:, [2, 3, 4, 5]].copy()
        data.columns = ['Metoda', 'Rok', 'Miesiąc', 'Wartość']
        for col in ['Rok', 'Miesiąc', 'Wartość']: data[col] = pd.to_numeric(data[col], errors='coerce')
        data = data.dropna(subset=['Rok', 'Miesiąc', 'Wartość'])
        data['Rok'], data['Miesiąc'] = data['Rok'].astype(int), data['Miesiąc'].astype(int)
        data = data[data['Rok'] >= data['Rok'].max() - 5]
        data['Date'] = pd.to_datetime(pd.DataFrame({'year': data['Rok'], 'month': data['Miesiąc'], 'day': 1}))
        data['Miesiąc Nazwa'] = data['Miesiąc'].apply(lambda x: MONTH_MAP.get(x, str(x)))
        data['Inflacja %'] = (data['Wartość'] - 100.0).round(1) 
        data = data.sort_values('Date', ascending=False)
        kpi_df = data[data['Metoda'].astype(str).str.contains("analogiczny miesiąc", case=False, na=False)]
        if not kpi_df.empty: wyniki["kpi_inflacja"] = kpi_df.iloc[0]['Inflacja %']
        wyniki["df"] = data
    except Exception: pass
    return wyniki

@st.cache_data
def get_gus_wages_complex(url):
    wyniki = {"kpi_placa": None, "kpi_placa_dyn": None, "kpi_zatr": None, "kpi_zatr_dyn": None, "tablica_1": None, "wykresy": []}
    try:
        resp = requests.get(clean_url(url), headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        if resp.status_code != 200: return None
        excel = pd.ExcelFile(io.BytesIO(resp.content))
        sheet_tab1 = next((s for s in excel.sheet_names if "Tablica 1" in s or "Tabl. 1" in s), None)
        if sheet_tab1:
            df = pd.read_excel(excel, sheet_name=sheet_tab1, header=None)
            header_idx = next((idx for idx, row in df.iterrows() if "WYSZCZEGÓLNIENIE" in str(row.values[0])), None)
            if header_idx is not None:
                df.columns = process_gus_header(df, header_idx)
                data_df = df.iloc[header_idx + 2:].dropna(how='all', axis=1).dropna(how='all')
                data_df = data_df.loc[:, ~data_df.columns.get_level_values(0).str.contains('^nan|^$')]
                data_df = data_df[data_df.iloc[:, 0].astype(str).apply(lambda x: not x.strip()[0].isdigit() if len(x.strip()) > 0 else True)]
                for col in data_df.columns: data_df[col] = data_df[col].apply(clean_number_formatting)
                wyniki["tablica_1"] = data_df
                for _, row in data_df.copy().iterrows():
                    opis = str(row.iloc[0]).lower()
                    vals = [parse_float_safe(x) for x in row.iloc[1:] if parse_float_safe(x) is not None]
                    val_abs = next((v for v in vals if v > 2000), None)
                    val_dyn = next((v for v in vals if 80 < v < 150), None)
                    if "wynagrodzeni" in opis and "brutto" in opis:
                        if val_abs: wyniki["kpi_placa"] = val_abs
                        if val_dyn: wyniki["kpi_placa_dyn"] = round(val_dyn - 100.0, 1)
                    if "zatrudnienie" in opis and "przeciętne" in opis:
                        if val_abs: wyniki["kpi_zatr"] = val_abs
                        if val_dyn: wyniki["kpi_zatr_dyn"] = round(val_dyn - 100.0, 1)
        for sheet_hint in ["Wykres 1", "Wykres 2"]:
            sheet = next((s for s in excel.sheet_names if sheet_hint in s), None)
            if sheet:
                title, years_data, full_data, val_col, dyn_col = process_chart_table(pd.read_excel(excel, sheet_name=sheet, header=None))
                if years_data: wyniki["wykresy"].append({"title": title, "data": years_data, "full_data": full_data, "val_col": val_col, "dyn_col": dyn_col})
    except Exception: pass
    return wyniki

@st.cache_data
def get_gus_construction_data_ai(url, api_key, model_name):
    wyniki = {"time_series": None, "regional": None}
    try:
        resp = requests.get(clean_url(url), headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        if resp.status_code != 200: return wyniki
        excel = pd.ExcelFile(io.BytesIO(resp.content))
        
        df_ts = pd.read_excel(excel, sheet_name=excel.sheet_names[0], header=None).dropna(how='all', axis=0).dropna(how='all', axis=1) 
        ts_df = ai_extract_table(df_ts.head(100).to_csv(index=False), "Zamień miesiące na pełne nazwy. Powiel rok w dół.", ["Rok", "Miesiąc", "Oddane do użytkowania", "Rozpoczęte budowy", "Wydane pozwolenia"], api_key, model_name)
        if ts_df is not None and not ts_df.empty:
            ts_df['Rok'], ts_df['Miesiąc'] = ts_df['Rok'].astype(str), ts_df['Miesiąc'].astype(str).apply(format_month_name)
            ts_df['m_num'] = ts_df['Miesiąc'].apply(get_month_number)
            wyniki["time_series"] = ts_df.sort_values(by=['Rok', 'm_num'], ascending=[False, False]).drop(columns=['m_num'])
            
        if len(excel.sheet_names) > 1:
            sheet_reg = next((s for s in excel.sheet_names if "Wykres 2" in s or "Tabl" in s), excel.sheet_names[1])
            df_reg = pd.read_excel(excel, sheet_name=sheet_reg, header=None).dropna(how='all', axis=0).dropna(how='all', axis=1)
            reg_df = ai_extract_table(df_reg.head(80).to_csv(index=False), "Podział na województwa. Ignoruj sumę POLSKA.", ["Obszar", "Pozwolenia wydane", "Rozpoczęte budowy", "Oddane do użytkowania"], api_key, model_name)
            if reg_df is not None: wyniki["regional"] = reg_df
    except Exception: pass
    return wyniki

@st.cache_data
def get_construction_prices_ai(url, api_key, model_name):
    wyniki = {"headers": None, "data": None}
    try:
        resp = requests.get(clean_url(url), headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        if resp.status_code != 200: return wyniki
        df_clean = pd.read_excel(io.BytesIO(resp.content), sheet_name=0, header=None).dropna(how='all', axis=0).dropna(how='all', axis=1)
        json_data = ai_extract_complex_table(df_clean.head(50).to_csv(index=False), "Pobierz nagłówki i wiersze z danymi.", api_key, model_name)
        if json_data and "headers" in json_data and "data" in json_data:
            extracted_df = pd.DataFrame(json_data["data"])
            if len(json_data["headers"][0]) == len(extracted_df.columns):
                wyniki["headers"] = json_data["headers"]
                wyniki["data"] = extracted_df
    except Exception: pass
    return wyniki

@st.cache_data
def get_gus_quarterly_data(url):
    wyniki = {"mapa": None, "wykresy": []}
    try:
        resp = requests.get(clean_url(url), headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        if resp.status_code != 200: return wyniki
        excel = pd.ExcelFile(io.BytesIO(resp.content))
        
        sheet_map = next((s for s in excel.sheet_names if "mapa" in s.lower()), None)
        if sheet_map:
            df = pd.read_excel(excel, sheet_name=sheet_map, header=None)
            data_rows = [{"Województwo": str(row.iloc[0]).strip(), "Wartość": next((parse_float_safe(row.iloc[c]) for c in range(1, len(row)) if parse_float_safe(row.iloc[c]) is not None), None)} for i, row in df.iterrows() if i >= 2 and str(row.iloc[0]).strip().lower() != 'nan']
            if data_rows: wyniki["mapa"] = {"title": str(df.iloc[0, 0]).strip(), "data": pd.DataFrame([d for d in data_rows if d['Wartość'] is not None])}

        for sheet_name in excel.sheet_names:
            if not re.match(r'^wykres\s*\d+$', sheet_name.strip().lower()): continue
            df = pd.read_excel(excel, sheet_name=sheet_name, header=None)
            title = str(df.iloc[0, 0]).strip() if not pd.isna(df.iloc[0, 0]) else sheet_name
            data_raw = df.iloc[2:].dropna(how='all', axis=1).dropna(how='all', axis=0)
            if data_raw.empty: continue
            
            sheet_num = int(re.findall(r'\d+', sheet_name)[0])
            if sheet_num in [1, 8] and data_raw.shape[1] >= 2:
                data = data_raw.iloc[:, :2]
                data.columns, data["Udział"] = ["Kategoria", "Udział"], data.iloc[:, 1].apply(parse_float_safe)
                wyniki["wykresy"].append({"type": "pie", "title": title, "data": data})
            elif sheet_num in [2, 9] and data_raw.shape[1] >= 4:
                data = data_raw.iloc[:, :4]
                data.columns = ["Województwo", "Okres Bieżący", "Okres Poprzedni", "Zmiana"]
                for c in ["Okres Bieżący", "Okres Poprzedni", "Zmiana"]: data[c] = data[c].apply(parse_float_safe)
                wyniki["wykresy"].append({"type": "compare", "title": title, "data": data})
            elif data_raw.shape[1] >= 2:
                data = data_raw.iloc[:, :2]
                data.columns, data["Wartość"] = ["Województwo", "Wartość"], data.iloc[:, 1].apply(parse_float_safe)
                wyniki["wykresy"].append({"type": "bar", "title": title, "data": data})
    except Exception: pass
    return wyniki

# ==========================================
# KOMPONENTY UI (PANEL BOCZNY I EKSPORT)
# ==========================================

def render_sidebar():
    with st.sidebar:
        st.header("⚙️ Konfiguracja")
        
        st.session_state.gemini_key = st.text_input("Klucz API Gemini (Wymagany do parsera)", value=st.session_state.get('gemini_key', ''), type="password")
        model_options = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro", "gemini-2.0-flash-lite", "gemini-3-flash-preview", "gemini-3.1-pro-preview"]
        st.session_state.model_name = st.selectbox("Model AI", model_options, index=model_options.index(st.session_state.get('model_name', 'gemini-2.5-flash')))
        st.session_state.length_mode = st.select_slider("Długość opisu AI", options=["Zwięzły", "Standardowy", "Szczegółowy"], value=st.session_state.get('length_mode', 'Standardowy'))
        
        st.session_state.rok = st.number_input("Rok raportu", value=st.session_state.get('rok', 2025))
        st.session_state.miesiac = st.selectbox("Miesiąc raportu", MONTH_ORDER, index=MONTH_ORDER.index(st.session_state.get('miesiac', 'Grudzień')))
        
        st.markdown("---")
        st.info("Linki do plików GUS (XLSX):")
        st.caption("Obszary tematyczne -> wskaźniki cen -> wskaźniki cen towarów i usług konsumpcyjnych")
        link_inflacja = st.text_input("GUS Inflacja", value="https://stat.gov.pl/download/gfx/portalinformacyjny/pl/defaultstronaopisowa/4741/1/1/miesiecznewskaznikicentowarowiuslugkonsumpcyjnychod1982roku_4.xlsx")
        st.caption("Obszary tematyczne -> rynek pracy -> przeciętne zatrudnienie i wynagrodzenie")
        link_place = st.text_input("GUS Płace", value="https://stat.gov.pl/download/gfx/portalinformacyjny/pl/defaultaktualnosci/5474/3/169/1/przecietne_zatrudnienie_i_wynagrodzenie_w_sektorze_przedsiebiorstw_w_grudniu_2025_r._wykresy.xlsx")
        st.caption("Obszary tematyczne -> przemysł. Budownictwo -> budownictwo mieszkaniowe")
        link_budowa = st.text_input("GUS Budownictwo", value="https://stat.gov.pl/download/gfx/portalinformacyjny/pl/defaultaktualnosci/5478/5/171/1/budownictwo_mieszkaniowe_w_okresie_styczengrudzien_2025_r._wykresy.xlsx")
        st.caption("Obszary tematyczne -> przemysł. budownictwo -> budownictwo w x-x kwartale")
        link_kwartalne = st.text_input("GUS Budownictwo Kwartalne", value="https://stat.gov.pl/download/gfx/portalinformacyjny/pl/defaultaktualnosci/5478/13/28/1/budownictwo_w_1-3_kwartale_2025_r._wykresy.xlsx")
        st.caption("Obszary tematyczne -> ceny -> wskaźniki cen produkcji budowlano-montażowej")
        link_ceny_bud = st.text_input("GUS Ceny Budowlane", value="https://stat.gov.pl/download/gfx/portalinformacyjny/pl/defaultaktualnosci/5464/15/85/1/wskazniki_cen_produkcji_budowlano-montazowej_w_grudniu_2025_r_tablice.xlsx")
        
        st.markdown("---")
        st.markdown("### 🪄 Magiczny Panel Uniwersalny")
        st.caption("Wklej link z tabelą, a AI samo zgadnie co to za dane i jak je narysować!")
        link_universal = st.text_input("Link do dowolnego arkusza Excel z GUS:", value="")

        if st.button("🚀 POBIERZ DANE", type="primary"):
            if not st.session_state.gemini_key: st.error("❗ Wpisz Klucz API Gemini (AI) - jest niezbędny.")
            else:
                with st.spinner("Pobieranie i analizowanie danych przez AI..."):
                    st.session_state.nbp_df, st.session_state.nbp_date = get_nbp_full_table()
                    st.session_state.inflacja = get_inflation_data(link_inflacja)
                    st.session_state.gus_praca = get_gus_wages_complex(link_place)
                    st.session_state.gus_budowa = get_gus_construction_data_ai(link_budowa, st.session_state.gemini_key, st.session_state.model_name)
                    st.session_state.gus_kwartalne = get_gus_quarterly_data(link_kwartalne)
                    st.session_state.ceny_bud = get_construction_prices_ai(link_ceny_bud, st.session_state.gemini_key, st.session_state.model_name)
                    if link_universal: st.session_state.universal_data = get_universal_data_ai(link_universal, st.session_state.gemini_key, st.session_state.model_name)
                    st.session_state.data_loaded = True

def render_bik_section(title, url):
    clean_url_b = f"{clean_url(url)}?:showVizHome=no&:embed=true&:toolbar=no&:size=1200,1100"
    st.markdown(f'<div style="margin-bottom: 40px;"><h4 style="margin: 0 0 10px 0;">{title}</h4><iframe src="{clean_url_b}" width="100%" height="1150" style="border:none; overflow:hidden;" scrolling="no"></iframe></div>', unsafe_allow_html=True)