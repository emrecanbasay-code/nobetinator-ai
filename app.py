import streamlit as st
import pandas as pd
import numpy as np
from ortools.sat.python import cp_model
import json
from datetime import datetime
import calendar
import io
import xlsxwriter

# --- SAYFA VE TASARIM AYARLARI ---
st.set_page_config(
    page_title="Nobetinator AI",
    page_icon="🌑",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- DARK PRO CSS TASARIMI ---
st.markdown("""
<style>
    .stApp { background-color: #0f172a !important; }
    h1, h2, h3, h4, h5, h6, p, span, div, label { color: #e2e8f0 !important; }
    [data-testid="stSidebar"] { background-color: #1e293b !important; border-right: 1px solid #334155; }
    .css-card { 
        background-color: #1e293b !important; 
        padding: 20px; 
        border-radius: 12px; 
        border: 1px solid #334155;
        margin-bottom: 20px; 
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.5);
    }
    div[data-testid="stMetric"] { 
        background-color: #1e293b !important; 
        border: 1px solid #334155; 
        padding: 15px; 
        border-radius: 10px; 
        text-align: center;
    }
    div[data-testid="stMetricLabel"] > div { color: #94a3b8 !important; }
    div[data-testid="stMetricValue"] > div { color: #38bdf8 !important; }
    .stButton>button { 
        background-color: #3b82f6 !important; 
        color: white !important; 
        border-radius: 8px; 
        border: none; 
        padding: 0.6rem 1.2rem; 
        font-weight: 600; 
        box-shadow: 0 4px 6px rgba(59, 130, 246, 0.3);
        transition: all 0.2s ease; 
        width: 100%;
    }
    .stButton>button:hover { 
        background-color: #2563eb !important; 
        transform: translateY(-2px);
    }
    div[data-testid="stFileUploader"] {
        padding-top: 0px;
    }
    div[data-testid="stFileUploader"] button { background-color: #475569 !important; }
    div[data-testid="stDataEditor"] {
        background-color: #1e293b; 
        border-radius: 10px;
        border: 1px solid #334155;
    }
    div[data-testid="stDataEditor"] * {
        color: #e2e8f0 !important;
        background-color: #1e293b !important;
    }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; background-color: transparent; }
    .stTabs [data-baseweb="tab"] { background-color: #1e293b; border-radius: 5px; color: #94a3b8; border: 1px solid #334155; }
    .stTabs [aria-selected="true"] { background-color: #3b82f6 !important; color: white !important; border: none; }
    header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# --- YARDIMCI FONKSİYONLAR ---
def get_storage_key(y, m): return f"{y}_{m}"

def normalize_col(col_name):
    return str(col_name).strip()

def save_current_month_data():
    if 'db' not in st.session_state: st.session_state.db = {}
    key = get_storage_key(st.session_state.year, st.session_state.month)
    st.session_state.db[key] = {
        "daily_needs_24h": st.session_state.daily_needs_24h.copy(),
        "daily_needs_16h": st.session_state.daily_needs_16h.copy(),
        "quotas_24h": st.session_state.quotas_24h.copy(),
        "quotas_16h": st.session_state.quotas_16h.copy(),
        "manual_constraints": st.session_state.manual_constraints.copy()
    }

def load_month_data(y, m):
    key = get_storage_key(y, m)
    if 'db' in st.session_state and key in st.session_state.db:
        data = st.session_state.db[key]
        st.session_state.daily_needs_24h = data["daily_needs_24h"]
        st.session_state.daily_needs_16h = data["daily_needs_16h"]
        st.session_state.quotas_24h = data["quotas_24h"]
        st.session_state.quotas_16h = data["quotas_16h"]
        st.session_state.manual_constraints = data["manual_constraints"]
    else:
        st.session_state.daily_needs_24h = {}
        st.session_state.daily_needs_16h = {}
        # Yüklü veri yoksa varsayılanları tekrar oluştur (Init bloğu aşağıda)
        init_defaults()

def init_defaults():
    # Yeni Doktor Listesi (Dosyadan alındı)
    initial_doctors = [
        "A01", "A02", "A03", "A4", "A5", "A6", "A7", "A8", "A9", "A10", 
        "A11", "A12", "A13", "A14", "A15", "A16", "A17", "A18", "A19", "A20", 
        "A21", "A22", "A23", "A24", "A25", "A26", "A27", "A28", "A29", "A30", 
        "A31", "A32", "A33"
    ]
    
    st.session_state.doctors = initial_doctors
    
    q24 = {}
    q16 = {}
    
    for doc in initial_doctors:
        # Varsayılan Kural: A01-A21 arası 8/0
        d_24, d_16 = 8, 0
        
        # İstisnalar (Dosyaya göre)
        if doc in ["A22", "A23"] or doc in [f"A{i}" for i in range(25, 34)]: # A25-A33
            d_24, d_16 = 8, 2
        elif doc == "A24":
            d_24, d_16 = 6, 2
            
        q24[doc] = d_24
        q16[doc] = d_16
        
    st.session_state.quotas_24h = q24
    st.session_state.quotas_16h = q16
    st.session_state.manual_constraints = {}


# --- BAŞLANGIÇ ---
if 'year' not in st.session_state: st.session_state.year = datetime.now().year
if 'month' not in st.session_state: st.session_state.month = datetime.now().month
if 'db' not in st.session_state: st.session_state.db = {}
if 'editor_key' not in st.session_state: st.session_state.editor_key = 0

if 'daily_needs_24h' not in st.session_state: st.session_state.daily_needs_24h = {}
if 'daily_needs_16h' not in st.session_state: st.session_state.daily_needs_16h = {}

# Doktor ve Kota Başlatma (Eğer yoksa)
if 'doctors' not in st.session_state or 'quotas_24h' not in st.session_state:
    init_defaults()

if 'manual_constraints' not in st.session_state: st.session_state.manual_constraints = {}

# --- SIDEBAR ---
with st.sidebar:
    st.title("🌑 Nobetinator Pro")
    st.caption("AI Destekli Nöbet Planlama")
    st.markdown("---")
    
    col1, col2 = st.columns(2)
    with col1: selected_year = st.number_input("Yıl", 2020, 2030, st.session_state.year)
    with col2: selected_month = st.selectbox("Ay", range(1, 13), index=st.session_state.month-1, format_func=lambda x: calendar.month_name[x])
    
    if selected_year != st.session_state.year or selected_month != st.session_state.month:
        save_current_month_data()
        st.session_state.year = selected_year
        st.session_state.month = selected_month
        load_month_data(selected_year, selected_month)
        st.rerun()

    num_days = calendar.monthrange(selected_year, selected_month)[1]
    st.markdown("---")
    st.subheader("⚙️ Kurallar")
    rest_days_24h = st.slider("24h Sonrası Yasaklı Gün", 1, 5, 2)
    st.markdown("---")
    st.subheader("🎛️ AI Stratejisi")
    solver_mode = st.radio("Mod:", ["Katı Kurallar (Tam Uyum)", "Esnek Mod (Tavan Sınır)"], index=1)
    st.markdown("---")
    
    with st.expander("👨‍⚕️ Kadro Yönetimi"):
        new_doc = st.text_input("Eklenecek İsim")
        if st.button("Listeye Ekle") and new_doc:
            if new_doc not in st.session_state.doctors:
                st.session_state.doctors.append(new_doc)
                st.rerun()
        rem_doc = st.selectbox("Silinecek İsim", [""] + st.session_state.doctors)
        if st.button("Listeden Sil") and rem_doc:
            st.session_state.doctors.remove(rem_doc)
            st.rerun()

    with st.expander("💾 Veri İşlemleri"):
        if st.button("Yedek İndir (JSON)"):
            save_current_month_data()
            d_out = {"doctors": st.session_state.doctors, "db": {str(k): v for k, v in st.session_state.db.items()}, "current_year": st.session_state.year, "current_month": st.session_state.month}
            st.download_button("📥 JSON İndir", json.dumps(d_out, default=str), "nobetinator_backup.json")
        upl = st.file_uploader("Yedek Yükle", type=['json'])
        if upl:
            try:
                data = json.load(upl)
                st.session_state.doctors = data.get('doctors', st.session_state.doctors)
                st.rerun()
            except: pass
        if st.button("🔄 Ayarları Sıfırla (Dosya Verisine Dön)"):
            init_defaults()
            st.rerun()

# --- DASHBOARD ---
st.markdown(f"### 🗓️ {calendar.month_name[st.session_state.month]} {st.session_state.year} Dashboard")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Toplam Gün", num_days)
c2.metric("Personel Sayısı", len(st.session_state.doctors))
c3.metric("Mod", "Esnek" if "Esnek" in solver_mode else "Katı")
c4.metric("Kısıtlar", len(st.session_state.manual_constraints))

st.write("") 

t1, t2, t3, t4 = st.tabs(["📋 GÜNLÜK İHTİYAÇ", "🎯 KOTALAR (LİMİT)", "🔒 KISITLAR (X)", "🚀 SONUÇ & RAPOR"])

# TAB 1: GÜNLÜK İHTİYAÇ
with t1:
    st.markdown('<div class="css-card">', unsafe_allow_html=True)
    # Varsayılan değerler
    for d in range(1, num_days+1):
        if d not in st.session_state.daily_needs_24h: st.session_state.daily_needs_24h[d] = 1
        if d not in st.session_state.daily_needs_16h: st.session_state.daily_needs_16h[d] = 1

    # --- EXCEL YÜKLEME ---
    with st.expander("📤 İhtiyaçları Excel ile Yükle", expanded=True):
        col_dl, col_up = st.columns([1, 2])
        with col_dl:
            # Excel Şablonu
            daily_template = []
            for d in range(1, num_days + 1):
                daily_template.append({"Gün": d, "24h İhtiyaç": 1, "16h İhtiyaç": 1})
            df_daily_temp = pd.DataFrame(daily_template)
            
            buf_daily = io.BytesIO()
            with pd.ExcelWriter(buf_daily, engine='xlsxwriter') as writer:
                df_daily_temp.to_excel(writer, index=False, sheet_name='Ihtiyaclar')
            
            st.download_button(
                label="📥 Excel Şablonu İndir", 
                data=buf_daily.getvalue(), 
                file_name="gunluk_ihtiyac_sablonu.xlsx", 
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        
        with col_up:
            # BURADA FORM YOK - DOĞRUDAN ÇALIŞIR
            up_daily = st.file_uploader("Excel Dosyası (.xlsx)", type=["xlsx"], label_visibility="collapsed", key="u_daily")
            
            if st.button("📂 İhtiyaçları Güncelle", type="primary", key="btn_daily"):
                if up_daily:
                    try:
                        df_d = pd.read_excel(up_daily, engine='openpyxl')
                        df_d.columns = [normalize_col(c) for c in df_d.columns]
                        
                        if len(df_d.columns) >= 2: 
                            for idx, row in df_d.iterrows():
                                try:
                                    d_val = int(row.iloc[0])
                                    if 1 <= d_val <= num_days:
                                        if len(row) > 1: st.session_state.daily_needs_24h[d_val] = int(row.iloc[1])
                                        if len(row) > 2: st.session_state.daily_needs_16h[d_val] = int(row.iloc[2])
                                except: pass
                            
                            st.success("✅ Günlük ihtiyaçlar güncellendi!")
                            st.session_state.editor_key += 1
                            st.rerun()
                        else:
                            st.error("Excel formatı anlaşılamadı. Lütfen şablonu kullanın.")
                    except Exception as e:
                        st.error(f"Hata: {e}")
                else:
                    st.warning("Lütfen önce bir dosya seçin.")

    # Tablo
    d_data = [{"Gün": d, "Tarih": f"{d} {['Pzt','Sal','Çar','Per','Cum','Cmt','Paz'][datetime(st.session_state.year, st.session_state.month, d).weekday()]}", "24h": st.session_state.daily_needs_24h.get(d, 1), "16h": st.session_state.daily_needs_16h.get(d, 1)} for d in range(1, num_days+1)]
    
    with st.form("needs_manual"):
        edf = st.data_editor(pd.DataFrame(d_data), key=f"need_ed_{st.session_state.editor_key}", use_container_width=True, hide_index=True, column_config={"Gün": st.column_config.NumberColumn(disabled=True), "Tarih": st.column_config.TextColumn(disabled=True)})
        if st.form_submit_button("💾 Tablodan Kaydet"):
            for i, r in edf.iterrows():
                st.session_state.daily_needs_24h[r["Gün"]] = int(r["24h"])
                st.session_state.daily_needs_16h[r["Gün"]] = int(r["16h"])
            st.success("Kaydedildi!")
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# TAB 2: KOTALAR
with t2:
    st.markdown('<div class="css-card">', unsafe_allow_html=True)
    
    total_need_24 = sum(st.session_state.daily_needs_24h.get(d, 1) for d in range(1, num_days+1))
    total_need_16 = sum(st.session_state.daily_needs_16h.get(d, 1) for d in range(1, num_days+1))
    current_dist_24 = sum(st.session_state.quotas_24h.get(d, 0) for d in st.session_state.doctors)
    current_dist_16 = sum(st.session_state.quotas_16h.get(d, 0) for d in st.session_state.doctors)
    
    col_q1, col_q2 = st.columns(2)
    col_q1.metric("24h İhtiyaç / Dağıtılan", f"{total_need_24} / {current_dist_24}", delta=f"{current_dist_24 - total_need_24}", delta_color="off")
    col_q2.metric("16h İhtiyaç / Dağıtılan", f"{total_need_16} / {current_dist_16}", delta=f"{current_dist_16 - total_need_16}", delta_color="off")
    
    st.markdown("---")
    
    with st.expander("📤 Kota Toplu Yükleme (Excel)", expanded=True):
        col_dl, col_up = st.columns([1, 2])
        with col_dl:
            sample_data = [{"Dr": d, "Max 24h": 0, "Max 16h": 0} for d in st.session_state.doctors]
            sample_df = pd.DataFrame(sample_data)
            
            buf_quota = io.BytesIO()
            with pd.ExcelWriter(buf_quota, engine='xlsxwriter') as writer:
                sample_df.to_excel(writer, index=False, sheet_name='Kotalar')
                
            st.download_button(
                label="📥 Excel Şablonu İndir", 
                data=buf_quota.getvalue(), 
                file_name="kota_sablonu.xlsx", 
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
                use_container_width=True
            )
        
        with col_up:
            # BURADA FORM YOK
            uploaded_quotas = st.file_uploader("Excel Dosyası", type=["xlsx"], label_visibility="collapsed", key="u_quota")
            
            if st.button("📂 Kotaları İşle", type="primary", key="btn_quota"):
                if uploaded_quotas:
                    try:
                        df_up = pd.read_excel(uploaded_quotas, engine='openpyxl')
                        df_up.columns = [normalize_col(c) for c in df_up.columns]
                        
                        doc_map = {d.lower().strip(): d for d in st.session_state.doctors}
                        
                        col_dr = next((c for c in df_up.columns if "dr" in c.lower()), None)
                        col_24 = next((c for c in df_up.columns if "24" in c), None)
                        col_16 = next((c for c in df_up.columns if "16" in c), None)
                        
                        if col_dr and col_24:
                            count = 0
                            for idx, row in df_up.iterrows():
                                dname_raw = str(row[col_dr]).lower().strip()
                                if dname_raw in doc_map:
                                    real_name = doc_map[dname_raw]
                                    try:
                                        st.session_state.quotas_24h[real_name] = int(row[col_24])
                                        if col_16: st.session_state.quotas_16h[real_name] = int(row[col_16])
                                        count += 1
                                    except: pass
                            
                            st.success(f"✅ {count} doktorun kotası güncellendi!")
                            st.session_state.editor_key += 1
                            st.rerun()
                        else:
                            st.error(f"Sütunlar bulunamadı. Dosyada 'Dr' ve '24' içeren başlıklar olmalı.")
                    except Exception as e: st.error(f"Hata: {e}")
                else:
                    st.warning("Dosya seçilmedi.")

    # Tablo
    q_data = [{"Dr": d, "Max 24h": st.session_state.quotas_24h.get(d, 0), "Max 16h": st.session_state.quotas_16h.get(d, 0)} for d in st.session_state.doctors]
    with st.form("quotas_manual"):
        qdf = st.data_editor(pd.DataFrame(q_data), key=f"quota_ed_{st.session_state.editor_key}", use_container_width=True, hide_index=True, column_config={"Dr": st.column_config.TextColumn(disabled=True)})
        if st.form_submit_button("💾 Tablodan Kaydet"):
            for i, r in qdf.iterrows():
                st.session_state.quotas_24h[r["Dr"]] = int(r["Max 24h"])
                st.session_state.quotas_16h[r["Dr"]] = int(r["Max 16h"])
            st.success("Kaydedildi!")
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# TAB 3: MANUEL KISITLAR
with t3:
    st.markdown('<div class="css-card">', unsafe_allow_html=True)
    st.write(f"💡 **İpucu:** '24' seçerseniz, sonraki **{rest_days_24h} gün** otomatik bloklanır.")
    
    with st.expander("📤 Kısıtları Toplu Yükle (Excel)", expanded=True):
        st.info("Hücrelere '24', '16' veya 'X' yazabilirsiniz. Boş bırakırsanız kısıt yok demektir.")
        
        col_kd, col_ku = st.columns([1, 2])
        with col_kd:
            days_header = [str(d) for d in range(1, num_days + 1)]
            template_data = []
            for d in st.session_state.doctors:
                row = {"Dr": d}
                for day in days_header: row[day] = "" 
                template_data.append(row)
            
            df_temp = pd.DataFrame(template_data)
            
            buf_const = io.BytesIO()
            with pd.ExcelWriter(buf_const, engine='xlsxwriter') as writer:
                df_temp.to_excel(writer, index=False, sheet_name='Kisitlar')

            st.download_button(
                label="📥 Excel Şablonu İndir", 
                data=buf_const.getvalue(), 
                file_name="kisit_sablonu.xlsx", 
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
                use_container_width=True
            )

        with col_ku:
            # BURADA FORM YOK
            up_const = st.file_uploader("Excel Dosyası", type=["xlsx"], label_visibility="collapsed", key="u_const")
            
            if st.button("📂 Kısıtları İşle", type="primary", key="btn_const"):
                if up_const:
                    try:
                        df_c = pd.read_excel(up_const, engine='openpyxl')
                        df_c.columns = [normalize_col(c) for c in df_c.columns]
                        
                        doc_map = {d.lower().strip(): d for d in st.session_state.doctors}
                        col_dr = next((c for c in df_c.columns if "dr" in c.lower()), None)
                        
                        if col_dr:
                            processed_count = 0
                            for idx, row in df_c.iterrows():
                                dname_raw = str(row[col_dr]).lower().strip()
                                if dname_raw in doc_map:
                                    real_name = doc_map[dname_raw]
                                    
                                    for day in range(1, num_days + 1):
                                        d_col = str(day)
                                        if d_col in df_c.columns:
                                            raw_val = row[d_col]
                                            if pd.notna(raw_val):
                                                val = str(raw_val).strip().upper()
                                                if val in ["24", "16", "X"]:
                                                    st.session_state.manual_constraints[f"{real_name}_{day}"] = val
                                                    if val == "24":
                                                        for off in range(1, rest_days_24h+1):
                                                            if day+off <= num_days: 
                                                                st.session_state.manual_constraints[f"{real_name}_{day+off}"] = "X"
                                                elif val == "":
                                                    k = f"{real_name}_{day}"
                                                    if k in st.session_state.manual_constraints:
                                                        del st.session_state.manual_constraints[k]
                                    processed_count += 1
                            
                            st.success(f"✅ {processed_count} doktor kısıtı yüklendi!")
                            st.session_state.editor_key += 1
                            st.rerun()
                        else:
                            st.error("Dosyada 'Dr' sütunu bulunamadı.")
                    except Exception as e:
                        st.error(f"Hata oluştu: {e}")
                else:
                    st.warning("Dosya seçilmedi.")

    # Tablo
    c_data = []
    for doc in st.session_state.doctors:
        r = {"Doktor": doc}
        for d in range(1, num_days+1): r[str(d)] = st.session_state.manual_constraints.get(f"{doc}_{d}", "")
        c_data.append(r)
        
    col_cfg = {"Doktor": st.column_config.TextColumn(disabled=True)}
    for d in range(1, num_days+1):
        dn = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"][datetime(st.session_state.year, st.session_state.month, d).weekday()]
        col_cfg[str(d)] = st.column_config.SelectboxColumn(label=f"{d} {dn}", options=["", "24", "16", "X"], width="small")
        
    with st.form("const_manual"):
        ed_cons = st.data_editor(pd.DataFrame(c_data), column_config=col_cfg, hide_index=True, use_container_width=True, key=f"cons_ed_{st.session_state.editor_key}")
        if st.form_submit_button("💾 Tablodan Kaydet"):
            updated = False
            for i, r in ed_cons.iterrows():
                doc = r["Doktor"]
                for d in range(1, num_days+1):
                    val = str(r[str(d)])
                    k = f"{doc}_{d}"
                    if val != st.session_state.manual_constraints.get(k, ""):
                        if val in ["24", "16", "X"]:
                            st.session_state.manual_constraints[k] = val
                            if val == "24":
                                for off in range(1, rest_days_24h+1):
                                    if d+off <= num_days: st.session_state.manual_constraints[f"{doc}_{d+off}"] = "X"
                        else:
                            if k in st.session_state.manual_constraints: del st.session_state.manual_constraints[k]
                        updated = True
            if updated: st.rerun()
            else: st.success("Değişiklik yok.")
    st.markdown('</div>', unsafe_allow_html=True)

# TAB 4: HESAPLAMA
with t4:
    st.markdown('<div class="css-card">', unsafe_allow_html=True)
    if st.button("🚀 Nöbetleri Dağıt (AI)", type="primary", use_container_width=True):
        with st.spinner("Hesaplanıyor..."):
            model = cp_model.CpModel()
            docs = st.session_state.doctors
            days = range(1, num_days+1)
            x24, x16 = {}, {}

            for d in docs:
                for t in days:
                    x24[(d,t)] = model.NewBoolVar(f'x24_{d}_{t}')
                    x16[(d,t)] = model.NewBoolVar(f'x16_{d}_{t}')
                    model.Add(x24[(d,t)] + x16[(d,t)] <= 1)

            for t in days:
                need24 = st.session_state.daily_needs_24h.get(t, 1)
                need16 = st.session_state.daily_needs_16h.get(t, 1)
                model.Add(sum(x24[(d,t)] for d in docs) == need24)
                model.Add(sum(x16[(d,t)] for d in docs) == need16)

            for d in docs:
                for t in range(1, num_days):
                    model.Add(x24[(d,t)] + x16[(d,t)] + x24[(d,t+1)] + x16[(d,t+1)] <= 1)
                win = rest_days_24h + 1
                for i in range(len(days) - win + 1):
                    wd = [days[j] for j in range(i, i+win)]
                    model.Add(sum(x24[(d,k)] for k in wd) <= 1)

            for d in docs:
                for t in days:
                    c = st.session_state.manual_constraints.get(f"{d}_{t}", "")
                    if c == "24": model.Add(x24[(d,t)] == 1)
                    elif c == "16": model.Add(x16[(d,t)] == 1)
                    elif c == "X": 
                        model.Add(x24[(d,t)] == 0)
                        model.Add(x16[(d,t)] == 0)

            deviations = []
            for d in docs:
                tot24 = sum(x24[(d,t)] for t in days)
                tgt24 = st.session_state.quotas_24h.get(d, 0)
                if "Katı" in solver_mode: model.Add(tot24 <= tgt24)
                else:
                    model.Add(tot24 <= tgt24) 
                    diff = model.NewIntVar(0, 31, f'd24_{d}')
                    model.Add(diff == tgt24 - tot24)
                    deviations.append(diff)
                
                tot16 = sum(x16[(d,t)] for t in days)
                tgt16 = st.session_state.quotas_16h.get(d, 0)
                if "Katı" in solver_mode: model.Add(tot16 <= tgt16)
                else:
                    model.Add(tot16 <= tgt16)
                    diff = model.NewIntVar(0, 31, f'd16_{d}')
                    model.Add(diff == tgt16 - tot16)
                    deviations.append(diff)
            
            if "Esnek" in solver_mode: model.Minimize(sum(deviations))

            solver = cp_model.CpSolver()
            status = solver.Solve(model)

            if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
                st.success("✅ Çizelge Hazır!")
                res_mx, res_lst = [], []
                stats = {d: {"24h":0, "16h":0} for d in docs}
                
                for t in days:
                    dt = datetime(st.session_state.year, st.session_state.month, t)
                    dstr = f"{t:02d} {['Pzt','Sal','Çar','Per','Cum','Cmt','Paz'][dt.weekday()]}"
                    rm = {"Tarih": dstr}
                    l24, l16 = [], []
                    for d in docs:
                        if solver.Value(x24[(d,t)]): 
                            rm[d]="24h"; l24.append(d); stats[d]["24h"]+=1
                        elif solver.Value(x16[(d,t)]): 
                            rm[d]="16h"; l16.append(d); stats[d]["16h"]+=1
                        else: rm[d]=""
                    res_mx.append(rm)
                    res_lst.append({"Tarih": dstr, "24 Saat": ", ".join(l24), "16 Saat": ", ".join(l16)})
                
                stat_data = []
                for d in docs:
                    t24 = st.session_state.quotas_24h.get(d, 0)
                    t16 = st.session_state.quotas_16h.get(d, 0)
                    stat_data.append({
                        "Doktor": d,
                        "24h (Hedef)": t24, "24h (Gerçek)": stats[d]["24h"],
                        "16h (Hedef)": t16, "16h (Gerçek)": stats[d]["16h"],
                        "Durum": "✅ Tam" if (stats[d]["24h"]==t24 and stats[d]["16h"]==t16) else "⚠️ Eksik"
                    })
                
                df_mx = pd.DataFrame(res_mx)
                df_ls = pd.DataFrame(res_lst)
                df_st = pd.DataFrame(stat_data)
                
                st.dataframe(df_st, use_container_width=True)
                vt1, vt2 = st.tabs(["Renkli Genel Tablo", "Günlük Liste Görünümü"])
                with vt1: st.dataframe(df_mx.style.applymap(lambda v: 'background-color: #ef4444; color: white' if v=='24h' else ('background-color: #22c55e; color: white' if v=='16h' else '')), use_container_width=True)
                with vt2: st.dataframe(df_ls, use_container_width=True)
                
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
                    df_ls.to_excel(writer, sheet_name='Liste', index=False)
                    df_mx.to_excel(writer, sheet_name='Cizelge', index=False)
                    df_st.to_excel(writer, sheet_name='Istatistik', index=False)
                st.download_button("📥 Excel Olarak İndir", buf.getvalue(), "nobet_cizelgesi.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            else:
                st.error("Çözüm Bulunamadı! Kısıtları gevşetin.")
    st.markdown('</div>', unsafe_allow_html=True)
