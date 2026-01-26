import streamlit as st
import pandas as pd
from ortools.sat.python import cp_model
import json
from datetime import datetime
import calendar
import io
import xlsxwriter
import time

# -----------------------------------------------------------------------------
# 1. AYARLAR VE SAYFA YAPILANDIRMASI
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Nobetinatör Ai",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -----------------------------------------------------------------------------
# 2. PROFESYONEL CSS TASARIMI (MODERN UI)
# -----------------------------------------------------------------------------
st.markdown("""
<style>
    /* GENEL SAYFA YAPISI */
    .stApp { background-color: #0f172a; font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; }
    h1, h2, h3 { color: #f8fafc !important; font-weight: 700; }
    p, label, span, div { color: #cbd5e1; }
    [data-testid="stSidebar"] { background-color: #1e293b; border-right: 1px solid #334155; }
    
    /* KART TASARIMI */
    .css-card {
        background-color: #1e293b;
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #334155;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
        margin-bottom: 20px;
    }
    
    /* METRİK KUTULARI */
    div[data-testid="stMetric"] {
        background-color: #334155;
        border-radius: 8px;
        padding: 10px;
        border: 1px solid #475569;
    }
    div[data-testid="stMetricLabel"] > div { color: #94a3b8 !important; font-size: 0.9rem; }
    div[data-testid="stMetricValue"] > div { color: #38bdf8 !important; font-weight: 700; }
    
    /* BUTONLAR */
    .stButton>button {
        border-radius: 8px;
        font-weight: 600;
        border: none;
        transition: all 0.3s ease;
    }
    .stButton>button[kind="primary"] {
        background: linear-gradient(90deg, #3b82f6 0%, #2563eb 100%);
        box-shadow: 0 4px 10px rgba(37, 99, 235, 0.3);
    }
    .stButton>button[kind="primary"]:hover { transform: scale(1.02); }
    
    /* TABLO DÜZENİ */
    div[data-testid="stDataEditor"] {
        border: 1px solid #475569;
        border-radius: 8px;
        overflow: hidden;
    }
    
    /* SEKME (TAB) TASARIMI */
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        background-color: #1e293b;
        border: 1px solid #334155;
        border-radius: 6px;
        color: #94a3b8;
        padding: 8px 16px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #3b82f6 !important;
        color: white !important;
        border-color: #3b82f6 !important;
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 3. VERİ YÖNETİMİ VE FONKSİYONLAR
# -----------------------------------------------------------------------------
def get_storage_key(y, m): return f"{y}_{m}"

def save_current_month_data():
    if 'db' not in st.session_state: st.session_state.db = {}
    key = get_storage_key(st.session_state.year, st.session_state.month)
    st.session_state.db[key] = {
        "daily_needs_24h": st.session_state.daily_needs_24h.copy(),
        "daily_needs_16h": st.session_state.daily_needs_16h.copy(),
        "quotas_24h": st.session_state.quotas_24h.copy(),
        "quotas_16h": st.session_state.quotas_16h.copy(),
        "seniority": st.session_state.seniority.copy(),
        "manual_constraints": st.session_state.manual_constraints.copy(),
        "couples": st.session_state.couples.copy()
    }

def load_month_data(y, m):
    key = get_storage_key(y, m)
    if 'db' in st.session_state and key in st.session_state.db:
        data = st.session_state.db[key]
        st.session_state.daily_needs_24h = data["daily_needs_24h"]
        st.session_state.daily_needs_16h = data["daily_needs_16h"]
        st.session_state.quotas_24h = data["quotas_24h"]
        st.session_state.quotas_16h = data["quotas_16h"]
        st.session_state.seniority = data.get("seniority", {k["isim"]: "Orta" for k in VARSAYILAN_EKIP})
        st.session_state.manual_constraints = data["manual_constraints"]
        st.session_state.couples = data.get("couples", [])
    else:
        st.session_state.daily_needs_24h = {}
        st.session_state.daily_needs_16h = {}
        st.session_state.quotas_24h = {k["isim"]: k["kota24"] for k in VARSAYILAN_EKIP}
        st.session_state.quotas_16h = {k["isim"]: k["kota16"] for k in VARSAYILAN_EKIP}
        st.session_state.seniority = {k["isim"]: "Orta" for k in VARSAYILAN_EKIP}
        st.session_state.manual_constraints = {}
        st.session_state.couples = []

# Varsayılan Kadro
VARSAYILAN_EKIP = [
    {"isim": "A01", "kota24": 8, "kota16": 0}, {"isim": "A02", "kota24": 8, "kota16": 0},
    {"isim": "A03", "kota24": 8, "kota16": 0}, {"isim": "A4",  "kota24": 8, "kota16": 0},
    {"isim": "A5",  "kota24": 8, "kota16": 0}, {"isim": "A6",  "kota24": 8, "kota16": 0},
    {"isim": "A7",  "kota24": 8, "kota16": 0}, {"isim": "A8",  "kota24": 8, "kota16": 0},
    {"isim": "A9",  "kota24": 8, "kota16": 0}, {"isim": "A10", "kota24": 8, "kota16": 0},
    {"isim": "A11", "kota24": 8, "kota16": 0}, {"isim": "A12", "kota24": 8, "kota16": 0},
    {"isim": "A13", "kota24": 8, "kota16": 0}, {"isim": "A14", "kota24": 8, "kota16": 0},
    {"isim": "A15", "kota24": 8, "kota16": 0}, {"isim": "A16", "kota24": 8, "kota16": 0},
    {"isim": "A17", "kota24": 8, "kota16": 1}, {"isim": "A18", "kota24": 8, "kota16": 1},
    {"isim": "A19", "kota24": 8, "kota16": 1}, {"isim": "A20", "kota24": 8, "kota16": 1},
    {"isim": "A21", "kota24": 8, "kota16": 1}, {"isim": "A22", "kota24": 8, "kota16": 2},
    {"isim": "A23", "kota24": 8, "kota16": 2}, {"isim": "A24", "kota24": 8, "kota16": 2},
    {"isim": "A25", "kota24": 8, "kota16": 2}, {"isim": "A26", "kota24": 8, "kota16": 2},
    {"isim": "A27", "kota24": 8, "kota16": 2}, {"isim": "A28", "kota24": 8, "kota16": 2},
    {"isim": "A29", "kota24": 8, "kota16": 2}, {"isim": "A30", "kota24": 8, "kota16": 2},
    {"isim": "A31", "kota24": 8, "kota16": 2}, {"isim": "A32", "kota24": 8, "kota16": 2},
    {"isim": "A33", "kota24": 8, "kota16": 2}
]

# Session State Başlatma
if 'doctors' not in st.session_state: st.session_state.doctors = [k["isim"] for k in VARSAYILAN_EKIP]
if 'year' not in st.session_state: st.session_state.year = datetime.now().year
if 'month' not in st.session_state: st.session_state.month = datetime.now().month
if 'db' not in st.session_state: st.session_state.db = {}
if 'editor_key' not in st.session_state: st.session_state.editor_key = 0
if 'daily_needs_24h' not in st.session_state: st.session_state.daily_needs_24h = {}
if 'daily_needs_16h' not in st.session_state: st.session_state.daily_needs_16h = {}
if 'quotas_24h' not in st.session_state: st.session_state.quotas_24h = {k["isim"]: k["kota24"] for k in VARSAYILAN_EKIP}
if 'quotas_16h' not in st.session_state: st.session_state.quotas_16h = {k["isim"]: k["kota16"] for k in VARSAYILAN_EKIP}
if 'seniority' not in st.session_state: st.session_state.seniority = {k["isim"]: "Orta" for k in VARSAYILAN_EKIP}
if 'manual_constraints' not in st.session_state: st.session_state.manual_constraints = {}
if 'couples' not in st.session_state: st.session_state.couples = []

# -----------------------------------------------------------------------------
# 4. YAN MENÜ (SIDEBAR) - KONTROL PANELİ
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## 🏥 Nobetinatör Ai")
    st.markdown("---")
    
    # Tarih Seçimi
    c1, c2 = st.columns(2)
    with c1: selected_year = st.number_input("Yıl", 2024, 2030, st.session_state.year)
    with c2: selected_month = st.selectbox("Ay", range(1, 13), index=st.session_state.month-1, format_func=lambda x: calendar.month_name[x])
    
    if selected_year != st.session_state.year or selected_month != st.session_state.month:
        save_current_month_data()
        st.session_state.year = selected_year
        st.session_state.month = selected_month
        load_month_data(selected_year, selected_month)
        st.rerun()

    num_days = calendar.monthrange(selected_year, selected_month)[1]
    
    st.markdown("---")
    st.markdown("### ⚙️ Algoritma Ayarları")
    rest_days_24h = st.slider("24s Sonrası İzin (Gün)", 1, 5, 2, help="Nöbetçinin 24 saat nöbetten sonra kaç gün boş kalacağını belirler.")
    calc_time = st.slider("Düşünme Süresi (sn)", 10, 60, 30, help="AI'nın çözümü araması için maksimum süre.")
    
    st.markdown("---")
    
    # EŞLEŞTİRME MODÜLÜ (ESNEK)
    with st.expander("❤️ Evli Çiftler / Partnerler", expanded=True):
        st.caption("Seçilen kişiler **mümkün olduğunca aynı gün** nöbet tutar. Eğer nöbet sayıları farklıysa, ortak olanları birlikte tutarlar, kalanları ayrı tutarlar.")
        
        c_p1 = st.selectbox("1. Kişi", ["Seçiniz"] + st.session_state.doctors, key="p1")
        c_p2 = st.selectbox("2. Kişi", ["Seçiniz"] + st.session_state.doctors, key="p2")
        
        if st.button("Çift Ekle"):
            if c_p1 != "Seçiniz" and c_p2 != "Seçiniz" and c_p1 != c_p2:
                pair = sorted([c_p1, c_p2])
                if pair not in st.session_state.couples:
                    st.session_state.couples.append(pair)
                    st.success(f"{c_p1} & {c_p2} eklendi.")
                    time.sleep(1)
                    st.rerun()
            else:
                st.error("Geçersiz seçim.")

        if st.session_state.couples:
            st.write("📋 **Tanımlı Çiftler:**")
            for i, (d1, d2) in enumerate(st.session_state.couples):
                col_del1, col_del2 = st.columns([4, 1])
                col_del1.text(f"{d1} ❤️ {d2}")
                if col_del2.button("Sil", key=f"del_c_{i}"):
                    st.session_state.couples.pop(i)
                    st.rerun()

    with st.expander("👨‍⚕️ Personel İşlemleri"):
        new_doc = st.text_input("Yeni Doktor Adı")
        if st.button("Ekle") and new_doc:
            if new_doc not in st.session_state.doctors:
                st.session_state.doctors.append(new_doc)
                st.session_state.seniority[new_doc] = "Orta"
                st.rerun()
        
        rem_doc = st.selectbox("Doktor Sil", [""] + st.session_state.doctors)
        if st.button("Sil") and rem_doc:
            st.session_state.doctors.remove(rem_doc)
            st.rerun()
            
    with st.expander("💾 Veri Yedekleme"):
        if st.button("Yedeği İndir (JSON)"):
            save_current_month_data()
            d_out = {
                "doctors": st.session_state.doctors,
                "quotas_24h": st.session_state.quotas_24h,
                "quotas_16h": st.session_state.quotas_16h,
                "seniority": st.session_state.seniority,
                "manual_constraints": st.session_state.manual_constraints,
                "couples": st.session_state.couples,
                "db": {str(k): v for k, v in st.session_state.db.items()},
                "year": st.session_state.year, "month": st.session_state.month
            }
            st.download_button("📥 İndir", json.dumps(d_out, default=str), f"yedek_{st.session_state.year}_{st.session_state.month}.json")

# -----------------------------------------------------------------------------
# 5. ANA EKRAN (DASHBOARD)
# -----------------------------------------------------------------------------
st.title(f"🗓️ {calendar.month_name[st.session_state.month]} {st.session_state.year} Planlama Paneli")

# Üst Bilgi Kartları
m1, m2, m3, m4 = st.columns(4)
m1.metric("Toplam Gün", num_days, "Takvim")
m2.metric("Aktif Personel", len(st.session_state.doctors), "Doktor")
m3.metric("Kısıt Sayısı", len(st.session_state.manual_constraints), "Özel İstek")
m4.metric("Evli Çiftler", len(st.session_state.couples), "Senkronize")

st.write("") 

# Sekme Yapısı
tab_needs, tab_quotas, tab_const, tab_run = st.tabs([
    "📅 1. Günlük İhtiyaç", 
    "🎯 2. Kota & Kıdem", 
    "⛔ 3. İzin & İstekler", 
    "🚀 4. Oluştur & Sonuç"
])

# --- TAB 1: GÜNLÜK İHTİYAÇ ---
with tab_needs:
    st.markdown('<div class="css-card">', unsafe_allow_html=True)
    st.markdown("#### 🏥 Günlük Nöbetçi Sayısı Belirleme")
    
    for d in range(1, num_days+1):
        if d not in st.session_state.daily_needs_24h: st.session_state.daily_needs_24h[d] = 1
        if d not in st.session_state.daily_needs_16h: st.session_state.daily_needs_16h[d] = 1
    
    data_needs = []
    for d in range(1, num_days+1):
        dt = datetime(st.session_state.year, st.session_state.month, d)
        day_name = ['Pzt','Sal','Çar','Per','Cum','Cmt','Paz'][dt.weekday()]
        data_needs.append({
            "Gün No": d,
            "Tarih": f"{d} {calendar.month_name[st.session_state.month]} ({day_name})",
            "🔴 24 Saat İhtiyacı": st.session_state.daily_needs_24h.get(d, 1),
            "🟢 16 Saat İhtiyacı": st.session_state.daily_needs_16h.get(d, 1)
        })
    
    df_needs = pd.DataFrame(data_needs)
    
    with st.form("form_needs"):
        edited_needs = st.data_editor(
            df_needs, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "Gün No": st.column_config.NumberColumn(disabled=True),
                "Tarih": st.column_config.TextColumn(disabled=True),
                "🔴 24 Saat İhtiyacı": st.column_config.NumberColumn(min_value=0, max_value=10, step=1),
                "🟢 16 Saat İhtiyacı": st.column_config.NumberColumn(min_value=0, max_value=10, step=1)
            },
            height=800, 
            key=f"ed_needs_{st.session_state.editor_key}"
        )
        if st.form_submit_button("💾 İhtiyaçları Kaydet", type="primary"):
            for _, r in edited_needs.iterrows():
                d = r["Gün No"]
                st.session_state.daily_needs_24h[d] = r["🔴 24 Saat İhtiyacı"]
                st.session_state.daily_needs_16h[d] = r["🟢 16 Saat İhtiyacı"]
            st.success("Günlük ihtiyaçlar güncellendi!")
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# --- TAB 2: KOTA & KIDEM ---
with tab_quotas:
    st.markdown('<div class="css-card">', unsafe_allow_html=True)
    st.markdown("#### 🎯 Hedef Kotalar ve Kıdem Ayarları")
    
    tot_req_24 = sum(st.session_state.daily_needs_24h.values())
    tot_dist_24 = sum(st.session_state.quotas_24h.get(d, 0) for d in st.session_state.doctors)
    tot_req_16 = sum(st.session_state.daily_needs_16h.values())
    tot_dist_16 = sum(st.session_state.quotas_16h.get(d, 0) for d in st.session_state.doctors)
    
    col_k1, col_k2 = st.columns(2)
    with col_k1:
        st.metric("🔴 24h Dengesi (İhtiyaç / Kapasite)", f"{tot_req_24} / {tot_dist_24}", delta=(tot_dist_24 - tot_req_24))
    with col_k2:
        st.metric("🟢 16h Dengesi (İhtiyaç / Kapasite)", f"{tot_req_16} / {tot_dist_16}", delta=(tot_dist_16 - tot_req_16))
    
    st.info("💡 **İpucu:** Kotaları değiştirmek için sayıların üzerine çift tıklayıp yazabilirsiniz.")
    
    data_quota = []
    for doc in st.session_state.doctors:
        data_quota.append({
            "Doktor": doc,
            "Kıdem": st.session_state.seniority.get(doc, "Orta"),
            "🔴 Hedef 24h": st.session_state.quotas_24h.get(doc, 0),
            "🟢 Hedef 16h": st.session_state.quotas_16h.get(doc, 0)
        })
    
    with st.form("form_quotas"):
        edited_quotas = st.data_editor(
            pd.DataFrame(data_quota),
            use_container_width=True,
            hide_index=True,
            key=f"ed_quota_{st.session_state.editor_key}",
            height=1000,
            column_config={
                "Doktor": st.column_config.TextColumn(disabled=True),
                "Kıdem": st.column_config.SelectboxColumn(options=["Kıdemli", "Orta", "Çömez"], required=True),
                "🔴 Hedef 24h": st.column_config.NumberColumn("🔴 Hedef 24h", min_value=0, max_value=31, step=1, format="%d", required=True),
                "🟢 Hedef 16h": st.column_config.NumberColumn("🟢 Hedef 16h", min_value=0, max_value=31, step=1, format="%d", required=True)
            }
        )
        if st.form_submit_button("💾 Kotaları ve Kıdemi Kaydet", type="primary"):
            for _, r in edited_quotas.iterrows():
                d = r["Doktor"]
                st.session_state.quotas_24h[d] = int(r["🔴 Hedef 24h"])
                st.session_state.quotas_16h[d] = int(r["🟢 Hedef 16h"])
                st.session_state.seniority[d] = r["Kıdem"]
            st.success("Kotalar ve kıdemler başarıyla kaydedildi!")
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# --- TAB 3: KISITLAR ---
with tab_const:
    st.markdown('<div class="css-card">', unsafe_allow_html=True)
    st.markdown("#### ⚡ Hızlı Veri Girişi (İzinler ve Sabit Nöbetler)")
    
    c_bulk1, c_bulk2, c_bulk3 = st.columns([1.5, 3, 1])
    with c_bulk1:
        b_doc = st.selectbox("Doktor Seç", st.session_state.doctors)
        b_type = st.selectbox("İşlem Tipi", ["❌ İzinli (Nöbet Yok)", "🔴 24 Saat Nöbet", "🟢 16 Saat Nöbet", "🗑️ Temizle"])
    
    with c_bulk2:
        st.write("Günleri Seçin:")
        days_opts = [str(i) for i in range(1, num_days+1)]
        b_days = st.multiselect("Günler", days_opts, label_visibility="collapsed")
    
    with c_bulk3:
        st.write("")
        st.write("")
        if st.button("Uygula ⚡", type="primary", use_container_width=True):
            if b_days:
                val_map = {"❌ İzinli (Nöbet Yok)": "X", "🔴 24 Saat Nöbet": "24", "🟢 16 Saat Nöbet": "16", "🗑️ Temizle": ""}
                val = val_map[b_type]
                for d_str in b_days:
                    d = int(d_str)
                    key = f"{b_doc}_{d}"
                    if val:
                        st.session_state.manual_constraints[key] = val
                        if val == "24":
                            for off in range(1, rest_days_24h+1):
                                if d+off <= num_days: st.session_state.manual_constraints[f"{b_doc}_{d+off}"] = "⛔"
                    else:
                        if key in st.session_state.manual_constraints: del st.session_state.manual_constraints[key]
                st.success("İşlem Tamam!")
                st.session_state.editor_key += 1
                st.rerun()

    st.markdown("---")
    
    with st.expander("📋 Detaylı Kısıt Tablosunu Göster"):
        grid_data = []
        for doc in st.session_state.doctors:
            row = {"Doktor": doc}
            for d in range(1, num_days+1):
                row[str(d)] = st.session_state.manual_constraints.get(f"{doc}_{d}", "")
            grid_data.append(row)
        
        cfg = {"Doktor": st.column_config.TextColumn(disabled=True)}
        for d in range(1, num_days+1):
            cfg[str(d)] = st.column_config.SelectboxColumn(width="small", options=["", "24", "16", "X", "⛔"])
            
        with st.form("manual_grid"):
            ed_grid = st.data_editor(pd.DataFrame(grid_data), column_config=cfg, hide_index=True, key=f"grid_{st.session_state.editor_key}")
            if st.form_submit_button("Tabloyu Kaydet"):
                for _, r in ed_grid.iterrows():
                    dc = r["Doktor"]
                    for d in range(1, num_days+1):
                        v = r[str(d)]
                        k = f"{dc}_{d}"
                        if v: st.session_state.manual_constraints[k] = v
                        elif k in st.session_state.manual_constraints: del st.session_state.manual_constraints[k]
                st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# --- TAB 4: HESAPLAMA ---
with tab_run:
    st.markdown('<div class="css-card">', unsafe_allow_html=True)
    st.markdown("#### 🚀 Nobetinatör Ai Motoru")
    
    col_act1, col_act2 = st.columns([3, 1])
    with col_act1:
        st.info("Kıdem dengesi, kotalar, eş durumları ve homojen dağılım dikkate alınarak program oluşturulacak.")
    with col_act2:
        run_btn = st.button("Çizelgeyi Oluştur", type="primary", use_container_width=True)
        
    if run_btn:
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        status_text.text("Veriler hazırlanıyor...")
        progress_bar.progress(10)
        time.sleep(0.5)
        
        # --- OR-TOOLS MODELİ ---
        model = cp_model.CpModel()
        docs = st.session_state.doctors
        days = range(1, num_days+1)
        x24, x16 = {}, {}
        
        seniors = [d for d in docs if st.session_state.seniority.get(d) == "Kıdemli"]
        mids = [d for d in docs if st.session_state.seniority.get(d) == "Orta"]
        juniors = [d for d in docs if st.session_state.seniority.get(d) == "Çömez"]
        
        status_text.text("Değişkenler oluşturuluyor...")
        progress_bar.progress(20)

        # Değişkenler
        for d in docs:
            for t in days:
                x24[(d,t)] = model.NewBoolVar(f'x24_{d}_{t}')
                x16[(d,t)] = model.NewBoolVar(f'x16_{d}_{t}')
                model.Add(x24[(d,t)] + x16[(d,t)] <= 1)

        # İhtiyaçlar
        for t in days:
            model.Add(sum(x24[(d,t)] for d in docs) == st.session_state.daily_needs_24h.get(t, 1))
            model.Add(sum(x16[(d,t)] for d in docs) == st.session_state.daily_needs_16h.get(t, 1))
            
        # Yasaklar & Dinlenme
        for d in docs:
            # Peş peşe gelmeme (24h/16h fark etmez, ertesi gün boş)
            for t in range(1, num_days):
                model.Add(x24[(d,t)] + x16[(d,t)] + x24[(d,t+1)] + x16[(d,t+1)] <= 1)
            
            # 24h sonrası izin (rest_days_24h kadar gün)
            win = rest_days_24h + 1
            for i in range(len(days) - win + 1):
                wd = [days[j] for j in range(i, i+win)]
                model.Add(sum(x24[(d,k)] for k in wd) <= 1)
                
            # Manuel Kısıtlar
            for t in days:
                c = st.session_state.manual_constraints.get(f"{d}_{t}", "")
                if c == "24": model.Add(x24[(d,t)] == 1)
                elif c == "16": model.Add(x16[(d,t)] == 1)
                elif c == "X" or c == "⛔": 
                    model.Add(x24[(d,t)] == 0)
                    model.Add(x16[(d,t)] == 0)

        status_text.text("Evlilik ve Sosyal kurallar işleniyor...")
        progress_bar.progress(40)
        
        # --- ÖZEL MODÜL: EVLİ ÇİFTLER (ESNEK) ---
        penalties = []
        
        for (d1, d2) in st.session_state.couples:
            if d1 in docs and d2 in docs:
                for t in days:
                    is_working_1 = model.NewBoolVar(f'w_{d1}_{t}')
                    is_working_2 = model.NewBoolVar(f'w_{d2}_{t}')
                    model.Add(x24[(d1,t)] + x16[(d1,t)] == is_working_1)
                    model.Add(x24[(d2,t)] + x16[(d2,t)] == is_working_2)
                    
                    # Beraber çalışma durumu (AND)
                    both_working = model.NewBoolVar(f'both_{d1}_{d2}_{t}')
                    model.AddBoolAnd([is_working_1, is_working_2]).OnlyEnforceIf(both_working)
                    model.AddBoolOr([is_working_1.Not(), is_working_2.Not()]).OnlyEnforceIf(both_working.Not())
                    
                    # Ceza Puanı: (w1 + w2 - 2*both) -> 0 ise sorun yok (0-0 veya 1-1), 1 ise sorun var (biri var biri yok)
                    # Yani "Birlikte Değillerse" ceza yaz.
                    # Bu sayede AI, mümkün olan her gün onları birleştirmeye çalışır.
                    # Birleşemedikleri (kota farkı yüzünden) günler için ceza minimumda kalır.
                    
                    mismatch_cost = model.NewIntVar(0, 1, f'mm_{d1}_{d2}_{t}')
                    # mismatch = w1 + w2 - 2*both
                    model.Add(mismatch_cost == is_working_1 + is_working_2 - 2 * both_working)
                    penalties.append(mismatch_cost * 100) # Önemli bir kural

        # KOTALAR (Soft Constraints)
        for d in docs:
            # 24h Kota Sapması
            t24 = sum(x24[(d,t)] for t in days)
            goal24 = st.session_state.quotas_24h.get(d, 0)
            diff24 = model.NewIntVar(0, 31, f'd24_{d}')
            model.Add(diff24 >= t24 - goal24)
            model.Add(diff24 >= goal24 - t24)
            penalties.append(diff24 * 500) # Kotaya uymak en önemlisi
            
            # 16h Kota Sapması
            t16 = sum(x16[(d,t)] for t in days)
            goal16 = st.session_state.quotas_16h.get(d, 0)
            diff16 = model.NewIntVar(0, 31, f'd16_{d}')
            model.Add(diff16 >= t16 - goal16)
            model.Add(diff16 >= goal16 - t16)
            penalties.append(diff16 * 500)

        # --- YENİ ÖZELLİK: HOMOJEN DAĞILIM (Spacing) ---
        # Nöbetleri haftalara/bloklara bölüp dengelemeye çalışacağız.
        weeks = [range(1, 8), range(8, 15), range(15, 22), range(22, num_days+1)]
        for d in docs:
            week_counts = []
            for w_idx, week_days in enumerate(weeks):
                # O haftadaki toplam nöbet sayısı
                valid_days = [t for t in week_days if t <= num_days]
                if not valid_days: continue
                
                wc = model.NewIntVar(0, 7, f'wc_{d}_{w_idx}')
                model.Add(wc == sum(x24[(d,t)] + x16[(d,t)] for t in valid_days))
                week_counts.append(wc)
            
            # Haftalar arası farkı minimize et
            for i in range(len(week_counts) - 1):
                wdiff = model.NewIntVar(0, 7, f'wdiff_{d}_{i}')
                model.Add(wdiff >= week_counts[i] - week_counts[i+1])
                model.Add(wdiff >= week_counts[i+1] - week_counts[i])
                penalties.append(wdiff * 20) # Homojenlik cezası

        # KIDEM DENGESİ (Soft Constraint)
        for t in days:
            cnt_s = sum(x24[(d,t)] for d in seniors)
            cnt_m = sum(x24[(d,t)] for d in mids)
            cnt_j = sum(x24[(d,t)] for d in juniors)
            
            if seniors and mids:
                d1 = model.NewIntVar(0, 10, f'sm_{t}')
                model.Add(d1 >= cnt_s - cnt_m)
                model.Add(d1 >= cnt_m - cnt_s)
                penalties.append(d1 * 5)
            if mids and juniors:
                d2 = model.NewIntVar(0, 10, f'mj_{t}')
                model.Add(d2 >= cnt_m - cnt_j)
                model.Add(d2 >= cnt_j - cnt_m)
                penalties.append(d2 * 5)
            if seniors and juniors:
                d3 = model.NewIntVar(0, 10, f'sj_{t}')
                model.Add(d3 >= cnt_s - cnt_j)
                model.Add(d3 >= cnt_j - cnt_s)
                penalties.append(d3 * 5)
        
        model.Minimize(sum(penalties))

        status_text.text("AI optimum çözümü arıyor...")
        progress_bar.progress(70)
        
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(calc_time)
        status = solver.Solve(model)
        
        progress_bar.progress(100)
        status_text.empty()

        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            st.success(f"✅ Çözüm Bulundu! ({solver.StatusName(status)})")
            
            # --- SONUÇLARI İŞLEME ---
            res_list = []
            res_grid = []
            stats = {d: {"24":0, "16":0} for d in docs}
            
            for t in days:
                dt = datetime(st.session_state.year, st.session_state.month, t)
                t_str = f"{t:02d} {['Pzt','Sal','Çar','Per','Cum','Cmt','Paz'][dt.weekday()]}"
                
                row_g = {"Tarih": t_str}
                l24, l16 = [], []
                cnt_s, cnt_m, cnt_j = 0, 0, 0
                
                for d in docs:
                    val = ""
                    if solver.Value(x24[(d,t)]):
                        val = "24h"
                        l24.append(d)
                        stats[d]["24"] += 1
                        kdm = st.session_state.seniority.get(d)
                        if kdm == "Kıdemli": cnt_s += 1
                        elif kdm == "Çömez": cnt_j += 1
                        else: cnt_m += 1
                    elif solver.Value(x16[(d,t)]):
                        val = "16h"
                        l16.append(d)
                        stats[d]["16"] += 1
                    row_g[d] = val
                
                res_grid.append(row_g)
                res_list.append({
                    "Tarih": t_str,
                    "🔴 24 Saat Ekibi": ", ".join(l24),
                    "🟢 16 Saat Ekibi": ", ".join(l16),
                    "Ekip Dengesi (K-O-Ç)": f"{cnt_s} - {cnt_m} - {cnt_j}"
                })
            
            # --- İSTATİSTİK TABLOSU ---
            stat_rows = []
            for d in docs:
                h24 = st.session_state.quotas_24h.get(d, 0)
                g24 = stats[d]["24"]
                h16 = st.session_state.quotas_16h.get(d, 0)
                g16 = stats[d]["16"]
                
                durum = "✅ Tam"
                if g24 != h24: durum = f"⚠️ {g24-h24:+d}"
                
                stat_rows.append({
                    "Doktor": d,
                    "Kıdem": st.session_state.seniority.get(d),
                    "24h (Hedef/Gerçek)": f"{h24} / {g24}",
                    "16h (Hedef/Gerçek)": f"{h16} / {g16}",
                    "Sapma Durumu": durum
                })
            
            df_list = pd.DataFrame(res_list)
            df_grid = pd.DataFrame(res_grid)
            df_stat = pd.DataFrame(stat_rows)
            
            st.markdown("#### 📊 Dağılım İstatistikleri")
            st.dataframe(df_stat, use_container_width=True)
            
            st.markdown("#### 📅 Günlük Nöbet Listesi")
            st.dataframe(df_list, use_container_width=True)
            
            st.markdown("#### 🌈 Renkli Genel Çizelge")
            def color_map(val):
                if val == "24h": return 'background-color: #ef4444; color: white; font-weight: bold'
                elif val == "16h": return 'background-color: #22c55e; color: white; font-weight: bold'
                return ''
            
            st.dataframe(df_grid.style.applymap(color_map), use_container_width=True)
            
            # Excel İndirme
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
                df_list.to_excel(writer, sheet_name='Liste', index=False)
                df_grid.to_excel(writer, sheet_name='Cizelge', index=False)
                df_stat.to_excel(writer, sheet_name='Istatistik', index=False)
                
                wb = writer.book
                ws = writer.sheets['Cizelge']
                fmt_red = wb.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'})
                ws.conditional_format(1, 1, num_days, len(docs), {'type': 'text', 'criteria': 'containing', 'value': '24h', 'format': fmt_red})
                
            st.download_button("📥 Excel Raporunu İndir", buf.getvalue(), "Nobetinator_Ai_Final.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")

        else:
            st.error("⚠️ Çözüm bulunamadı!")
            st.warning("Çok fazla kısıt olabilir. 'Düşünme Süresi'ni artırmayı veya yasakları azaltmayı deneyin.")

    st.markdown('</div>', unsafe_allow_html=True)