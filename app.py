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
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS İLE MODERN GÖRÜNÜM (AI TEMASI) ---
st.markdown("""
<style>
    /* Ana Arka Plan */
    .stApp { background-color: #f0f2f6; }
    
    /* Sidebar */
    [data-testid="stSidebar"] { background-color: #1e272e; }
    [data-testid="stSidebar"] * { color: #d2dae2 !important; }
    
    /* Başlıklar */
    h1, h2, h3 { color: #1e272e; font-family: 'Segoe UI', sans-serif; }
    
    /* Kartlar */
    .css-card { 
        background-color: white; 
        padding: 25px; 
        border-radius: 15px; 
        box-shadow: 0 4px 15px rgba(0,0,0,0.05); 
        margin-bottom: 20px; 
        border-left: 6px solid #0fb9b1; /* Turkuaz AI Rengi */
    }
    
    /* Butonlar */
    .stButton>button { 
        background-color: #0fb9b1; 
        color: white; 
        border-radius: 10px; 
        border: none; 
        padding: 0.6rem 1.2rem; 
        font-weight: 600; 
        transition: all 0.3s ease; 
    }
    .stButton>button:hover { 
        background-color: #05c46b; 
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        transform: translateY(-2px);
    }
    
    /* Metrik Kutuları */
    div[data-testid="stMetric"] { 
        background-color: #ffffff; 
        border: 1px solid #dcdde1; 
        padding: 15px; 
        border-radius: 12px; 
        text-align: center; 
    }
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
        st.session_state.quotas_24h = {doc: 0 for doc in st.session_state.doctors}
        st.session_state.quotas_16h = {doc: 0 for doc in st.session_state.doctors}
        st.session_state.manual_constraints = {}

# --- BAŞLANGIÇ AYARLARI ---
if 'doctors' not in st.session_state: st.session_state.doctors = ["Dr. Ahmet", "Dr. Ayşe", "Dr. Mehmet", "Dr. Zeynep", "Dr. Can"]
if 'year' not in st.session_state: st.session_state.year = datetime.now().year
if 'month' not in st.session_state: st.session_state.month = datetime.now().month
if 'db' not in st.session_state: st.session_state.db = {}

# Sözlük Kontrolleri
if 'daily_needs_24h' not in st.session_state: st.session_state.daily_needs_24h = {}
if 'daily_needs_16h' not in st.session_state: st.session_state.daily_needs_16h = {}
if 'quotas_24h' not in st.session_state: st.session_state.quotas_24h = {}
if 'quotas_16h' not in st.session_state: st.session_state.quotas_16h = {}
if 'manual_constraints' not in st.session_state: st.session_state.manual_constraints = {}

# --- SIDEBAR MENÜSÜ ---
with st.sidebar:
    st.title("🤖 Nobetinator AI")
    st.caption("Yapay Zeka Destekli Planlama")
    st.markdown("---")
    
    # 1. Tarih
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
    
    # 2. Kurallar
    st.subheader("⚙️ Kurallar")
    rest_days_24h = st.slider("24h Sonrası Yasaklı Gün", 1, 5, 2, help="24 saat nöbetten sonra kaç gün boş kalsın?")
    
    st.markdown("---")
    
    # 3. Mod Seçimi
    st.subheader("🎛️ AI Modu")
    solver_mode = st.radio(
        "Strateji:", 
        ["Katı Kurallar (Tam Uyum)", "Esnek Mod (Tavan Sınır)"], 
        index=1,
        help="Esnek Mod: Belirlediğin sayıyı ASLA aşmaz, gerekirse daha az yazar."
    )
    
    st.markdown("---")
    
    # 4. Doktorlar
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

    # 5. Yedekleme
    with st.expander("💾 Veri Yedekleme"):
        if st.button("Yedek İndir (JSON)"):
            save_current_month_data()
            d_out = {"doctors": st.session_state.doctors, "db": {str(k): v for k, v in st.session_state.db.items()}, "current_year": st.session_state.year, "current_month": st.session_state.month}
            st.download_button("İndir", json.dumps(d_out, default=str), "nobetinator_backup.json")
            
        upl = st.file_uploader("Yedek Yükle", type=['json'])
        if upl:
            try:
                data = json.load(upl)
                st.session_state.doctors = data.get('doctors', st.session_state.doctors)
                st.rerun()
            except: pass

# --- ANA EKRAN ---
st.markdown(f"## 🗓️ {calendar.month_name[st.session_state.month]} {st.session_state.year} Planlaması")

# Dashboard
c1, c2, c3, c4 = st.columns(4)
c1.metric("Toplam Gün", num_days)
c2.metric("Personel Sayısı", len(st.session_state.doctors))
c3.metric("Çalışma Modu", "Esnek (Tavan)" if "Esnek" in solver_mode else "Katı")
c4.metric("Aktif Kısıtlar", len(st.session_state.manual_constraints))

st.write("") # Boşluk

# Sekmeler
t1, t2, t3, t4 = st.tabs(["📋 GÜNLÜK İHTİYAÇ", "🎯 KOTALAR (LİMİT)", "🔒 KISITLAR (X)", "🚀 SONUÇ & EXCEL"])

# TAB 1: GÜNLÜK İHTİYAÇLAR
with t1:
    st.markdown('<div class="css-card">', unsafe_allow_html=True)
    st.info("Hangi gün kaç personele ihtiyaç var?")
    
    d_data = [{"Gün": d, "Tarih": f"{d} {['Pzt','Sal','Çar','Per','Cum','Cmt','Paz'][datetime(st.session_state.year, st.session_state.month, d).weekday()]}", "24h": st.session_state.daily_needs_24h.get(d, 1), "16h": st.session_state.daily_needs_16h.get(d, 1)} for d in range(1, num_days+1)]
    
    with st.form("needs"):
        edf = st.data_editor(pd.DataFrame(d_data), key="need_ed", use_container_width=True, hide_index=True, column_config={"Gün": st.column_config.NumberColumn(disabled=True), "Tarih": st.column_config.TextColumn(disabled=True)})
        if st.form_submit_button("💾 İhtiyaçları Kaydet", type="primary"):
            for i, r in edf.iterrows():
                st.session_state.daily_needs_24h[r["Gün"]] = int(r["24h"])
                st.session_state.daily_needs_16h[r["Gün"]] = int(r["16h"])
            st.success("Kaydedildi!")
    st.markdown('</div>', unsafe_allow_html=True)

# TAB 2: KOTALAR
with t2:
    st.markdown('<div class="css-card">', unsafe_allow_html=True)
    if "Esnek" in solver_mode:
        st.warning("⚠️ **Esnek Mod:** Bu sayılar **ÜST LİMİTTİR**. AI asla bu sayıdan fazla nöbet yazmaz, gerekirse daha az yazar.")
    else:
        st.info("ℹ️ **Katı Mod:** AI tam olarak bu sayı kadar nöbet yazmaya çalışır. Sığmazsa hata verir.")
        
    q_data = [{"Dr": d, "Max 24h": st.session_state.quotas_24h.get(d, 0), "Max 16h": st.session_state.quotas_16h.get(d, 0)} for d in st.session_state.doctors]
    
    with st.form("quotas"):
        qdf = st.data_editor(pd.DataFrame(q_data), key="quota_ed", use_container_width=True, hide_index=True, column_config={"Dr": st.column_config.TextColumn(disabled=True)})
        if st.form_submit_button("💾 Hedefleri Kaydet", type="primary"):
            for i, r in qdf.iterrows():
                st.session_state.quotas_24h[r["Dr"]] = int(r["Max 24h"])
                st.session_state.quotas_16h[r["Dr"]] = int(r["Max 16h"])
            st.success("Kaydedildi!")
    st.markdown('</div>', unsafe_allow_html=True)

# TAB 3: MANUEL KISITLAR (AKILLI)
with t3:
    st.markdown('<div class="css-card">', unsafe_allow_html=True)
    st.write(f"💡 **Akıllı Kısıt:** '24' seçerseniz, sonraki **{rest_days_24h} günü** otomatik kapatır.")
    
    c_data = []
    for doc in st.session_state.doctors:
        r = {"Doktor": doc}
        for d in range(1, num_days+1): r[str(d)] = st.session_state.manual_constraints.get(f"{doc}_{d}", "")
        c_data.append(r)
        
    col_cfg = {"Doktor": st.column_config.TextColumn(disabled=True)}
    for d in range(1, num_days+1):
        dn = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"][datetime(st.session_state.year, st.session_state.month, d).weekday()]
        col_cfg[str(d)] = st.column_config.SelectboxColumn(label=f"{d} {dn}", options=["", "24", "16", "X"], width="small")
        
    ed_cons = st.data_editor(pd.DataFrame(c_data), column_config=col_cfg, hide_index=True, use_container_width=True, key="cons_ed")
    
    updated = False
    for i, r in ed_cons.iterrows():
        doc = r["Doktor"]
        for d in range(1, num_days+1):
            val = str(r[str(d)])
            k = f"{doc}_{d}"
            if val != st.session_state.manual_constraints.get(k, ""):
                if val in ["24", "16", "X"]:
                    st.session_state.manual_constraints[k] = val
                    if val == "24": # Oto Blokaj
                        for off in range(1, rest_days_24h+1):
                            if d+off <= num_days: st.session_state.manual_constraints[f"{doc}_{d+off}"] = "X"
                else:
                    if k in st.session_state.manual_constraints: del st.session_state.manual_constraints[k]
                updated = True
    if updated: st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# TAB 4: HESAPLAMA
with t4:
    st.markdown('<div class="css-card">', unsafe_allow_html=True)
    if st.button("🚀 Nobetinator AI Çalıştır", type="primary", use_container_width=True):
        with st.spinner("Nobetinator hesaplıyor..."):
            model = cp_model.CpModel()
            docs = st.session_state.doctors
            days = range(1, num_days+1)
            x24, x16 = {}, {}

            # Değişken Tanımı
            for d in docs:
                for t in days:
                    x24[(d,t)] = model.NewBoolVar(f'x24_{d}_{t}')
                    x16[(d,t)] = model.NewBoolVar(f'x16_{d}_{t}')
                    model.Add(x24[(d,t)] + x16[(d,t)] <= 1)

            # 1. İhtiyaçlar (Sert Kısıt)
            for t in days:
                model.Add(sum(x24[(d,t)] for d in docs) == st.session_state.daily_needs_24h.get(t, 0))
                model.Add(sum(x16[(d,t)] for d in docs) == st.session_state.daily_needs_16h.get(t, 0))

            # 2. Dinlenme (Sert Kısıt)
            for d in docs:
                # Ertesi gün boş
                for t in range(1, num_days):
                    model.Add(x24[(d,t)] + x16[(d,t)] + x24[(d,t+1)] + x16[(d,t+1)] <= 1)
                # 24h sonrası blokaj
                win = rest_days_24h + 1
                for i in range(len(days) - win + 1):
                    wd = [days[j] for j in range(i, i+win)]
                    model.Add(sum(x24[(d,k)] for k in wd) <= 1)

            # 3. Manuel Kısıtlar (Sert Kısıt)
            for d in docs:
                for t in days:
                    c = st.session_state.manual_constraints.get(f"{d}_{t}", "")
                    if c == "24": model.Add(x24[(d,t)] == 1)
                    elif c == "16": model.Add(x16[(d,t)] == 1)
                    elif c == "X": 
                        model.Add(x24[(d,t)] == 0)
                        model.Add(x16[(d,t)] == 0)

            # 4. Kotalar (TAVAN SINIR MANTIĞI)
            deviations = []
            for d in docs:
                # 24h
                tot24 = sum(x24[(d,t)] for t in days)
                tgt24 = st.session_state.quotas_24h.get(d, 0)
                
                if "Katı" in solver_mode:
                    model.Add(tot24 <= tgt24) # Aşamaz
                else:
                    # Esnek Mod: ASLA AŞMA (<=), ama farkı minimize et
                    model.Add(tot24 <= tgt24) 
                    diff = model.NewIntVar(0, 31, f'd24_{d}')
                    model.Add(diff == tgt24 - tot24)
                    deviations.append(diff)
                
                # 16h
                tot16 = sum(x16[(d,t)] for t in days)
                tgt16 = st.session_state.quotas_16h.get(d, 0)
                
                if "Katı" in solver_mode:
                    model.Add(tot16 <= tgt16)
                else:
                    model.Add(tot16 <= tgt16)
                    diff = model.NewIntVar(0, 31, f'd16_{d}')
                    model.Add(diff == tgt16 - tot16)
                    deviations.append(diff)
            
            if "Esnek" in solver_mode:
                model.Minimize(sum(deviations))

            # Çözüm
            solver = cp_model.CpSolver()
            status = solver.Solve(model)

            if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
                st.success("✅ Nobetinator Başarıyla Çözdü!")
                
                # Veri Hazırlığı
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
                
                # İstatistik Tablosu
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
                
                # GÖSTERİM
                df_mx = pd.DataFrame(res_mx)
                df_ls = pd.DataFrame(res_lst)
                df_st = pd.DataFrame(stat_data)
                
                st.subheader("📊 Analiz Raporu")
                st.dataframe(df_st, use_container_width=True)
                
                vt1, vt2 = st.tabs(["Renkli Tablo", "Günlük Liste"])
                with vt1:
                    st.dataframe(df_mx.style.applymap(lambda v: 'background-color: #ff6b6b; color: white' if v=='24h' else ('background-color: #1dd1a1; color: white' if v=='16h' else '')), use_container_width=True)
                with vt2:
                    st.dataframe(df_ls, use_container_width=True)
                
                # EXCEL İNDİR
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
                    df_ls.to_excel(writer, sheet_name='Günlük Liste', index=False)
                    df_mx.to_excel(writer, sheet_name='Genel Çizelge', index=False)
                    df_st.to_excel(writer, sheet_name='İstatistik', index=False)
                    
                    # Format
                    wb = writer.book
                    ws = writer.sheets['Günlük Liste']
                    fmt = wb.add_format({'text_wrap': True, 'valign': 'top'})
                    ws.set_column('A:A', 15)
                    ws.set_column('B:C', 40, fmt)
                    
                st.download_button("📥 Nobetinator Excel'i İndir", buf.getvalue(), "nobetinator_cizelge.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")

            else:
                st.error("❌ Nobetinator Çözüm Bulamadı!")
                st.error("Sebep: Personel yetersizliği veya çakışan izinler (X) yüzünden matematiksel imkansızlık.")
    st.markdown('</div>', unsafe_allow_html=True)