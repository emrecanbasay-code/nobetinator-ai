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
    }
    div[data-testid="stMetric"] { background-color: #1e293b !important; border: 1px solid #334155; border-radius: 10px; }
    .stButton>button { 
        background-color: #3b82f6 !important; 
        color: white !important; 
        border: none; padding: 0.6rem 1.2rem; font-weight: 600; 
    }
    .stButton>button:hover { background-color: #2563eb !important; }
    div[data-testid="stDataEditor"] { border: 1px solid #334155; border-radius: 10px; }
</style>
""", unsafe_allow_html=True)

# --- YARDIMCI FONKSİYONLAR ---
def normalize_string(s):
    """Metinleri karşılaştırmak için temizler (boşluk siler, küçük harfe çevirir)."""
    if pd.isna(s): return ""
    return str(s).strip().lower()

def get_storage_key(y, m): return f"{y}_{m}"

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
        st.session_state.quotas_24h = {doc: 0 for doc in st.session_state.doctors}
        st.session_state.quotas_16h = {doc: 0 for doc in st.session_state.doctors}
        st.session_state.manual_constraints = {}

# --- BAŞLANGIÇ ---
if 'doctors' not in st.session_state: st.session_state.doctors = ["Dr. Ahmet", "Dr. Ayşe", "Dr. Mehmet", "Dr. Zeynep", "Dr. Can"]
if 'year' not in st.session_state: st.session_state.year = datetime.now().year
if 'month' not in st.session_state: st.session_state.month = datetime.now().month
if 'db' not in st.session_state: st.session_state.db = {}
if 'editor_key' not in st.session_state: st.session_state.editor_key = 0

if 'daily_needs_24h' not in st.session_state: st.session_state.daily_needs_24h = {}
if 'daily_needs_16h' not in st.session_state: st.session_state.daily_needs_16h = {}
if 'quotas_24h' not in st.session_state: st.session_state.quotas_24h = {}
if 'quotas_16h' not in st.session_state: st.session_state.quotas_16h = {}
if 'manual_constraints' not in st.session_state: st.session_state.manual_constraints = {}

# --- SIDEBAR ---
with st.sidebar:
    st.title("🌑 Nobetinator v10")
    
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
    st.subheader("⚙️ Ayarlar")
    rest_days_24h = st.slider("24h Sonrası İzin", 1, 5, 2)
    solver_mode = st.radio("Mod:", ["Katı Kurallar", "Esnek Mod"], index=1)
    
    with st.expander("👨‍⚕️ Doktor Listesi"):
        new_doc = st.text_input("Ekle")
        if st.button("Listeye Ekle") and new_doc:
            if new_doc not in st.session_state.doctors:
                st.session_state.doctors.append(new_doc)
                st.rerun()
        rem_doc = st.selectbox("Sil", [""] + st.session_state.doctors)
        if st.button("Sil") and rem_doc:
            st.session_state.doctors.remove(rem_doc)
            st.rerun()
            
    with st.expander("💾 Yedekleme"):
        if st.button("Yedek İndir"):
            d_out = {"doctors": st.session_state.doctors, "db": {str(k): v for k, v in st.session_state.db.items()}, "current_year": st.session_state.year, "current_month": st.session_state.month}
            st.download_button("JSON İndir", json.dumps(d_out, default=str), "yedek.json")
        upl = st.file_uploader("Yedek Yükle", type=['json'])
        if upl:
            try:
                data = json.load(upl)
                st.session_state.doctors = data.get('doctors', st.session_state.doctors)
                st.rerun()
            except: pass

# --- DASHBOARD ---
st.markdown(f"### 🗓️ {calendar.month_name[st.session_state.month]} {st.session_state.year}")
t1, t2, t3, t4 = st.tabs(["📋 GÜNLÜK İHTİYAÇ", "🎯 KOTALAR", "🔒 KISITLAR", "🚀 SONUÇ"])

# TAB 1: GÜNLÜK İHTİYAÇ
with t1:
    st.markdown('<div class="css-card">', unsafe_allow_html=True)
    
    # 1. Varsayılanlar
    for d in range(1, num_days+1):
        if d not in st.session_state.daily_needs_24h: st.session_state.daily_needs_24h[d] = 1
        if d not in st.session_state.daily_needs_16h: st.session_state.daily_needs_16h[d] = 1

    # 2. Şablon İndirme ve Yükleme Alanı
    col_a, col_b = st.columns([1, 2])
    with col_a:
        daily_template = []
        for d in range(1, num_days + 1): daily_template.append({"Gün": d, "24h İhtiyaç": 1, "16h İhtiyaç": 1})
        df_daily_temp = pd.DataFrame(daily_template)
        buf_daily = io.BytesIO()
        with pd.ExcelWriter(buf_daily, engine='xlsxwriter') as writer: df_daily_temp.to_excel(writer, index=False)
        st.download_button("📥 Excel Şablonu", buf_daily.getvalue(), "ihtiyac_sablonu.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

    with col_b:
        # FORM KULLANMIYORUZ - DOĞRUDAN ETKİLEŞİM
        up_daily = st.file_uploader("Excel Dosyası Yükle", type=["xlsx"], key="daily_upl")
        if up_daily:
            if st.button("📂 İhtiyaçları Dosyadan Güncelle", type="primary"):
                try:
                    df_d = pd.read_excel(up_daily, engine='openpyxl')
                    # Sütunları temizle
                    df_d.columns = [str(c).strip() for c in df_d.columns]
                    
                    # Beklenen sütunlar var mı kontrol et
                    if "Gün" in df_d.columns and "24h İhtiyaç" in df_d.columns:
                        for idx, row in df_d.iterrows():
                            try:
                                d_val = int(row["Gün"])
                                if 1 <= d_val <= num_days:
                                    st.session_state.daily_needs_24h[d_val] = int(row["24h İhtiyaç"])
                                    if "16h İhtiyaç" in row:
                                        st.session_state.daily_needs_16h[d_val] = int(row["16h İhtiyaç"])
                            except: pass
                        st.success("✅ Veriler yüklendi! Tablo güncelleniyor...")
                        st.session_state.editor_key += 1
                        st.rerun()
                    else:
                        st.error(f"⚠️ Sütunlar bulunamadı! Beklenen: 'Gün', '24h İhtiyaç'. Bulunan: {list(df_d.columns)}")
                except Exception as e:
                    st.error(f"Hata: {e}")

    # 3. Tablo (Manuel Düzenleme)
    d_data = [{"Gün": d, "Tarih": f"{d}", "24h": st.session_state.daily_needs_24h.get(d, 1), "16h": st.session_state.daily_needs_16h.get(d, 1)} for d in range(1, num_days+1)]
    
    with st.form("needs_manual"):
        edf = st.data_editor(pd.DataFrame(d_data), key=f"ed_need_{st.session_state.editor_key}", use_container_width=True, hide_index=True, column_config={"Gün": st.column_config.NumberColumn(disabled=True)})
        if st.form_submit_button("💾 Tabloyu Kaydet"):
            for i, r in edf.iterrows():
                st.session_state.daily_needs_24h[r["Gün"]] = int(r["24h"])
                st.session_state.daily_needs_16h[r["Gün"]] = int(r["16h"])
            st.success("Kaydedildi")
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# TAB 2: KOTALAR
with t2:
    st.markdown('<div class="css-card">', unsafe_allow_html=True)
    
    col_a, col_b = st.columns([1, 2])
    with col_a:
        sample_data = [{"Dr": d, "Max 24h": 0, "Max 16h": 0} for d in st.session_state.doctors]
        sample_df = pd.DataFrame(sample_data)
        buf_quota = io.BytesIO()
        with pd.ExcelWriter(buf_quota, engine='xlsxwriter') as writer: sample_df.to_excel(writer, index=False)
        st.download_button("📥 Excel Şablonu", buf_quota.getvalue(), "kota_sablonu.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
    
    with col_b:
        # FORM KULLANMIYORUZ - DOĞRUDAN ETKİLEŞİM
        up_quota = st.file_uploader("Excel Dosyası Yükle", type=["xlsx"], key="quota_upl")
        if up_quota:
            if st.button("📂 Kotaları Dosyadan Güncelle", type="primary"):
                try:
                    df_up = pd.read_excel(up_quota, engine='openpyxl')
                    df_up.columns = [str(c).strip() for c in df_up.columns]
                    
                    if "Dr" in df_up.columns and "Max 24h" in df_up.columns:
                        count = 0
                        # Doktor isimlerini normalize ederek eşleştir
                        doc_map = {normalize_string(d): d for d in st.session_state.doctors}
                        
                        for idx, row in df_up.iterrows():
                            d_excel = normalize_string(row["Dr"])
                            if d_excel in doc_map:
                                real_name = doc_map[d_excel]
                                st.session_state.quotas_24h[real_name] = int(row["Max 24h"])
                                if "Max 16h" in row:
                                    st.session_state.quotas_16h[real_name] = int(row["Max 16h"])
                                count += 1
                        if count > 0:
                            st.success(f"✅ {count} doktor güncellendi!")
                            st.session_state.editor_key += 1
                            st.rerun()
                        else:
                            st.warning("⚠️ Doktor isimleri sistemdekilerle eşleşmedi. Harf hatası olabilir.")
                    else:
                        st.error(f"⚠️ Gerekli sütunlar yok. 'Dr', 'Max 24h' gerekli. Dosyada: {list(df_up.columns)}")
                except Exception as e:
                    st.error(f"Hata: {e}")

    # Tablo
    q_data = [{"Dr": d, "Max 24h": st.session_state.quotas_24h.get(d, 0), "Max 16h": st.session_state.quotas_16h.get(d, 0)} for d in st.session_state.doctors]
    with st.form("quotas_manual"):
        qdf = st.data_editor(pd.DataFrame(q_data), key=f"ed_quota_{st.session_state.editor_key}", use_container_width=True, hide_index=True, column_config={"Dr": st.column_config.TextColumn(disabled=True)})
        if st.form_submit_button("💾 Tabloyu Kaydet"):
            for i, r in qdf.iterrows():
                st.session_state.quotas_24h[r["Dr"]] = int(r["Max 24h"])
                st.session_state.quotas_16h[r["Dr"]] = int(r["Max 16h"])
            st.success("Kaydedildi")
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# TAB 3: KISITLAR
with t3:
    st.markdown('<div class="css-card">', unsafe_allow_html=True)
    st.write(f"Hücrelere: '24', '16' veya 'X' (izin) yazın.")
    
    col_a, col_b = st.columns([1, 2])
    with col_a:
        days_header = [str(d) for d in range(1, num_days + 1)]
        template_data = []
        for d in st.session_state.doctors:
            row = {"Dr": d}
            for day in days_header: row[day] = "" 
            template_data.append(row)
        df_temp = pd.DataFrame(template_data)
        buf_const = io.BytesIO()
        with pd.ExcelWriter(buf_const, engine='xlsxwriter') as writer: df_temp.to_excel(writer, index=False)
        st.download_button("📥 Excel Şablonu", buf_const.getvalue(), "kisit_sablonu.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        
    with col_b:
        # FORM KULLANMIYORUZ - DOĞRUDAN ETKİLEŞİM
        up_const = st.file_uploader("Excel Dosyası Yükle", type=["xlsx"], key="const_upl")
        if up_const:
            if st.button("📂 Kısıtları Dosyadan Güncelle", type="primary"):
                try:
                    df_c = pd.read_excel(up_const, engine='openpyxl')
                    df_c.columns = [str(c).strip() for c in df_c.columns]
                    
                    if "Dr" in df_c.columns:
                        doc_map = {normalize_string(d): d for d in st.session_state.doctors}
                        processed_count = 0
                        
                        for idx, row in df_c.iterrows():
                            d_excel = normalize_string(row["Dr"])
                            if d_excel in doc_map:
                                doc_name = doc_map[d_excel]
                                for day in range(1, num_days + 1):
                                    if str(day) in df_c.columns:
                                        raw_val = row[str(day)]
                                        if pd.notna(raw_val):
                                            val = str(raw_val).strip().upper()
                                            if val in ["24", "16", "X"]:
                                                st.session_state.manual_constraints[f"{doc_name}_{day}"] = val
                                                # Otomatik izin kuralı
                                                if val == "24":
                                                    for off in range(1, rest_days_24h+1):
                                                        if day+off <= num_days: 
                                                            st.session_state.manual_constraints[f"{doc_name}_{day+off}"] = "X"
                                processed_count += 1
                        st.success(f"✅ {processed_count} doktorun kısıtları işlendi!")
                        st.session_state.editor_key += 1
                        st.rerun()
                    else:
                        st.error(f"⚠️ 'Dr' sütunu bulunamadı. Bulunanlar: {list(df_c.columns)}")
                except Exception as e:
                    st.error(f"Hata: {e}")

    # Tablo
    c_data = []
    for doc in st.session_state.doctors:
        r = {"Doktor": doc}
        for d in range(1, num_days+1): r[str(d)] = st.session_state.manual_constraints.get(f"{doc}_{d}", "")
        c_data.append(r)
    
    col_cfg = {"Doktor": st.column_config.TextColumn(disabled=True)}
    for d in range(1, num_days+1):
        col_cfg[str(d)] = st.column_config.SelectboxColumn(label=str(d), options=["", "24", "16", "X"], width="small")
    
    with st.form("const_manual"):
        ed_cons = st.data_editor(pd.DataFrame(c_data), column_config=col_cfg, hide_index=True, use_container_width=True, key=f"ed_const_{st.session_state.editor_key}")
        if st.form_submit_button("💾 Tabloyu Kaydet"):
            for i, r in ed_cons.iterrows():
                doc = r["Doktor"]
                for d in range(1, num_days+1):
                    val = str(r[str(d)])
                    k = f"{doc}_{d}"
                    if val in ["24", "16", "X"]:
                        st.session_state.manual_constraints[k] = val
                    else:
                        if k in st.session_state.manual_constraints: del st.session_state.manual_constraints[k]
            st.success("Kaydedildi")
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# TAB 4: HESAPLAMA
with t4:
    st.markdown('<div class="css-card">', unsafe_allow_html=True)
    if st.button("🚀 Nöbetleri Dağıt (AI)", type="primary", use_container_width=True):
        with st.spinner("Yapay Zeka Hesaplanıyor..."):
            model = cp_model.CpModel()
            docs = st.session_state.doctors
            days = range(1, num_days+1)
            x24, x16 = {}, {}

            # Değişkenler
            for d in docs:
                for t in days:
                    x24[(d,t)] = model.NewBoolVar(f'x24_{d}_{t}')
                    x16[(d,t)] = model.NewBoolVar(f'x16_{d}_{t}')
                    model.Add(x24[(d,t)] + x16[(d,t)] <= 1)

            # Günlük İhtiyaç
            for t in days:
                need24 = st.session_state.daily_needs_24h.get(t, 1)
                need16 = st.session_state.daily_needs_16h.get(t, 1)
                model.Add(sum(x24[(d,t)] for d in docs) == need24)
                model.Add(sum(x16[(d,t)] for d in docs) == need16)

            # Peş peşe nöbet yasağı ve Dinlenme
            for d in docs:
                for t in range(1, num_days):
                    model.Add(x24[(d,t)] + x16[(d,t)] + x24[(d,t+1)] + x16[(d,t+1)] <= 1)
                
                win = rest_days_24h + 1
                for i in range(len(days) - win + 1):
                    wd = [days[j] for j in range(i, i+win)]
                    model.Add(sum(x24[(d,k)] for k in wd) <= 1)

            # Manuel Kısıtlar
            for d in docs:
                for t in days:
                    c = st.session_state.manual_constraints.get(f"{d}_{t}", "")
                    if c == "24": model.Add(x24[(d,t)] == 1)
                    elif c == "16": model.Add(x16[(d,t)] == 1)
                    elif c == "X": 
                        model.Add(x24[(d,t)] == 0)
                        model.Add(x16[(d,t)] == 0)

            # Hedefler (Sapma Minimize Et)
            deviations = []
            for d in docs:
                tot24 = sum(x24[(d,t)] for t in days)
                tgt24 = st.session_state.quotas_24h.get(d, 0)
                
                if "Katı" in solver_mode: model.Add(tot24 <= tgt24)
                else:
                    diff24 = model.NewIntVar(0, 31, f'd24_{d}')
                    # Mutlak sapma hilesi
                    model.Add(diff24 >= tot24 - tgt24)
                    model.Add(diff24 >= tgt24 - tot24)
                    deviations.append(diff24)
                
                tot16 = sum(x16[(d,t)] for t in days)
                tgt16 = st.session_state.quotas_16h.get(d, 0)
                if "Katı" in solver_mode: model.Add(tot16 <= tgt16)
                else:
                    diff16 = model.NewIntVar(0, 31, f'd16_{d}')
                    model.Add(diff16 >= tot16 - tgt16)
                    model.Add(diff16 >= tgt16 - tot16)
                    deviations.append(diff16)

            if "Esnek" in solver_mode: model.Minimize(sum(deviations))

            solver = cp_model.CpSolver()
            status = solver.Solve(model)

            if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
                st.success("✅ Çizelge Başarıyla Oluşturuldu!")
                
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
                
                df_st = pd.DataFrame([{
                    "Doktor": d,
                    "24h (Hedef)": st.session_state.quotas_24h.get(d,0), "24h (Gerçek)": stats[d]["24h"],
                    "16h (Hedef)": st.session_state.quotas_16h.get(d,0), "16h (Gerçek)": stats[d]["16h"]
                } for d in docs])
                
                st.dataframe(df_st, use_container_width=True)
                st.dataframe(pd.DataFrame(res_mx).style.applymap(lambda v: 'background-color: #ef4444; color: white' if v=='24h' else ('background-color: #22c55e; color: white' if v=='16h' else '')), use_container_width=True)
                
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
                    pd.DataFrame(res_lst).to_excel(writer, sheet_name='Liste', index=False)
                    pd.DataFrame(res_mx).to_excel(writer, sheet_name='Cizelge', index=False)
                    df_st.to_excel(writer, sheet_name='Istatistik', index=False)
                st.download_button("📥 Excel Olarak İndir", buf.getvalue(), "nobet_sonuc.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")
            else:
                st.error("Çözüm Bulunamadı! Kurallar çok sıkı olabilir. 'Esnek Mod' deneyin veya kotaları artırın.")
    st.markdown('</div>', unsafe_allow_html=True)
