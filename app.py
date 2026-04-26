import streamlit as st
import pandas as pd
from ortools.sat.python import cp_model
import json
from datetime import datetime
import calendar
import io
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
# DÜZELTME #6: Türkçe Ay İsimleri (locale bağımsız)
# -----------------------------------------------------------------------------
TURKCE_AYLAR = {
    1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan",
    5: "Mayıs", 6: "Haziran", 7: "Temmuz", 8: "Ağustos",
    9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık"
}

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

# Varsayılan Kadro
VARSAYILAN_EKIP = [
    {"isim": "Dr. Ahmet", "kota24": 8, "kota16": 0}, {"isim": "Dr. Mehmet", "kota24": 8, "kota16": 0},
    {"isim": "Dr. Ayşe", "kota24": 8, "kota16": 0}, {"isim": "Dr. Fatma",  "kota24": 8, "kota16": 0},
    {"isim": "Dr. Can",  "kota24": 8, "kota16": 0}, {"isim": "Dr. Ali",  "kota24": 8, "kota16": 0},
    {"isim": "Dr. Veli",  "kota24": 8, "kota16": 0}, {"isim": "Dr. Zeynep",  "kota24": 8, "kota16": 0}
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
if 'constraint_warnings' not in st.session_state: st.session_state.constraint_warnings = []

def save_current_month_data():
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

# DÜZELTME #3: Ay değiştirme - quotas, seniority, couples de sıfırlanıyor
def load_month_data(y, m):
    key = get_storage_key(y, m)
    if key in st.session_state.db:
        data = st.session_state.db[key]
        st.session_state.daily_needs_24h = data["daily_needs_24h"]
        st.session_state.daily_needs_16h = data["daily_needs_16h"]
        st.session_state.quotas_24h = data["quotas_24h"]
        st.session_state.quotas_16h = data["quotas_16h"]
        st.session_state.seniority = data.get("seniority", {d: "Orta" for d in st.session_state.doctors})
        st.session_state.manual_constraints = data["manual_constraints"]
        st.session_state.couples = data.get("couples", [])
    else:
        # Yeni ay: tüm veriler varsayılana döner
        st.session_state.daily_needs_24h = {}
        st.session_state.daily_needs_16h = {}
        st.session_state.manual_constraints = {}
        st.session_state.quotas_24h = {d: 0 for d in st.session_state.doctors}
        st.session_state.quotas_16h = {d: 0 for d in st.session_state.doctors}
        st.session_state.seniority = {d: st.session_state.seniority.get(d, "Orta") for d in st.session_state.doctors}
        st.session_state.couples = []

# -----------------------------------------------------------------------------
# DÜZELTME #8: Excel şablonu cache ile optimize edildi
# -----------------------------------------------------------------------------
@st.cache_data
def create_excel_template(_doctors, _seniority, _quotas_24h, _quotas_16h, _daily_needs_24h, _daily_needs_16h, _manual_constraints, year, month):
    """Mevcut ayarları içeren indirilebilir Excel şablonu oluşturur."""
    output = io.BytesIO()
    num_days = calendar.monthrange(year, month)[1]
    
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        # 1. Personel Sayfası
        df_personel = pd.DataFrame({
            "İsim": _doctors,
            "Kıdem": [_seniority.get(d, "Orta") for d in _doctors],
            "24h Kotası": [_quotas_24h.get(d, 8) for d in _doctors],
            "16h Kotası": [_quotas_16h.get(d, 0) for d in _doctors]
        })
        df_personel.to_excel(writer, sheet_name="Personel", index=False)
        
        # 2. Günlük İhtiyaçlar Sayfası
        df_needs = pd.DataFrame({
            "Gün": list(range(1, num_days + 1)),
            "24h Sayısı": [_daily_needs_24h.get(d, 1) for d in range(1, num_days + 1)],
            "16h Sayısı": [_daily_needs_16h.get(d, 0) for d in range(1, num_days + 1)]
        })
        df_needs.to_excel(writer, sheet_name="Günlük İhtiyaçlar", index=False)
        
        # 3. İzinler Sayfası (MATRİS YAPISI)
        days_cols = [str(i) for i in range(1, num_days + 1)]
        matrix_data = {"Doktor": _doctors}
        for col in days_cols:
            matrix_data[col] = [_manual_constraints.get(f"{d}_{col}", "") for d in _doctors]
        df_leaves = pd.DataFrame(matrix_data)
        df_leaves.to_excel(writer, sheet_name="İzinler", index=False)
        
        # Formatlama
        workbook = writer.book
        header_fmt = workbook.add_format({'bold': True, 'bg_color': '#4472C4', 'font_color': 'white', 'border': 1})
        for sheet_name in writer.sheets:
            ws = writer.sheets[sheet_name]
            ws.set_row(0, None, header_fmt)
        writer.sheets['İzinler'].set_column('A:A', 15)
        writer.sheets['İzinler'].set_column('B:AF', 4)
        
    return output.getvalue()

# -----------------------------------------------------------------------------
# DÜZELTME #1: load_excel_data return'daki kesik anahtar düzeltildi
# -----------------------------------------------------------------------------
def load_excel_data(uploaded_file):
    """Excel dosyasından verileri okur ve session state'e yükler."""
    try:
        # 1. Personel Sayfası
        df_personel = pd.read_excel(uploaded_file, sheet_name="Personel")
        doctors_list = []
        quotas_24h, quotas_16h, seniority = {}, {}, {}
        
        for _, row in df_personel.iterrows():
            name = str(row["İsim"]).strip()
            doctors_list.append(name)
            seniority[name] = str(row["Kıdem"]).strip() if "Kıdem" in row and pd.notna(row["Kıdem"]) else "Orta"
            quotas_24h[name] = int(row["24h Kotası"]) if "24h Kotası" in row and pd.notna(row["24h Kotası"]) else 0
            quotas_16h[name] = int(row["16h Kotası"]) if "16h Kotası" in row and pd.notna(row["16h Kotası"]) else 0
        
        # 2. Günlük İhtiyaçlar Sayfası
        df_needs = pd.read_excel(uploaded_file, sheet_name="Günlük İhtiyaçlar")
        daily_needs_24h, daily_needs_16h = {}, {}
        
        for _, row in df_needs.iterrows():
            day = int(row["Gün"])
            daily_needs_24h[day] = int(row["24h Sayısı"]) if "24h Sayısı" in row and pd.notna(row["24h Sayısı"]) else 1
            daily_needs_16h[day] = int(row["16h Sayısı"]) if "16h Sayısı" in row and pd.notna(row["16h Sayısı"]) else 0
        
        # 3. İzinler Sayfası (MATRİS YAPISI)
        manual_constraints = {}
        try:
            df_leaves = pd.read_excel(uploaded_file, sheet_name="İzinler")
            for _, row in df_leaves.iterrows():
                doc_name = str(row["Doktor"]).strip()
                for col in df_leaves.columns:
                    if col == "Doktor":
                        continue
                    try:
                        day_num = int(col)
                        val = str(row[col]).strip().upper() if pd.notna(row[col]) else ""
                        if val in ["X", "S", "24", "16"]:
                            manual_constraints[f"{doc_name}_{day_num}"] = val
                    except:
                        continue
        except Exception as e:
            st.warning(f"İzinler sayfası okunamadı: {e}")
        
        return {
            "doctors": doctors_list,
            "quotas_24h": quotas_24h,
            "quotas_16h": quotas_16h,
            "seniority": seniority,
            "daily_needs_24h": daily_needs_24h,
            "daily_needs_16h": daily_needs_16h,
            "manual_constraints": manual_constraints
        }
    except Exception as e:
        st.error(f"Excel dosyası okunurken hata: {str(e)}")
        return None

# -----------------------------------------------------------------------------
# DÜZELTME #2: Doktor silme yardımcı fonksiyonu (orphan data temizliği)
# -----------------------------------------------------------------------------
def remove_doctor(doc_name):
    """Doktoru listeden ve tüm ilişkili verilerden temizler."""
    if doc_name in st.session_state.doctors:
        st.session_state.doctors.remove(doc_name)
    # Kotalar ve kıdem temizliği
    st.session_state.quotas_24h.pop(doc_name, None)
    st.session_state.quotas_16h.pop(doc_name, None)
    st.session_state.seniority.pop(doc_name, None)
    # Manuel kısıtlar temizliği
    keys_to_remove = [k for k in st.session_state.manual_constraints if k.startswith(f"{doc_name}_")]
    for k in keys_to_remove:
        del st.session_state.manual_constraints[k]
    # Evli çiftler temizliği
    st.session_state.couples = [
        pair for pair in st.session_state.couples
        if doc_name not in pair
    ]

# -----------------------------------------------------------------------------
# 4. YAN MENÜ (SIDEBAR) - KONTROL PANELİ
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## 🏥 Nobetinatör Ai")
    st.markdown("---")
    
    # YENİ: Excel İşlemleri
    with st.expander("📂 Excel ile Veri Yükle", expanded=False):
        st.caption("Matris yapılı Excel yükleyerek tüm verileri otomatik doldurun.")
        
        # DÜZELTME #8: Şablon İndirme - cache ile optimize
        template_data = create_excel_template(
            tuple(st.session_state.doctors),
            dict(st.session_state.seniority),
            dict(st.session_state.quotas_24h),
            dict(st.session_state.quotas_16h),
            dict(st.session_state.daily_needs_24h),
            dict(st.session_state.daily_needs_16h),
            dict(st.session_state.manual_constraints),
            st.session_state.year,
            st.session_state.month
        )
        st.download_button(
            label="📥 Örnek Şablonu İndir",
            data=template_data,
            file_name=f"Nobetinator_Sablon_{st.session_state.year}_{st.session_state.month}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
        
        st.markdown("---")
        
        # Dosya Yükleme
        uploaded_file = st.file_uploader("Excel Dosyası Seçin", type=["xlsx", "xls"], key="excel_upload")
        
        if uploaded_file is not None:
            if st.button("📥 Verileri Yükle ve Uygula", type="primary", use_container_width=True):
                data = load_excel_data(uploaded_file)
                if data:
                    st.session_state.doctors = data["doctors"]
                    st.session_state.quotas_24h = data["quotas_24h"]
                    st.session_state.quotas_16h = data["quotas_16h"]
                    st.session_state.seniority = data["seniority"]
                    st.session_state.daily_needs_24h = data["daily_needs_24h"]
                    st.session_state.daily_needs_16h = data["daily_needs_16h"]
                    st.session_state.manual_constraints = data["manual_constraints"]
                    st.success("✅ Veriler başarıyla yüklendi!")
                    time.sleep(1)
                    st.rerun()
        
        st.markdown("**📋 Excel Şablon Yapısı:**")
        st.markdown("""
        - **Personel**: İsim, Kıdem, 24h/16h Kotası
        - **Günlük İhtiyaçlar**: Gün, 24h/16h Sayısı
        - **İzinler (Matris)**: Satırda Doktor, Sütunda Gün
          - Hücre: `X`, `S`, `24`, `16` veya boş
        """)
    
    st.markdown("---")
    
    # DÜZELTME #6: Türkçe ay isimleri kullanılıyor
    c1, c2 = st.columns(2)
    with c1: selected_year = st.number_input("Yıl", 2024, 2030, st.session_state.year)
    with c2: selected_month = st.selectbox("Ay", range(1, 13), index=st.session_state.month-1, format_func=lambda x: TURKCE_AYLAR[x])
    
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
    calc_time = st.slider("Düşünme Süresi (sn)", 5, 60, 20, help="AI'nın çözümü araması için maksimum süre.")
    
    st.markdown("---")
    
    # EŞLEŞTİRME MODÜLÜ
    with st.expander("❤️ Evli Çiftler / Partnerler", expanded=False):
        st.caption("Seçilen kişiler **mümkün olduğunca aynı gün** nöbet tutar.")
        
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
                col_del1.text(f"{d1} & {d2}")
                if col_del2.button("🗑️", key=f"del_c_{i}"):
                    st.session_state.couples.pop(i)
                    st.rerun()

    with st.expander("👨‍⚕️ Personel İşlemleri"):
        new_doc = st.text_input("Yeni Doktor Adı")
        if st.button("Ekle") and new_doc:
            if new_doc not in st.session_state.doctors:
                st.session_state.doctors.append(new_doc)
                st.session_state.seniority[new_doc] = "Orta"
                st.session_state.quotas_24h[new_doc] = 0
                st.session_state.quotas_16h[new_doc] = 0
                st.rerun()
        
        rem_doc = st.selectbox("Doktor Sil", [""] + st.session_state.doctors)
        # DÜZELTME #2: Doktor silme - orphan data temizliği
        if st.button("Sil") and rem_doc:
            remove_doctor(rem_doc)
            st.rerun()
            
    # DÜZELTME #7: JSON yedekleme tek adımda
    with st.expander("💾 Veri Yedekleme"):
        save_current_month_data()
        d_out = {
            "doctors": st.session_state.doctors,
            "quotas_24h": st.session_state.quotas_24h,
            "quotas_16h": st.session_state.quotas_16h,
            "seniority": st.session_state.seniority,
            "manual_constraints": st.session_state.manual_constraints,
            "couples": st.session_state.couples,
            "year": st.session_state.year, "month": st.session_state.month
        }
        st.download_button(
            "📥 Yedeği İndir (JSON)",
            json.dumps(d_out, default=str, ensure_ascii=False, indent=2),
            f"yedek_{st.session_state.year}_{st.session_state.month}.json",
            mime="application/json"
        )

# -----------------------------------------------------------------------------
# 5. ANA EKRAN (DASHBOARD)
# -----------------------------------------------------------------------------
# DÜZELTME #6: Türkçe ay ismi
st.title(f"🗓️ {TURKCE_AYLAR[st.session_state.month]} {st.session_state.year} Planlama Paneli")

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
    
    # DÜZELTME #5: Varsayılan 16h ihtiyacı 0 olarak ayarlandı
    for d in range(1, num_days+1):
        if d not in st.session_state.daily_needs_24h: st.session_state.daily_needs_24h[d] = 1
        if d not in st.session_state.daily_needs_16h: st.session_state.daily_needs_16h[d] = 0
    
    data_needs = []
    for d in range(1, num_days+1):
        dt = datetime(st.session_state.year, st.session_state.month, d)
        day_name = ['Pzt','Sal','Çar','Per','Cum','Cmt','Paz'][dt.weekday()]
        # DÜZELTME #6: Türkçe ay ismi
        data_needs.append({
            "Gün No": d,
            "Tarih": f"{d} {TURKCE_AYLAR[st.session_state.month]} ({day_name})",
            "🔴 24 Saat İhtiyacı": st.session_state.daily_needs_24h.get(d, 1),
            "🟢 16 Saat İhtiyacı": st.session_state.daily_needs_16h.get(d, 0)
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
            height=400, 
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
    
    # Yeni eklenen doktorların kotalarını kontrol et
    for doc in st.session_state.doctors:
        if doc not in st.session_state.quotas_24h: st.session_state.quotas_24h[doc] = 0
        if doc not in st.session_state.quotas_16h: st.session_state.quotas_16h[doc] = 0

    tot_req_24 = sum(st.session_state.daily_needs_24h.values())
    tot_dist_24 = sum(st.session_state.quotas_24h.get(d, 0) for d in st.session_state.doctors)
    tot_req_16 = sum(st.session_state.daily_needs_16h.values())
    tot_dist_16 = sum(st.session_state.quotas_16h.get(d, 0) for d in st.session_state.doctors)
    
    col_k1, col_k2 = st.columns(2)
    with col_k1:
        delta_val_24 = tot_dist_24 - tot_req_24
        st.metric("🔴 24h Dengesi (İhtiyaç / Kapasite)", f"{tot_req_24} / {tot_dist_24}", delta=int(delta_val_24))
    with col_k2:
        delta_val_16 = tot_dist_16 - tot_req_16
        st.metric("🟢 16h Dengesi (İhtiyaç / Kapasite)", f"{tot_req_16} / {tot_dist_16}", delta=int(delta_val_16))
    
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
            height=500,
            column_config={
                "Doktor": st.column_config.TextColumn(disabled=True),
                "Kıdem": st.column_config.SelectboxColumn(options=["Kıdemli", "Orta", "Çömez"], required=True),
                "🔴 Hedef 24h": st.column_config.NumberColumn(min_value=0, max_value=31, step=1),
                "🟢 Hedef 16h": st.column_config.NumberColumn(min_value=0, max_value=31, step=1)
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

# --- TAB 3: KISITLAR (S HARFİ EKLENDİ) ---
with tab_const:
    st.markdown('<div class="css-card">', unsafe_allow_html=True)
    st.markdown("#### ⚡ Hızlı Veri Girişi (İzinler ve Sabit Nöbetler)")
    
    c_bulk1, c_bulk2, c_bulk3 = st.columns([1.5, 3, 1])
    with c_bulk1:
        b_doc = st.selectbox("Doktor Seç", st.session_state.doctors)
        b_type = st.selectbox("İşlem Tipi", ["❌ Kesin İzin (X)", "⚠️ Esnek İzin (S)", "🔴 24 Saat Nöbet", "🟢 16 Saat Nöbet", "🗑️ Temizle"])
    
    with c_bulk2:
        st.write("Günleri Seçin:")
        days_opts = [str(i) for i in range(1, num_days+1)]
        b_days = st.multiselect("Günler", days_opts, label_visibility="collapsed")
    
    with c_bulk3:
        st.write("")
        st.write("")
        if st.button("Uygula ⚡", type="primary", use_container_width=True):
            if b_days:
                val_map = {"❌ Kesin İzin (X)": "X", "⚠️ Esnek İzin (S)": "S", "🔴 24 Saat Nöbet": "24", "🟢 16 Saat Nöbet": "16", "🗑️ Temizle": ""}
                val = val_map[b_type]
                for d_str in b_days:
                    d = int(d_str)
                    key = f"{b_doc}_{d}"
                    if val:
                        st.session_state.manual_constraints[key] = val
                    else:
                        if key in st.session_state.manual_constraints: del st.session_state.manual_constraints[key]
                st.success("İşlem Tamam!")
                
                # --- KISIT EKLEME SONRASI ANLIK UYARILAR ---
                _warn_msgs = []
                # 1) Doktorun toplam izin günü kontrolü
                doc_x_days = sum(1 for dd in range(1, num_days+1) if st.session_state.manual_constraints.get(f"{b_doc}_{dd}") == "X")
                doc_total_blocked = sum(1 for dd in range(1, num_days+1) if st.session_state.manual_constraints.get(f"{b_doc}_{dd}") in ["X", "S"])
                doc_quota = st.session_state.quotas_24h.get(b_doc, 0) + st.session_state.quotas_16h.get(b_doc, 0)
                available_days = num_days - doc_x_days
                
                if doc_x_days == num_days:
                    _warn_msgs.append(f"🚨 **{b_doc}** ayın tüm günlerinde izinli! Bu doktora hiç nöbet atanamayacak.")
                elif doc_x_days >= num_days * 0.8:
                    _warn_msgs.append(f"⚠️ **{b_doc}** ayın {doc_x_days}/{num_days} gününde izinli. Nöbet atanabilecek çok az gün kaldı.")
                
                if doc_quota > 0 and available_days < doc_quota:
                    _warn_msgs.append(f"⚠️ **{b_doc}** için hedef kota ({doc_quota}) ama müsait gün sayısı ({available_days}). Kota karşılanamayabilir.")
                
                # 2) Günlük kapasite kontrolü
                for d_str_chk in b_days:
                    d_chk = int(d_str_chk)
                    blocked_docs = sum(1 for dc in st.session_state.doctors if st.session_state.manual_constraints.get(f"{dc}_{d_chk}") == "X")
                    need_total = st.session_state.daily_needs_24h.get(d_chk, 1) + st.session_state.daily_needs_16h.get(d_chk, 0)
                    available_docs = len(st.session_state.doctors) - blocked_docs
                    if available_docs < need_total:
                        _warn_msgs.append(f"🚨 **{d_chk}. gün** için {need_total} doktor gerekli ama sadece {available_docs} doktor müsait! Çözüm bulunamayabilir.")
                    elif available_docs == need_total:
                        _warn_msgs.append(f"⚠️ **{d_chk}. gün** için tam sınırda: {available_docs} müsait doktor = {need_total} ihtiyaç. Esneklik kalmadı.")
                
                # Uyarıları session_state'e kaydet (rerun sonrası da görünsün)
                st.session_state.constraint_warnings = _warn_msgs
                
                st.session_state.editor_key += 1
                time.sleep(0.5)
                st.rerun()

    # --- Kalıcı uyarıları göster (session_state'ten) ---
    if st.session_state.constraint_warnings:
        st.markdown("---")
        for _cw in st.session_state.constraint_warnings:
            st.warning(_cw)
        if st.button("✖ Uyarıları Kapat", key="dismiss_warnings"):
            st.session_state.constraint_warnings = []
            st.rerun()
    
    st.markdown("---")
    st.caption("**X** = Kesin İzin (Asla nöbet yazılmaz) | **S** = Esnek İzin (Zorda kalınca yazılabilir) | **24/16** = Sabit Nöbet | Buraya excelden kopyala yapıştır yapabilirsiniz X ve S büyük harf olacak")
    
    # DÜZELTME #13: Boş hücreler "None" yerine "-" gösterecek
    with st.expander("📋 Detaylı Kısıt Tablosunu Göster", expanded=True):
        grid_data = []
        for doc in st.session_state.doctors:
            row = {"Doktor": doc}
            for d in range(1, num_days+1):
                val = st.session_state.manual_constraints.get(f"{doc}_{d}", "")
                row[str(d)] = val if val else ""
            grid_data.append(row)
        
        cfg = {"Doktor": st.column_config.TextColumn(disabled=True)}
        for d in range(1, num_days+1):
            cfg[str(d)] = st.column_config.SelectboxColumn(width="small", options=["", "24", "16", "X", "S"])
            
        with st.form("manual_grid"):
            ed_grid = st.data_editor(pd.DataFrame(grid_data), column_config=cfg, hide_index=True, key=f"grid_{st.session_state.editor_key}")
            if st.form_submit_button("Tabloyu Kaydet"):
                for _, r in ed_grid.iterrows():
                    dc = r["Doktor"]
                    for d in range(1, num_days+1):
                        v = r[str(d)]
                        k = f"{dc}_{d}"
                        if v and v in ["24", "16", "X", "S"]:
                            st.session_state.manual_constraints[k] = v
                        elif k in st.session_state.manual_constraints:
                            del st.session_state.manual_constraints[k]
                st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# --- TAB 4: HESAPLAMA VE ÇÖZÜM ---
with tab_run:
    st.markdown('<div class="css-card">', unsafe_allow_html=True)
    st.markdown("#### 🚀 Nobetinatör Ai Motoru")

    col_act1, col_act2 = st.columns([3, 1])
    with col_act1:
        st.info("Kıdem dengesi, kotalar, eş durumları ve homojen dağılım dikkate alınarak program oluşturulacak.")
    with col_act2:
        run_btn = st.button("Çizelgeyi Oluştur", type="primary", use_container_width=True)
        
    if run_btn:
        # DÜZELTME #11: Boş doktor listesi kontrolü
        if not st.session_state.doctors:
            st.error("⚠️ Aktif personel bulunmuyor! Lütfen önce doktor ekleyin.")
        else:
            # ================================================================
            # KAPSAMLI ÖN DOGRULAMA (PRE-VALIDATION) SİSTEMİ
            # ================================================================
            pre_errors = []    # Çözümü engelleyecek kritik hatalar
            pre_warnings = []  # Uyarılar (bilgilendirme amaçlı)
            
            # --- 1) Sabit nöbet çakışma kontrolü ---
            for t in range(1, num_days+1):
                fixed_24 = sum(1 for d in st.session_state.doctors if st.session_state.manual_constraints.get(f"{d}_{t}") == "24")
                fixed_16 = sum(1 for d in st.session_state.doctors if st.session_state.manual_constraints.get(f"{d}_{t}") == "16")
                need_24 = st.session_state.daily_needs_24h.get(t, 1)
                need_16 = st.session_state.daily_needs_16h.get(t, 0)
                if fixed_24 > need_24:
                    pre_errors.append(f"🚨 Gün {t}: {fixed_24} kişiye sabit 24h nöbet atanmış ama ihtiyaç sadece {need_24}.")
                if fixed_16 > need_16:
                    pre_errors.append(f"🚨 Gün {t}: {fixed_16} kişiye sabit 16h nöbet atanmış ama ihtiyaç sadece {need_16}.")
            
            # --- 2) Günlük müsait doktor yetersizliği kontrolü ---
            for t in range(1, num_days+1):
                blocked = sum(1 for d in st.session_state.doctors if st.session_state.manual_constraints.get(f"{d}_{t}") == "X")
                available = len(st.session_state.doctors) - blocked
                need_total = st.session_state.daily_needs_24h.get(t, 1) + st.session_state.daily_needs_16h.get(t, 0)
                if available < need_total:
                    pre_errors.append(f"🚨 {t}. gün için {need_total} doktor gerekli ama sadece {available} doktor müsait (izinli: {blocked}). Lütfen izinleri veya ihtiyaçları kontrol edin.")
                elif available == need_total:
                    pre_warnings.append(f"⚠️ {t}. gün için tam sınırda: {available} müsait = {need_total} ihtiyaç. Dinlenme kuralları nedeniyle çözümsüzlük olabilir.")
            
            # --- 3) Kota-kapasite uyumsuzluğu kontrolü ---
            total_quota_24 = sum(st.session_state.quotas_24h.get(d, 0) for d in st.session_state.doctors)
            total_quota_16 = sum(st.session_state.quotas_16h.get(d, 0) for d in st.session_state.doctors)
            total_need_24 = sum(st.session_state.daily_needs_24h.get(t, 1) for t in range(1, num_days+1))
            total_need_16 = sum(st.session_state.daily_needs_16h.get(t, 0) for t in range(1, num_days+1))
            
            if total_quota_24 > 0 and total_quota_24 < total_need_24:
                pre_warnings.append(f"⚠️ 24h kota toplamı ({total_quota_24}) < aylık ihtiyaç ({total_need_24}). Bazı doktorlara kotalarının üzerinde nöbet yazılacak.")
            if total_quota_16 > 0 and total_quota_16 < total_need_16:
                pre_warnings.append(f"⚠️ 16h kota toplamı ({total_quota_16}) < aylık ihtiyaç ({total_need_16}). Bazı doktorlara kotalarının üzerinde nöbet yazılacak.")
            
            # --- 4) Doktor bazında aşırı kısıt kontrolü ---
            for d in st.session_state.doctors:
                doc_x = sum(1 for dd in range(1, num_days+1) if st.session_state.manual_constraints.get(f"{d}_{dd}") == "X")
                doc_quota = st.session_state.quotas_24h.get(d, 0) + st.session_state.quotas_16h.get(d, 0)
                doc_available = num_days - doc_x
                
                if doc_x == num_days:
                    pre_warnings.append(f"🚨 **{d}** ayın tüm günlerinde izinli! Bu doktora hiç nöbet atanamayacak.")
                elif doc_x >= num_days * 0.7:
                    pre_warnings.append(f"⚠️ **{d}** ayın {doc_x}/{num_days} gününde izinli. Nöbet atanabilecek çok az gün kaldı ({doc_available} gün).")
                
                if doc_quota > 0 and doc_available > 0 and doc_available < doc_quota:
                    pre_warnings.append(f"⚠️ **{d}** için hedef kota ({doc_quota}) ama müsait gün ({doc_available}). Kota karşılanamayabilir.")
            
            # --- 5) Peş peşe gün kısıtı ile uyumluluk kontrolü ---
            for d in st.session_state.doctors:
                consecutive_issues = []
                for t in range(1, num_days):
                    c1 = st.session_state.manual_constraints.get(f"{d}_{t}", "")
                    c2 = st.session_state.manual_constraints.get(f"{d}_{t+1}", "")
                    if c1 in ["24", "16"] and c2 in ["24", "16"]:
                        consecutive_issues.append(f"{t}-{t+1}")
                if consecutive_issues:
                    pre_errors.append(f"🚨 **{d}** için peş peşe günlerde sabit nöbet atanmış (günler: {', '.join(consecutive_issues)}). Bu kurallara aykırı!")
            
            # --- Uyarıları göster ---
            has_critical = len(pre_errors) > 0
            
            if pre_errors:
                st.error(f"🚨 {len(pre_errors)} kritik sorun tespit edildi! Çözüm bulunamayabilir:")
                for err in pre_errors:
                    st.warning(err)
            
            if pre_warnings:
                with st.expander(f"⚠️ {len(pre_warnings)} uyarı mevcut (görmek için tıklayın)", expanded=has_critical):
                    for pw in pre_warnings:
                        st.info(pw)
            
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
            soft_violations = {}  # Esnek izin ihlalleri için
            
            seniors = [d for d in docs if st.session_state.seniority.get(d) == "Kıdemli"]
            mids = [d for d in docs if st.session_state.seniority.get(d) == "Orta"]
            juniors = [d for d in docs if st.session_state.seniority.get(d) == "Çömez"]
            
            status_text.text("Değişkenler oluşturuluyor...")
            progress_bar.progress(20)

            # 1. TEMEL DEĞİŞKENLER
            for d in docs:
                for t in days:
                    x24[(d,t)] = model.NewBoolVar(f'x24_{d}_{t}')
                    x16[(d,t)] = model.NewBoolVar(f'x16_{d}_{t}')
                    model.Add(x24[(d,t)] + x16[(d,t)] <= 1)

            # 2. GÜNLÜK İHTİYAÇLAR
            for t in days:
                model.Add(sum(x24[(d,t)] for d in docs) == st.session_state.daily_needs_24h.get(t, 1))
                model.Add(sum(x16[(d,t)] for d in docs) == st.session_state.daily_needs_16h.get(t, 0))
                
            # 3. YASAKLAR VE DİNLENME
            for d in docs:
                # Peş peşe gün çalışmama
                for t in range(1, num_days):
                    model.Add(x24[(d,t)] + x16[(d,t)] + x24[(d,t+1)] + x16[(d,t+1)] <= 1)
                
                # 24h sonrası izin
                for t_base in range(1, num_days + 1 - rest_days_24h):
                    block_days = [x24[(d, k)] for k in range(t_base+1, t_base + rest_days_24h + 1)] + \
                                 [x16[(d, k)] for k in range(t_base+1, t_base + rest_days_24h + 1)]
                    model.Add(sum(block_days) == 0).OnlyEnforceIf(x24[(d, t_base)])

                # Manuel Kısıtlar (X, S, 24, 16)
                for t in days:
                    c = st.session_state.manual_constraints.get(f"{d}_{t}", "")
                    if c == "24":
                        model.Add(x24[(d,t)] == 1)
                    elif c == "16":
                        model.Add(x16[(d,t)] == 1)
                    elif c == "X":
                        model.Add(x24[(d,t)] == 0)
                        model.Add(x16[(d,t)] == 0)
                    elif c == "S":
                        # Esnek İzin: Soft Constraint (düzeltilmiş mantık)
                        violation = model.NewBoolVar(f'viol_{d}_{t}')
                        model.AddMaxEquality(violation, [x24[(d,t)], x16[(d,t)]])
                        soft_violations[(d, t)] = violation

            status_text.text("Evlilik ve Sosyal kurallar işleniyor...")
            progress_bar.progress(40)
            
            penalties = []
            
            # Esnek İzin Cezaları
            for (d, t), v in soft_violations.items():
                penalties.append(v * 5000)  # Yüksek ceza ama imkansız değil
            
            # 4. EVLİ ÇİFTLER (ESNEK)
            for (d1, d2) in st.session_state.couples:
                if d1 in docs and d2 in docs:
                    for t in days:
                        w1 = model.NewBoolVar(f'w_{d1}_{t}')
                        w2 = model.NewBoolVar(f'w_{d2}_{t}')
                        model.AddMaxEquality(w1, [x24[(d1,t)], x16[(d1,t)]])
                        model.AddMaxEquality(w2, [x24[(d2,t)], x16[(d2,t)]])
                        
                        both = model.NewBoolVar(f'both_{d1}_{d2}_{t}')
                        model.AddBoolAnd([w1, w2]).OnlyEnforceIf(both)
                        model.AddBoolOr([w1.Not(), w2.Not()]).OnlyEnforceIf(both.Not())
                        
                        mismatch = model.NewIntVar(0, 1, f'mm_{d1}_{d2}_{t}')
                        model.Add(mismatch == w1 + w2 - 2 * both)
                        penalties.append(mismatch * 100) 

            # 5. KOTALAR (Soft Constraints)
            for d in docs:
                t24 = sum(x24[(d,t)] for t in days)
                goal24 = st.session_state.quotas_24h.get(d, 0)
                diff24 = model.NewIntVar(0, 31, f'd24_{d}')
                model.Add(diff24 >= t24 - goal24)
                model.Add(diff24 >= goal24 - t24)
                penalties.append(diff24 * 500)
                
                t16 = sum(x16[(d,t)] for t in days)
                goal16 = st.session_state.quotas_16h.get(d, 0)
                diff16 = model.NewIntVar(0, 31, f'd16_{d}')
                model.Add(diff16 >= t16 - goal16)
                model.Add(diff16 >= goal16 - t16)
                penalties.append(diff16 * 500)

            # 6. HOMOJEN DAĞILIM (Haftalık Denge)
            # DÜZELTME #10: Haftalık denge - oransal karşılaştırma
            weeks = [range(1, 8), range(8, 15), range(15, 22), range(22, num_days+1)]
            for d in docs:
                week_counts = []
                for w_idx, week_days in enumerate(weeks):
                    valid_days = [t for t in week_days if t <= num_days]
                    if not valid_days: continue
                    wc = model.NewIntVar(0, 10, f'wc_{d}_{w_idx}')
                    model.Add(wc == sum(x24[(d,t)] + x16[(d,t)] for t in valid_days))
                    week_counts.append(wc)
                
                for i in range(len(week_counts) - 1):
                    wdiff = model.NewIntVar(0, 10, f'wdiff_{d}_{i}')
                    model.Add(wdiff >= week_counts[i] - week_counts[i+1])
                    model.Add(wdiff >= week_counts[i+1] - week_counts[i])
                    penalties.append(wdiff * 20)

            # 7. KIDEM DENGESİ
            for t in days:
                cnt_s = sum(x24[(d,t)] for d in seniors)
                cnt_m = sum(x24[(d,t)] for d in mids)
                
                if seniors and mids:
                    d1 = model.NewIntVar(0, 10, f'sm_{t}')
                    model.Add(d1 >= cnt_s - cnt_m)
                    model.Add(d1 >= cnt_m - cnt_s)
                    penalties.append(d1 * 5)
            
            # HEDEF FONKSİYON
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
                warnings = []  # Esnek izin ihlalleri
                
                for t in days:
                    dt = datetime(st.session_state.year, st.session_state.month, t)
                    t_str = f"{t:02d} {['Pzt','Sal','Çar','Per','Cum','Cmt','Paz'][dt.weekday()]}"
                    
                    row_g = {"Tarih": t_str}
                    l24, l16 = [], []
                    
                    for d in docs:
                        val = ""
                        if solver.Value(x24[(d,t)]):
                            val = "24h"
                            l24.append(d)
                            stats[d]["24"] += 1
                            # Esnek izin ihlali kontrolü
                            if (d, t) in soft_violations and solver.Value(soft_violations[(d, t)]):
                                warnings.append(f"⚠️ {d}: {t}. gün esnek izin (S) istemişti ama 24h nöbet yazıldı.")
                        elif solver.Value(x16[(d,t)]):
                            val = "16h"
                            l16.append(d)
                            stats[d]["16"] += 1
                            if (d, t) in soft_violations and solver.Value(soft_violations[(d, t)]):
                                warnings.append(f"⚠️ {d}: {t}. gün esnek izin (S) istemişti ama 16h nöbet yazıldı.")
                        row_g[d] = val
                    
                    res_grid.append(row_g)
                    res_list.append({
                        "Tarih": t_str,
                        "🔴 24 Saat Ekibi": ", ".join(l24),
                        "🟢 16 Saat Ekibi": ", ".join(l16)
                    })
                
                # Esnek İzin İhlalleri Uyarısı
                if warnings:
                    with st.expander("⚠️ Esnek İzin İhlalleri", expanded=True):
                        st.warning("Aşağıdaki kişilere esnek izin (S) verilmesine rağmen çözüm için nöbet yazılmak zorunda kalındı:")
                        for w in warnings:
                            st.write(w)
                
                # --- İSTATİSTİK TABLOSU ---
                # DÜZELTME #4: Sapma Durumu artık hem 24h hem 16h kontrol ediyor
                stat_rows = []
                for d in docs:
                    h24 = st.session_state.quotas_24h.get(d, 0)
                    g24 = stats[d]["24"]
                    h16 = st.session_state.quotas_16h.get(d, 0)
                    g16 = stats[d]["16"]
                    
                    sapma_24 = g24 - h24
                    sapma_16 = g16 - h16
                    
                    if sapma_24 == 0 and sapma_16 == 0:
                        durum = "✅ Tam"
                    else:
                        parts = []
                        if sapma_24 != 0:
                            parts.append(f"24h:{sapma_24:+d}")
                        if sapma_16 != 0:
                            parts.append(f"16h:{sapma_16:+d}")
                        durum = f"⚠️ {' / '.join(parts)}"
                    
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
                
                st.dataframe(df_grid.style.map(color_map), use_container_width=True)
                
                # Excel İndirme
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
                    df_list.to_excel(writer, sheet_name='Liste', index=False)
                    df_grid.to_excel(writer, sheet_name='Cizelge', index=False)
                    df_stat.to_excel(writer, sheet_name='Istatistik', index=False)
                    
                    # Uyarılar sayfası
                    if warnings:
                        df_warn = pd.DataFrame({"Uyarılar": warnings})
                        df_warn.to_excel(writer, sheet_name='Uyarilar', index=False)
                    
                    # Excel Renklendirme
                    wb = writer.book
                    ws = writer.sheets['Cizelge']
                    fmt_red = wb.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'})
                    fmt_grn = wb.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100'})
                    
                    ws.conditional_format(1, 1, num_days, len(docs), {'type': 'text', 'criteria': 'containing', 'value': '24h', 'format': fmt_red})
                    ws.conditional_format(1, 1, num_days, len(docs), {'type': 'text', 'criteria': 'containing', 'value': '16h', 'format': fmt_grn})
                    
                st.download_button("📥 Excel Raporunu İndir", buf.getvalue(), "Nobetinator_Ai_Final.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")

            else:
                st.error("🚨 Çözüm Bulunamadı! (INFEASIBLE)")
                st.markdown("---")
                st.markdown("#### 🔍 Olası Nedenler ve Çözüm Önerileri")
                
                # Detaylı neden analizi
                infeasible_reasons = []
                
                # Neden 1: Günlük müsait doktor yetersizliği
                for t_chk in range(1, num_days+1):
                    blocked_chk = sum(1 for d in docs if st.session_state.manual_constraints.get(f"{d}_{t_chk}") == "X")
                    avail_chk = len(docs) - blocked_chk
                    need_chk = st.session_state.daily_needs_24h.get(t_chk, 1) + st.session_state.daily_needs_16h.get(t_chk, 0)
                    if avail_chk < need_chk:
                        infeasible_reasons.append(f"🚨 **{t_chk}. gün**: {need_chk} doktor gerekli ama sadece {avail_chk} müsait ({blocked_chk} kişi izinli). **Çözüm:** {t_chk}. gündeki izinleri azaltın veya günlük ihtiyacı düşürün.")
                
                # Neden 2: Peş peşe sabit nöbet çakışması
                for d in docs:
                    for t_chk in range(1, num_days):
                        c1 = st.session_state.manual_constraints.get(f"{d}_{t_chk}", "")
                        c2 = st.session_state.manual_constraints.get(f"{d}_{t_chk+1}", "")
                        if c1 in ["24", "16"] and c2 in ["24", "16"]:
                            infeasible_reasons.append(f"🚨 **{d}**: {t_chk}. ve {t_chk+1}. günlerde peş peşe sabit nöbet var. **Çözüm:** Birini kaldırın.")
                
                # Neden 3: Sabit nöbet fazlalığı
                for t_chk in range(1, num_days+1):
                    f24 = sum(1 for d in docs if st.session_state.manual_constraints.get(f"{d}_{t_chk}") == "24")
                    f16 = sum(1 for d in docs if st.session_state.manual_constraints.get(f"{d}_{t_chk}") == "16")
                    n24 = st.session_state.daily_needs_24h.get(t_chk, 1)
                    n16 = st.session_state.daily_needs_16h.get(t_chk, 0)
                    if f24 > n24:
                        infeasible_reasons.append(f"🚨 **{t_chk}. gün**: {f24} kişiye sabit 24h nöbet atanmış ama ihtiyaç {n24}. **Çözüm:** Fazla sabit nöbeti kaldırın.")
                    if f16 > n16:
                        infeasible_reasons.append(f"🚨 **{t_chk}. gün**: {f16} kişiye sabit 16h nöbet atanmış ama ihtiyaç {n16}. **Çözüm:** Fazla sabit nöbeti kaldırın.")
                
                # Neden 4: Aşırı izinli doktorlar
                for d in docs:
                    doc_x_chk = sum(1 for dd in range(1, num_days+1) if st.session_state.manual_constraints.get(f"{d}_{dd}") == "X")
                    if doc_x_chk >= num_days * 0.8:
                        infeasible_reasons.append(f"⚠️ **{d}** ayın {doc_x_chk}/{num_days} gününde izinli. **Çözüm:** Bazı izinleri kaldırın veya esnek izin (S) yapın.")
                
                if infeasible_reasons:
                    for ir in infeasible_reasons:
                        st.warning(ir)
                else:
                    st.warning("Çok fazla kısıt (izinler + dinlenme kuralları) bir araya geldiğinde çözüm bulunamıyor.")
                    st.info("**Öneriler:** 1️⃣ Bazı kesin izinleri (X) esnek izine (S) çevirin. 2️⃣ Düşünme süresini artırın. 3️⃣ 24h sonrası izin gününü azaltın. 4️⃣ Günlük ihtiyaçları kontrol edin.")

    st.markdown('</div>', unsafe_allow_html=True)
