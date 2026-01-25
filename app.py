import streamlit as st
import pandas as pd
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
    
    /* Kart Yapısı */
    .css-card { 
        background-color: #1e293b !important; 
        padding: 25px; 
        border-radius: 12px; 
        border: 1px solid #334155;
        margin-bottom: 25px; 
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
    }
    .stButton>button:hover { 
        background-color: #2563eb !important; 
        transform: translateY(-2px);
    }
    
    /* Tablo Alanlarını Genişletme */
    div[data-testid="stDataEditor"] {
        background-color: #1e293b; 
        border-radius: 10px;
        border: 1px solid #334155;
        min-height: 500px !important; 
    }
    div[data-testid="stDataEditor"] * {
        color: #e2e8f0 !important;
        background-color: #1e293b !important;
        font-size: 1.05rem !important; 
    }
    
    .stTabs [data-baseweb="tab-list"] { gap: 10px; background-color: transparent; }
    .stTabs [data-baseweb="tab"] { background-color: #1e293b; border-radius: 5px; color: #94a3b8; border: 1px solid #334155; }
    .stTabs [aria-selected="true"] { background-color: #3b82f6 !important; color: white !important; border: none; }
    header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# --- YARDIMCI FONKSİYONLAR ---
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
        st.session_state.quotas_24h = {k["isim"]: k["kota24"] for k in VARSAYILAN_EKIP}
        st.session_state.quotas_16h = {k["isim"]: k["kota16"] for k in VARSAYILAN_EKIP}
        st.session_state.manual_constraints = {}

# --- BAŞLANGIÇ VE KADRO AYARLARI ---
VARSAYILAN_EKIP = [
    # 1. GRUP (Sadece 24h: 8, 16h: 0)
    {"isim": "A01", "kota24": 8, "kota16": 0},
    {"isim": "A02", "kota24": 8, "kota16": 0},
    {"isim": "A03", "kota24": 8, "kota16": 0},
    {"isim": "A4",  "kota24": 8, "kota16": 0},
    {"isim": "A5",  "kota24": 8, "kota16": 0},
    {"isim": "A6",  "kota24": 8, "kota16": 0},
    {"isim": "A7",  "kota24": 8, "kota16": 0},
    {"isim": "A8",  "kota24": 8, "kota16": 0},
    {"isim": "A9",  "kota24": 8, "kota16": 0},
    {"isim": "A10", "kota24": 8, "kota16": 0},
    {"isim": "A11", "kota24": 8, "kota16": 0},
    {"isim": "A12", "kota24": 8, "kota16": 0},
    {"isim": "A13", "kota24": 8, "kota16": 0},
    {"isim": "A14", "kota24": 8, "kota16": 0},
    {"isim": "A15", "kota24": 8, "kota16": 0},
    {"isim": "A16", "kota24": 8, "kota16": 0},

    # 2. GRUP (24h: 8, 16h: 1)
    {"isim": "A17", "kota24": 8, "kota16": 1},
    {"isim": "A18", "kota24": 8, "kota16": 1},
    {"isim": "A19", "kota24": 8, "kota16": 1},
    {"isim": "A20", "kota24": 8, "kota16": 1},
    {"isim": "A21", "kota24": 8, "kota16": 1},
    
    # 3. GRUP (24h: 8, 16h: 2)
    {"isim": "A22", "kota24": 8, "kota16": 2},
    {"isim": "A23", "kota24": 8, "kota16": 2},
    {"isim": "A24", "kota24": 8, "kota16": 2},
    {"isim": "A25", "kota24": 8, "kota16": 2},
    {"isim": "A26", "kota24": 8, "kota16": 2},
    {"isim": "A27", "kota24": 8, "kota16": 2},
    {"isim": "A28", "kota24": 8, "kota16": 2},
    {"isim": "A29", "kota24": 8, "kota16": 2},
    {"isim": "A30", "kota24": 8, "kota16": 2},
    {"isim": "A31", "kota24": 8, "kota16": 2},
    {"isim": "A32", "kota24": 8, "kota16": 2},
    {"isim": "A33", "kota24": 8, "kota16": 2}
]

if 'doctors' not in st.session_state: 
    st.session_state.doctors = [kisi["isim"] for kisi in VARSAYILAN_EKIP]

if 'year' not in st.session_state: st.session_state.year = datetime.now().year
if 'month' not in st.session_state: st.session_state.month = datetime.now().month
if 'db' not in st.session_state: st.session_state.db = {}
if 'editor_key' not in st.session_state: st.session_state.editor_key = 0
if 'daily_needs_24h' not in st.session_state: st.session_state.daily_needs_24h = {}
if 'daily_needs_16h' not in st.session_state: st.session_state.daily_needs_16h = {}

if 'quotas_24h' not in st.session_state: 
    st.session_state.quotas_24h = {kisi["isim"]: kisi["kota24"] for kisi in VARSAYILAN_EKIP}
if 'quotas_16h' not in st.session_state: 
    st.session_state.quotas_16h = {kisi["isim"]: kisi["kota16"] for kisi in VARSAYILAN_EKIP}
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
    # Kullanıcıyı yönlendiriyoruz
    st.info("💡 16h nöbetini 24h'den sonraki 2. güne koymak için burayı '1' veya '2' olarak ayarlayın.")
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

    with st.expander("💾 YEDEKLEME (JSON)"):
        st.info("İsimleri, Kotaları ve Kısıtları kaydeder.")
        if st.button("Yedek İndir (JSON)"):
            save_current_month_data()
            d_out = {
                "doctors": st.session_state.doctors,
                "quotas_24h": st.session_state.quotas_24h,
                "quotas_16h": st.session_state.quotas_16h,
                "manual_constraints": st.session_state.manual_constraints,
                "db": {str(k): v for k, v in st.session_state.db.items()},
                "current_year": st.session_state.year,
                "current_month": st.session_state.month
            }
            st.download_button("📥 Dosyayı İndir", json.dumps(d_out, default=str), "nobetinator_tam_yedek.json")
        
        upl = st.file_uploader("Yedek Yükle", type=['json'])
        if upl:
            try:
                data = json.load(upl)
                st.session_state.doctors = data.get('doctors', st.session_state.doctors)
                if 'quotas_24h' in data: st.session_state.quotas_24h = data['quotas_24h']
                if 'quotas_16h' in data: st.session_state.quotas_16h = data['quotas_16h']
                if 'manual_constraints' in data: st.session_state.manual_constraints = data['manual_constraints']
                if 'db' in data: st.session_state.db = data['db']
                st.success("✅ Veriler yüklendi!")
                st.rerun()
            except Exception as e: st.error(f"Hata: {e}")

# --- DASHBOARD ---
st.markdown(f"### 🗓️ {calendar.month_name[st.session_state.month]} {st.session_state.year} Dashboard")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Toplam Gün", num_days)
c2.metric("Personel Sayısı", len(st.session_state.doctors))
c3.metric("Mod", "Esnek" if "Esnek" in solver_mode else "Katı")
c4.metric("Kısıtlar", len(st.session_state.manual_constraints))

st.write("") 

t1, t2, t3, t4 = st.tabs(["📋 GÜNLÜK İHTİYAÇ", "🎯 KOTALAR (LİMİT)", "🔒 KISITLAR (HIZLI GİRİŞ)", "🚀 SONUÇ & RAPOR"])

# TAB 1: GÜNLÜK İHTİYAÇ
with t1:
    st.markdown('<div class="css-card">', unsafe_allow_html=True)
    st.markdown("#### 📅 Günlük Nöbetçi İhtiyacı")
    for d in range(1, num_days+1):
        if d not in st.session_state.daily_needs_24h: st.session_state.daily_needs_24h[d] = 1
        if d not in st.session_state.daily_needs_16h: st.session_state.daily_needs_16h[d] = 1

    d_data = [{"Gün": d, "Tarih": f"{d} {['Pzt','Sal','Çar','Per','Cum','Cmt','Paz'][datetime(st.session_state.year, st.session_state.month, d).weekday()]}", "24h": st.session_state.daily_needs_24h.get(d, 1), "16h": st.session_state.daily_needs_16h.get(d, 1)} for d in range(1, num_days+1)]
    with st.form("needs_manual"):
        edf = st.data_editor(pd.DataFrame(d_data), height=500, key=f"need_ed_{st.session_state.editor_key}", use_container_width=True, hide_index=True, column_config={"Gün": st.column_config.NumberColumn(disabled=True), "Tarih": st.column_config.TextColumn(disabled=True)})
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
    st.markdown("#### 🎯 Doktor Nöbet Hedefleri")
    total_need_24 = sum(st.session_state.daily_needs_24h.get(d, 1) for d in range(1, num_days+1))
    total_need_16 = sum(st.session_state.daily_needs_16h.get(d, 1) for d in range(1, num_days+1))
    current_dist_24 = sum(st.session_state.quotas_24h.get(d, 0) for d in st.session_state.doctors)
    current_dist_16 = sum(st.session_state.quotas_16h.get(d, 0) for d in st.session_state.doctors)
    
    col_q1, col_q2 = st.columns(2)
    col_q1.metric("24h İhtiyaç / Dağıtılan", f"{total_need_24} / {current_dist_24}", delta=f"{current_dist_24 - total_need_24}", delta_color="off")
    col_q2.metric("16h İhtiyaç / Dağıtılan", f"{total_need_16} / {current_dist_16}", delta=f"{current_dist_16 - total_need_16}", delta_color="off")
    
    q_data = [{"Dr": d, "Max 24h": st.session_state.quotas_24h.get(d, 0), "Max 16h": st.session_state.quotas_16h.get(d, 0)} for d in st.session_state.doctors]
    with st.form("quotas_manual"):
        qdf = st.data_editor(pd.DataFrame(q_data), height=500, key=f"quota_ed_{st.session_state.editor_key}", use_container_width=True, hide_index=True, column_config={"Dr": st.column_config.TextColumn(disabled=True)})
        if st.form_submit_button("💾 Tablodan Kaydet"):
            for i, r in qdf.iterrows():
                st.session_state.quotas_24h[r["Dr"]] = int(r["Max 24h"])
                st.session_state.quotas_16h[r["Dr"]] = int(r["Max 16h"])
            st.success("Kaydedildi!")
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# TAB 3: MANUEL KISITLAR (HIZLI GİRİŞ VE GÖRSEL UYARI)
with t3:
    st.markdown('<div class="css-card">', unsafe_allow_html=True)
    
    # --- YENİ BÖLÜM: TOPLU GİRİŞ ARACI ---
    with st.expander("⚡ Hızlı & Toplu Veri Girişi (Burası Çok Hızlı!)", expanded=True):
        st.info("Tek tek uğraşma! Doktoru seç, günleri işaretle ve tek tıkla ata.")
        c_b1, c_b2, c_b3 = st.columns([1, 2, 1])
        
        with c_b1:
            bulk_doc = st.selectbox("1. Doktor Seç:", st.session_state.doctors)
            bulk_type = st.selectbox("2. Ne Atanacak?", ["🔴 24 (Nöbet)", "🟢 16 (Nöbet)", "❌ Mazeret (Boşalt)", "🗑️ Temizle (Sil)"])
        
        with c_b2:
            st.write("3. Günleri Seç:")
            # Multi-select ile günleri seçtirme
            days_labels = [f"{d}" for d in range(1, num_days+1)]
            selected_days = st.multiselect("Günler", days_labels, label_visibility="collapsed")
        
        with c_b3:
            st.write("")
            st.write("")
            if st.button("⚡ Uygula", type="primary", use_container_width=True):
                if bulk_doc and selected_days:
                    val_map = {"🔴 24 (Nöbet)": "24", "🟢 16 (Nöbet)": "16", "❌ Mazeret (Boşalt)": "X", "🗑️ Temizle (Sil)": ""}
                    val = val_map[bulk_type]
                    
                    for day_str in selected_days:
                        d = int(day_str)
                        k = f"{bulk_doc}_{d}"
                        if val:
                            st.session_state.manual_constraints[k] = val
                            # Otomatik bloklama (Sadece 24 ise) - Görsel olarak ekler
                            if val == "24":
                                for off in range(1, rest_days_24h+1):
                                    if d+off <= num_days:
                                        # Eğer orada başka bir kısıt yoksa visual block koy
                                        if f"{bulk_doc}_{d+off}" not in st.session_state.manual_constraints:
                                            st.session_state.manual_constraints[f"{bulk_doc}_{d+off}"] = "⛔"
                        else:
                            # Temizleme
                            if k in st.session_state.manual_constraints: del st.session_state.manual_constraints[k]
                    
                    st.success(f"{len(selected_days)} güne işlem uygulandı!")
                    st.session_state.editor_key += 1
                    st.rerun()

    st.markdown("---")
    st.markdown("#### 📋 Detaylı Tablo Görünümü")
    st.caption("Not: '⛔' işareti sizin dikkatinizi çekmek içindir. **AI hesaplama yaparken bu işareti görmezden gelir.** Böylece kurallar izin veriyorsa (örn: 1 gün boşluk varsa) o güne 16h nöbet yazabilir.")

    # Tablo Verisi Hazırlama
    c_data = []
    for doc in st.session_state.doctors:
        r = {"Doktor": doc}
        for d in range(1, num_days+1): 
            # Veride ne varsa onu çekiyoruz
            r[str(d)] = st.session_state.manual_constraints.get(f"{doc}_{d}", "")
        c_data.append(r)
        
    col_cfg = {"Doktor": st.column_config.TextColumn(disabled=True)}
    for d in range(1, num_days+1):
        dn = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"][datetime(st.session_state.year, st.session_state.month, d).weekday()]
        # Emoji Destekli Dropdown
        col_cfg[str(d)] = st.column_config.SelectboxColumn(
            label=f"{d}\n{dn}", 
            options=["", "24", "16", "X", "⛔"], 
            width="small"
        )
        
    with st.form("const_manual"):
        ed_cons = st.data_editor(
            pd.DataFrame(c_data), 
            height=600, 
            column_config=col_cfg, 
            hide_index=True, 
            use_container_width=True, 
            key=f"cons_ed_{st.session_state.editor_key}"
        )
        
        if st.form_submit_button("💾 Tablodan Kaydet"):
            updated = False
            for i, r in ed_cons.iterrows():
                doc = r["Doktor"]
                for d in range(1, num_days+1):
                    val = str(r[str(d)])
                    k = f"{doc}_{d}"
                    
                    # Mevcut değerden farklıysa güncelle
                    if val != st.session_state.manual_constraints.get(k, ""):
                        if val in ["24", "16", "X", "⛔"]:
                            st.session_state.manual_constraints[k] = val
                            
                            # OTOMATİK BLOKLAMA MANTIĞI (Görsel)
                            if val == "24":
                                for off in range(1, rest_days_24h+1):
                                    if d+off <= num_days: 
                                        st.session_state.manual_constraints[f"{doc}_{d+off}"] = "⛔"
                        else:
                            if k in st.session_state.manual_constraints: del st.session_state.manual_constraints[k]
                        updated = True
            
            if updated: 
                st.session_state.editor_key += 1 # Force refresh
                st.rerun()
            else: 
                st.success("Değişiklik yok.")
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
                    # Bir gün nöbet tutan ertesi gün tutamaz (Standart yorgunluk kuralı)
                    model.Add(x24[(d,t)] + x16[(d,t)] + x24[(d,t+1)] + x16[(d,t+1)] <= 1)
                
                # 24 Saatlik Nöbet Sonrası Dinlenme Kuralı (Slider'a göre)
                win = rest_days_24h + 1
                for i in range(len(days) - win + 1):
                    wd = [days[j] for j in range(i, i+win)]
                    # Bu aralıkta en fazla bir tane 24 saatlik nöbet olabilir.
                    # ÖNEMLİ: Bu kural 16 saatlik nöbetleri engellemez, sadece sık 24 nöbetini engeller.
                    model.Add(sum(x24[(d,k)] for k in wd) <= 1)

            for d in docs:
                for t in days:
                    # Constraint kontrolü (Genişletilmiş)
                    c = st.session_state.manual_constraints.get(f"{d}_{t}", "")
                    if c == "24": model.Add(x24[(d,t)] == 1)
                    elif c == "16": model.Add(x16[(d,t)] == 1)
                    elif c == "X": # X Kesinlikle Yasak
                        model.Add(x24[(d,t)] == 0)
                        model.Add(x16[(d,t)] == 0)
                    elif c == "⛔": 
                        # ÖNEMLİ DEĞİŞİKLİK: '⛔' işaretini AI görmezden geliyor.
                        # Sadece görsel uyarıdır. Matematiksel kısıt eklemiyoruz (pass).
                        pass

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
