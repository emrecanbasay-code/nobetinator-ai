import streamlit as st
import pandas as pd
from ortools.sat.python import cp_model
import json
from datetime import datetime
import calendar
import io
import xlsxwriter

# --- EVLİ ÇİFTLER LİSTESİ (Burayı Düzenleyebilirsiniz) ---
# Format: [("Doktor1", "Doktor2"), ("Doktor3", "Doktor4")]
COUPLES_LIST = [
    ("A10", "A11"), 
    ("A20", "A21")
]

# --- SAYFA VE TASARIM AYARLARI ---
st.set_page_config(
    page_title="Nobetinator Pro v3",
    page_icon="🌑",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS TASARIMI ---
st.markdown("""
<style>
    .stApp { background-color: #0f172a !important; }
    h1, h2, h3, h4, h5, h6, p, span, div, label, li { color: #e2e8f0 !important; }
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
        background-color: #3b82f6 !important; color: white !important; border-radius: 8px; font-weight: 600; 
        width: 100%; transition: all 0.2s ease;
    }
    .stButton>button:hover { background-color: #2563eb !important; transform: translateY(-2px); }
    div[data-testid="stDataEditor"] { background-color: #1e293b; border-radius: 10px; border: 1px solid #334155; }
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
        init_defaults()

def init_defaults():
    # Doktor listesi
    initial_doctors = ["A01", "A02", "A03"] + [f"A{i}" for i in range(4, 34)]
    st.session_state.doctors = initial_doctors
    
    q24, q16 = {}, {}
    for doc in initial_doctors:
        d_24, d_16 = 8, 0
        if doc in ["A22", "A23"] or doc in [f"A{i}" for i in range(25, 34)]: d_24, d_16 = 8, 2
        elif doc == "A24": d_24, d_16 = 6, 2
        q24[doc] = d_24
        q16[doc] = d_16
    st.session_state.quotas_24h = q24
    st.session_state.quotas_16h = q16
    st.session_state.manual_constraints = {}

# --- BAŞLANGIÇ ---
if 'year' not in st.session_state: st.session_state.year = datetime.now().year
if 'month' not in st.session_state: st.session_state.month = datetime.now().month
if 'doctors' not in st.session_state: init_defaults()
if 'daily_needs_24h' not in st.session_state: st.session_state.daily_needs_24h = {}
if 'daily_needs_16h' not in st.session_state: st.session_state.daily_needs_16h = {}

# --- SIDEBAR ---
with st.sidebar:
    st.title("🌑 Nobetinator Pro v3")
    st.markdown("---")
    
    # Tarih
    c1, c2 = st.columns(2)
    with c1: selected_year = st.number_input("Yıl", 2020, 2030, st.session_state.year)
    with c2: selected_month = st.selectbox("Ay", range(1, 13), index=st.session_state.month-1, format_func=lambda x: calendar.month_name[x])
    
    if selected_year != st.session_state.year or selected_month != st.session_state.month:
        save_current_month_data()
        st.session_state.year = selected_year
        st.session_state.month = selected_month
        load_month_data(selected_year, selected_month)
        st.rerun()
    
    num_days = calendar.monthrange(selected_year, selected_month)[1]
    
    st.markdown("---")
    st.subheader("⚙️ Kurallar & Ayarlar")
    
    # 1. Düşünme Süresi (Geri Geldi)
    calc_time = st.slider("⏳ Düşünme Süresi (Saniye)", 10, 120, 30, help="Süre ne kadar uzun olursa karmaşık durumlarda çözüm bulma şansı artar.")
    
    # 2. Dinlenme Kuralı
    rest_days_24h = st.slider("🛌 24h Sonrası Yasaklı Gün", 1, 5, 2)
    
    # 3. Evli Çiftler Modu (Geri Geldi)
    enable_couples = st.checkbox("❤️ Evli Çiftler Çakışmasın", value=True, help="Listedeki çiftlerin aynı gün nöbet tutmasını engeller.")
    
    st.markdown("### 🔓 Esneklik (Soft Kural)")
    # 4. Esnek X Modu
    allow_break_x = st.checkbox(
        "Sıkışırsa 'X' Delinebilir", 
        value=True, 
        help="Liste dönmezse 'X' günlerine mecburen nöbet yazar (Ceza puanı ile)."
    )
    
    st.info("ℹ️ **Not:** Doktor kotaları her zaman **KATI LİMİT**'tir ve aşılmaz.")
    
    st.markdown("---")
    with st.expander("👨‍⚕️ Kadro Yönetimi"):
        new_doc = st.text_input("Eklenecek İsim")
        if st.button("Ekle") and new_doc:
            if new_doc not in st.session_state.doctors:
                st.session_state.doctors.append(new_doc)
                st.rerun()
        rem_doc = st.selectbox("Silinecek", [""] + st.session_state.doctors)
        if st.button("Sil") and rem_doc:
            st.session_state.doctors.remove(rem_doc)
            st.rerun()

# --- ANA EKRAN ---
st.markdown(f"### 🗓️ {calendar.month_name[st.session_state.month]} {st.session_state.year} Dashboard")

t1, t2, t3, t4 = st.tabs(["📋 İHTİYAÇLAR", "🎯 KOTALAR", "🔒 KISITLAR (X)", "🚀 HESAPLA"])

# TAB 1: İHTİYAÇLAR
with t1:
    st.markdown('<div class="css-card">', unsafe_allow_html=True)
    # Varsayılanlar
    for d in range(1, num_days+1):
        if d not in st.session_state.daily_needs_24h: st.session_state.daily_needs_24h[d] = 1
        if d not in st.session_state.daily_needs_16h: st.session_state.daily_needs_16h[d] = 1
    
    d_data = [{"Gün": d, "Tarih": f"{d}", "24h": st.session_state.daily_needs_24h.get(d, 1), "16h": st.session_state.daily_needs_16h.get(d, 1)} for d in range(1, num_days+1)]
    with st.form("needs_manual"):
        edf = st.data_editor(pd.DataFrame(d_data), key="need_ed", use_container_width=True, hide_index=True, column_config={"Gün": st.column_config.NumberColumn(disabled=True)})
        if st.form_submit_button("💾 Kaydet"):
            for i, r in edf.iterrows():
                st.session_state.daily_needs_24h[r["Gün"]] = int(r["24h"])
                st.session_state.daily_needs_16h[r["Gün"]] = int(r["16h"])
            st.success("Kaydedildi!")
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# TAB 2: KOTALAR
with t2:
    st.markdown('<div class="css-card">', unsafe_allow_html=True)
    q_data = [{"Dr": d, "Max 24h": st.session_state.quotas_24h.get(d, 0), "Max 16h": st.session_state.quotas_16h.get(d, 0)} for d in st.session_state.doctors]
    with st.form("quotas_manual"):
        qdf = st.data_editor(pd.DataFrame(q_data), key="quota_ed", use_container_width=True, hide_index=True, column_config={"Dr": st.column_config.TextColumn(disabled=True)})
        if st.form_submit_button("💾 Kaydet"):
            for i, r in qdf.iterrows():
                st.session_state.quotas_24h[r["Dr"]] = int(r["Max 24h"])
                st.session_state.quotas_16h[r["Dr"]] = int(r["Max 16h"])
            st.success("Kaydedildi!")
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# TAB 3: KISITLAR
with t3:
    st.markdown('<div class="css-card">', unsafe_allow_html=True)
    st.info("Hücrelere '24', '16' veya 'X' yazabilirsiniz.")
    c_data = []
    for doc in st.session_state.doctors:
        r = {"Doktor": doc}
        for d in range(1, num_days+1): r[str(d)] = st.session_state.manual_constraints.get(f"{doc}_{d}", "")
        c_data.append(r)
    
    col_cfg = {"Doktor": st.column_config.TextColumn(disabled=True)}
    for d in range(1, num_days+1): col_cfg[str(d)] = st.column_config.SelectboxColumn(label=str(d), options=["", "24", "16", "X"], width="small")
    
    with st.form("const_manual"):
        ed_cons = st.data_editor(pd.DataFrame(c_data), column_config=col_cfg, hide_index=True, use_container_width=True, key="cons_ed")
        if st.form_submit_button("💾 Kaydet"):
            for i, r in ed_cons.iterrows():
                doc = r["Doktor"]
                for d in range(1, num_days+1):
                    val = str(r[str(d)])
                    k = f"{doc}_{d}"
                    if val in ["24", "16", "X"]: st.session_state.manual_constraints[k] = val
                    elif k in st.session_state.manual_constraints: del st.session_state.manual_constraints[k]
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# TAB 4: HESAPLAMA
with t4:
    st.markdown('<div class="css-card">', unsafe_allow_html=True)
    if st.button("🚀 Nöbetleri Dağıt (AI)", type="primary", use_container_width=True):
        with st.spinner("Yapay zeka hesaplıyor..."):
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

            # 1. Günlük İhtiyaçlar (ZORUNLU)
            for t in days:
                need24 = st.session_state.daily_needs_24h.get(t, 1)
                need16 = st.session_state.daily_needs_16h.get(t, 1)
                model.Add(sum(x24[(d,t)] for d in docs) == need24)
                model.Add(sum(x16[(d,t)] for d in docs) == need16)

            # 2. Temel Kurallar (Blok & Dinlenme)
            for d in docs:
                # 24/16 üst üste yasak
                for t in range(1, num_days):
                    model.Add(x24[(d,t)] + x16[(d,t)] + x24[(d,t+1)] + x16[(d,t+1)] <= 1)
                
                # Dinlenme (48 saat vs)
                win = rest_days_24h + 1
                for i in range(len(days) - win + 1):
                    wd = [days[j] for j in range(i, i+win)]
                    model.Add(sum(x24[(d,k)] for k in wd) <= 1)

            # 3. Kotalar (ZORUNLU - Asla Aşılmaz)
            for d in docs:
                tot24 = sum(x24[(d,t)] for t in days)
                tgt24 = st.session_state.quotas_24h.get(d, 0)
                model.Add(tot24 <= tgt24) 
                
                tot16 = sum(x16[(d,t)] for t in days)
                tgt16 = st.session_state.quotas_16h.get(d, 0)
                model.Add(tot16 <= tgt16)

            # 4. Evli Çiftler Kuralı (SEÇMELİ)
            if enable_couples:
                for c1, c2 in COUPLES_LIST:
                    if c1 in docs and c2 in docs:
                        for t in days:
                            # Aynı gün ikisi birden nöbet (24 veya 16 fark etmez) tutamaz
                            model.Add(x24[(c1,t)] + x16[(c1,t)] + x24[(c2,t)] + x16[(c2,t)] <= 1)

            # 5. 'X' Kısıtları (SEÇMELİ - SOFT/HARD)
            soft_penalties = []
            for d in docs:
                for t in days:
                    c = st.session_state.manual_constraints.get(f"{d}_{t}", "")
                    
                    if c == "24": model.Add(x24[(d,t)] == 1)
                    elif c == "16": model.Add(x16[(d,t)] == 1)
                    elif c == "X":
                        if allow_break_x:
                            # Esnekse: Ceza puanı ekle
                            soft_penalties.append(x24[(d,t)])
                            soft_penalties.append(x16[(d,t)])
                        else:
                            # Katıysa: Yasakla
                            model.Add(x24[(d,t)] == 0)
                            model.Add(x16[(d,t)] == 0)

            # Hedef Fonksiyonu
            if soft_penalties:
                # X ihlallerini minimize et
                model.Minimize(sum(soft_penalties))

            solver = cp_model.CpSolver()
            # KULLANICININ SEÇTİĞİ SÜRE
            solver.parameters.max_time_in_seconds = calc_time
            status = solver.Solve(model)

            if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
                st.success(f"✅ Çizelge Hazır! (Süre: {solver.WallTime():.2f} sn)")
                if allow_break_x and solver.ObjectiveValue() > 0:
                    st.warning(f"⚠️ DİKKAT: Liste sıkıştığı için {int(solver.ObjectiveValue())} yerde 'X' kuralı ihlal edildi.")

                # Raporlama
                res_mx, res_lst = [], []
                stats = {d: {"24h":0, "16h":0} for d in docs}
                
                for t in days:
                    dstr = f"{t:02d}"
                    rm = {"Tarih": dstr}
                    l24, l16 = [], []
                    for d in docs:
                        is_violation = False
                        constraint_val = st.session_state.manual_constraints.get(f"{d}_{t}", "")
                        cell_val = ""
                        
                        if solver.Value(x24[(d,t)]): 
                            cell_val = "24h"
                            stats[d]["24h"] += 1
                            l24.append(d)
                            if constraint_val == "X": is_violation = True
                        elif solver.Value(x16[(d,t)]): 
                            cell_val = "16h"
                            stats[d]["16h"] += 1
                            l16.append(d)
                            if constraint_val == "X": is_violation = True
                        
                        if is_violation: cell_val += " (!)"
                        rm[d] = cell_val
                    res_mx.append(rm)
                    res_lst.append({"Tarih": dstr, "24 Saat": ", ".join(l24), "16 Saat": ", ".join(l16)})
                
                # İstatistik
                stat_data = []
                for d in docs:
                    t24 = st.session_state.quotas_24h.get(d, 0)
                    g24 = stats[d]["24h"]
                    t16 = st.session_state.quotas_16h.get(d, 0)
                    g16 = stats[d]["16h"]
                    
                    status_msgs = []
                    if g24 < t24: status_msgs.append(f"24h: {t24-g24} Eksik")
                    if g16 < t16: status_msgs.append(f"16h: {t16-g16} Eksik")
                    
                    final_status = "✅ Tam" if not status_msgs else "⚠️ " + ", ".join(status_msgs)
                    
                    stat_data.append({
                        "Doktor": d,
                        "24h (Limit/Gerçek)": f"{t24} / {g24}",
                        "16h (Limit/Gerçek)": f"{t16} / {g16}",
                        "Durum": final_status
                    })
                
                df_mx = pd.DataFrame(res_mx)
                df_st = pd.DataFrame(stat_data)
                
                st.dataframe(df_st, use_container_width=True)
                
                def highlight_cells(val):
                    if '24h' in str(val): return 'background-color: #7f1d1d; color: white' if '(!)' in str(val) else 'background-color: #ef4444; color: white'
                    if '16h' in str(val): return 'background-color: #14532d; color: white' if '(!)' in str(val) else 'background-color: #22c55e; color: white'
                    return ''
                
                st.dataframe(df_mx.style.applymap(highlight_cells), use_container_width=True)
                
                # Excel İndirme
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
                    pd.DataFrame(res_lst).to_excel(writer, sheet_name='Liste', index=False)
                    df_mx.to_excel(writer, sheet_name='Cizelge', index=False)
                    df_st.to_excel(writer, sheet_name='Istatistik', index=False)
                st.download_button("📥 Excel İndir", buf.getvalue(), "nobet_cizelgesi.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                
            else:
                st.error("Çözüm Bulunamadı! Kotalar yetersiz veya kurallar çok sıkı. Süreyi artırmayı veya 'Esnek X' modunu açmayı deneyin.")
    st.markdown('</div>', unsafe_allow_html=True)
