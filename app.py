import streamlit as st
import pandas as pd
from ortools.sat.python import cp_model
import json
from datetime import datetime
import calendar
import io
import xlsxwriter

# -----------------------------------------------------------------------------
# 1. AYARLAR VE SAYFA YAPILANDIRMASI
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Nobetinatör Ai Pro",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -----------------------------------------------------------------------------
# 2. CSS TASARIMI
# -----------------------------------------------------------------------------
st.markdown("""
<style>
    .stApp { background-color: #0f172a; font-family: 'Segoe UI', sans-serif; }
    h1, h2, h3 { color: #f8fafc !important; }
    p, label, span, div { color: #cbd5e1; }
    [data-testid="stSidebar"] { background-color: #1e293b; border-right: 1px solid #334155; }
    .css-card {
        background-color: #1e293b; padding: 20px; border-radius: 12px;
        border: 1px solid #334155; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.3); margin-bottom: 20px;
    }
    div[data-testid="stMetric"] { background-color: #334155; border-radius: 8px; padding: 10px; border: 1px solid #475569; }
    div[data-testid="stMetricLabel"] > div { color: #94a3b8 !important; }
    div[data-testid="stMetricValue"] > div { color: #38bdf8 !important; }
    .stButton>button[kind="primary"] {
        background: linear-gradient(90deg, #3b82f6 0%, #2563eb 100%);
        border: none; box-shadow: 0 4px 10px rgba(37, 99, 235, 0.3);
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 3. VERİ YÖNETİMİ
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

# Varsayılan Kadro
VARSAYILAN_EKIP = [{"isim": f"Dr. {i}", "kota24": 8, "kota16": 0} for i in range(1, 21)]

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

if 'doctors' not in st.session_state: st.session_state.doctors = [k["isim"] for k in VARSAYILAN_EKIP]
if 'year' not in st.session_state: st.session_state.year = datetime.now().year
if 'month' not in st.session_state: st.session_state.month = datetime.now().month
if 'db' not in st.session_state: st.session_state.db = {}
if 'editor_key' not in st.session_state: st.session_state.editor_key = 0
if 'daily_needs_24h' not in st.session_state: load_month_data(st.session_state.year, st.session_state.month)

# -----------------------------------------------------------------------------
# 4. YAN MENÜ
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## 🏥 Nobetinatör Ai")
    
    # Tarih
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
    st.markdown("### ⚙️ Ayarlar")
    rest_days_24h = st.slider("24s Sonrası İzin", 1, 5, 2)
    calc_time = st.slider("Düşünme Süresi (sn)", 10, 60, 30)

    # --- ESNEK KISIT AYARI ---
    st.markdown("### 🚨 Acil Durum Modu")
    allow_break_constraints = st.checkbox(
        "Kısıtları Esnetmeye İzin Ver", 
        value=False,
        help="Eğer liste çözülemezse, kişilerin 'X' (İzinli) dediği günlere nöbet yazarak çözümü zorlar."
    )
    
    # --- YENİ EKLENEN: YEDEKLEME MODÜLÜ ---
    st.markdown("### 💾 Veri Yedekleme")
    with st.expander("JSON İçe/Dışa Aktar"):
        # 1. DIŞA AKTAR (EXPORT)
        export_data = {
            "version": "1.0",
            "year": st.session_state.year,
            "month": st.session_state.month,
            "doctors": st.session_state.doctors,
            "daily_needs_24h": st.session_state.daily_needs_24h,
            "daily_needs_16h": st.session_state.daily_needs_16h,
            "quotas_24h": st.session_state.quotas_24h,
            "quotas_16h": st.session_state.quotas_16h,
            "seniority": st.session_state.seniority,
            "manual_constraints": st.session_state.manual_constraints,
            "couples": st.session_state.couples
        }
        json_str = json.dumps(export_data, indent=4, ensure_ascii=False)
        st.download_button(
            label="💾 Bu Ayı Kaydet (JSON)",
            data=json_str,
            file_name=f"yedek_{st.session_state.year}_{st.session_state.month}.json",
            mime="application/json"
        )

        # 2. İÇE AKTAR (IMPORT)
        uploaded_file = st.file_uploader("📂 Yedek Yükle", type=["json"])
        if uploaded_file is not None:
            try:
                data = json.load(uploaded_file)
                # JSON integer key'leri string yapar, onları geri int yapmamız lazım:
                def keys_to_int(d): return {int(k) if k.isdigit() else k: v for k, v in d.items()}

                if "doctors" in data: st.session_state.doctors = data["doctors"]
                if "daily_needs_24h" in data: st.session_state.daily_needs_24h = keys_to_int(data["daily_needs_24h"])
                if "daily_needs_16h" in data: st.session_state.daily_needs_16h = keys_to_int(data["daily_needs_16h"])
                if "quotas_24h" in data: st.session_state.quotas_24h = data["quotas_24h"]
                if "quotas_16h" in data: st.session_state.quotas_16h = data["quotas_16h"]
                if "seniority" in data: st.session_state.seniority = data["seniority"]
                if "manual_constraints" in data: st.session_state.manual_constraints = data["manual_constraints"]
                if "couples" in data: st.session_state.couples = data["couples"]
                
                st.success("Veriler başarıyla yüklendi!")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"Hata: {e}")

    # ---------------------------------------
    
    with st.expander("❤️ Çiftler"):
        p1 = st.selectbox("Kişi 1", ["Seç"] + st.session_state.doctors, key="p1")
        p2 = st.selectbox("Kişi 2", ["Seç"] + st.session_state.doctors, key="p2")
        if st.button("Çift Ekle"):
            if p1 != "Seç" and p2 != "Seç" and p1 != p2:
                pair = sorted([p1, p2])
                if pair not in st.session_state.couples:
                    st.session_state.couples.append(pair)
                    st.rerun()
        
        for i, (d1, d2) in enumerate(st.session_state.couples):
            c_d1, c_d2 = st.columns([4,1])
            c_d1.text(f"{d1} & {d2}")
            if c_d2.button("🗑️", key=f"del_{i}"):
                st.session_state.couples.pop(i)
                st.rerun()

    with st.expander("👨‍⚕️ Personel"):
        new_d = st.text_input("Yeni İsim")
        if st.button("Ekle") and new_d:
            if new_d not in st.session_state.doctors:
                st.session_state.doctors.append(new_d)
                st.session_state.quotas_24h[new_d] = 0
                st.session_state.quotas_16h[new_d] = 0
                st.session_state.seniority[new_d] = "Orta"
                st.rerun()
        rem_d = st.selectbox("Sil", [""] + st.session_state.doctors)
        if st.button("Sil") and rem_d:
            st.session_state.doctors.remove(rem_d)
            st.rerun()

# -----------------------------------------------------------------------------
# 5. ANA EKRAN
# -----------------------------------------------------------------------------
st.title(f"🗓️ {calendar.month_name[st.session_state.month]} {st.session_state.year} Planlama")

m1, m2, m3, m4 = st.columns(4)
m1.metric("Gün Sayısı", num_days)
m2.metric("Personel", len(st.session_state.doctors))
m3.metric("Kısıtlar", len(st.session_state.manual_constraints))
m4.metric("Çiftler", len(st.session_state.couples))

tab1, tab2, tab3, tab4 = st.tabs(["📅 İhtiyaç", "🎯 Kotalar", "⛔ Kısıtlar", "🚀 Oluştur"])

# --- TAB 1: İHTİYAÇ ---
with tab1:
    st.markdown('<div class="css-card">', unsafe_allow_html=True)
    for d in range(1, num_days+1):
        if d not in st.session_state.daily_needs_24h: st.session_state.daily_needs_24h[d] = 1
        if d not in st.session_state.daily_needs_16h: st.session_state.daily_needs_16h[d] = 1
    
    data_n = [{"Gün": d, "🔴 24h": st.session_state.daily_needs_24h[d], "🟢 16h": st.session_state.daily_needs_16h[d]} for d in range(1, num_days+1)]
    ed_n = st.data_editor(pd.DataFrame(data_n), hide_index=True, use_container_width=True, height=500, key=f"n_{st.session_state.editor_key}")
    
    if st.button("İhtiyaçları Kaydet"):
        for _, r in ed_n.iterrows():
            st.session_state.daily_needs_24h[r["Gün"]] = r["🔴 24h"]
            st.session_state.daily_needs_16h[r["Gün"]] = r["🟢 16h"]
        st.success("Kaydedildi")
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# --- TAB 2: KOTA ---
with tab2:
    st.markdown('<div class="css-card">', unsafe_allow_html=True)
    data_q = []
    for d in st.session_state.doctors:
        data_q.append({
            "Doktor": d, 
            "Kıdem": st.session_state.seniority.get(d, "Orta"),
            "🔴 24h": st.session_state.quotas_24h.get(d, 0),
            "🟢 16h": st.session_state.quotas_16h.get(d, 0)
        })
    ed_q = st.data_editor(pd.DataFrame(data_q), hide_index=True, use_container_width=True, height=500, key=f"q_{st.session_state.editor_key}",
                          column_config={"Kıdem": st.column_config.SelectboxColumn(options=["Kıdemli","Orta","Çömez"])})
    
    if st.button("Kotaları Kaydet"):
        for _, r in ed_q.iterrows():
            doc = r["Doktor"]
            st.session_state.quotas_24h[doc] = r["🔴 24h"]
            st.session_state.quotas_16h[doc] = r["🟢 16h"]
            st.session_state.seniority[doc] = r["Kıdem"]
        st.success("Kaydedildi")
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# --- TAB 3: KISITLAR ---
with tab3:
    st.markdown('<div class="css-card">', unsafe_allow_html=True)
    c_b1, c_b2, c_b3 = st.columns([2, 3, 1])
    with c_b1:
        bd = st.selectbox("Doktor", st.session_state.doctors)
        bt = st.selectbox("Tip", ["❌ İzin", "🔴 24 Sabit", "🟢 16 Sabit", "🗑️ Sil"])
    with c_b2:
        bday = st.multiselect("Günler", [str(i) for i in range(1, num_days+1)])
    with c_b3:
        st.write("")
        st.write("")
        if st.button("Uygula"):
            val_map = {"❌ İzin": "X", "🔴 24 Sabit": "24", "🟢 16 Sabit": "16", "🗑️ Sil": ""}
            for day_str in bday:
                k = f"{bd}_{day_str}"
                v = val_map[bt]
                if v: st.session_state.manual_constraints[k] = v
                elif k in st.session_state.manual_constraints: del st.session_state.manual_constraints[k]
            st.session_state.editor_key += 1
            st.rerun()

    # Grid
    with st.expander("Tablo Görünümü", expanded=True):
        g_data = []
        for d in st.session_state.doctors:
            r = {"Doktor": d}
            for day in range(1, num_days+1):
                r[str(day)] = st.session_state.manual_constraints.get(f"{d}_{day}", "")
            g_data.append(r)
        
        cfg = {"Doktor": st.column_config.TextColumn(disabled=True)}
        for day in range(1, num_days+1): cfg[str(day)] = st.column_config.SelectboxColumn(options=["","X","24","16"], width="small")
        
        ed_g = st.data_editor(pd.DataFrame(g_data), hide_index=True, column_config=cfg, key=f"g_{st.session_state.editor_key}")
        if st.button("Tabloyu Güncelle"):
            for _, r in ed_g.iterrows():
                dc = r["Doktor"]
                for day in range(1, num_days+1):
                    v = r[str(day)]
                    k = f"{dc}_{day}"
                    if v: st.session_state.manual_constraints[k] = v
                    elif k in st.session_state.manual_constraints: del st.session_state.manual_constraints[k]
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# --- TAB 4: MOTOR ---
with tab4:
    st.markdown('<div class="css-card">', unsafe_allow_html=True)
    
    if allow_break_constraints:
        st.warning("⚠️ **Acil Durum Modu Aktif:** Yapay zeka, çözüm bulamazsa 'X' (İzin) kuralını delerek nöbet yazabilir.")

    if st.button("🚀 Çizelgeyi Oluştur", type="primary", use_container_width=True):
        
        pb = st.progress(0)
        stt = st.empty()
        stt.text("Model kuruluyor...")
        
        # --- OR-TOOLS MODELİ ---
        model = cp_model.CpModel()
        docs = st.session_state.doctors
        days = range(1, num_days+1)
        x24, x16 = {}, {}
        
        seniors = [d for d in docs if st.session_state.seniority.get(d) == "Kıdemli"]
        juniors = [d for d in docs if st.session_state.seniority.get(d) == "Çömez"]

        # Değişkenler
        for d in docs:
            for t in days:
                x24[(d,t)] = model.NewBoolVar(f'x24_{d}_{t}')
                x16[(d,t)] = model.NewBoolVar(f'x16_{d}_{t}')
                model.Add(x24[(d,t)] + x16[(d,t)] <= 1)

        # İhtiyaçlar
        for t in days:
            model.Add(sum(x24[(d,t)] for d in docs) == st.session_state.daily_needs_24h.get(t,1))
            model.Add(sum(x16[(d,t)] for d in docs) == st.session_state.daily_needs_16h.get(t,1))

        # Genel Kurallar
        for d in docs:
            # Peş peşe nöbet yok
            for t in range(1, num_days):
                model.Add(x24[(d,t)] + x16[(d,t)] + x24[(d,t+1)] + x16[(d,t+1)] <= 1)
            
            # 24h sonrası izin
            for t in days:
                for r in range(1, rest_days_24h + 1):
                    if t+r <= num_days:
                         model.Add(x24[(d,t+r)] + x16[(d,t+r)] == 0).OnlyEnforceIf(x24[(d,t)])

        penalties = []
        
        # --- MANUEL KISITLAR (Soft/Hard) ---
        for t in days:
            for d in docs:
                c = st.session_state.manual_constraints.get(f"{d}_{t}", "")
                if c == "24": model.Add(x24[(d,t)] == 1)
                elif c == "16": model.Add(x16[(d,t)] == 1)
                elif c == "X":
                    if not allow_break_constraints:
                        # Mod KAPALI: Sert kural
                        model.Add(x24[(d,t)] == 0)
                        model.Add(x16[(d,t)] == 0)
                    else:
                        # Mod AÇIK: Ceza puanlı kural
                        is_working = model.NewBoolVar(f'force_break_{d}_{t}')
                        model.Add(x24[(d,t)] + x16[(d,t)] == is_working)
                        penalties.append(is_working * 1000000) 

        # Homojen Dağılım (Haftalık Denge)
        weeks = [range(1, 8), range(8, 15), range(15, 22), range(22, num_days+1)]
        for d in docs:
            week_counts = []
            for w_idx, week_days in enumerate(weeks):
                valid_days = [t for t in week_days if t <= num_days]
                if not valid_days: continue
                wc = model.NewIntVar(0, 7, f'wc_{d}_{w_idx}')
                model.Add(wc == sum(x24[(d,t)] + x16[(d,t)] for t in valid_days))
                week_counts.append(wc)
            
            for i in range(len(week_counts) - 1):
                wdiff = model.NewIntVar(0, 7, f'wdiff_{d}_{i}')
                model.AddAbsEquality(wdiff, week_counts[i] - week_counts[i+1])
                penalties.append(wdiff * 20)
        
        # Kıdem Dengesi
        if seniors and juniors:
            for t in days:
                cnt_s = sum(x24[(d,t)] for d in seniors)
                cnt_j = sum(x24[(d,t)] for d in juniors)
                d_sj = model.NewIntVar(0, 10, f'dsj_{t}')
                model.AddAbsEquality(d_sj, cnt_s - cnt_j)
                penalties.append(d_sj * 5)

        # Kotalar
        for d in docs:
            # 24h
            w24 = sum(x24[(d,t)] for t in days)
            diff24 = model.NewIntVar(0, 31, f'd24_{d}')
            model.AddAbsEquality(diff24, w24 - st.session_state.quotas_24h.get(d, 0))
            penalties.append(diff24 * 500)
            
            # 16h
            w16 = sum(x16[(d,t)] for t in days)
            diff16 = model.NewIntVar(0, 31, f'd16_{d}')
            model.AddAbsEquality(diff16, w16 - st.session_state.quotas_16h.get(d, 0))
            penalties.append(diff16 * 500)

        # Çiftler
        for (d1, d2) in st.session_state.couples:
            if d1 in docs and d2 in docs:
                for t in days:
                    w1, w2 = model.NewBoolVar(f'w_{d1}_{t}'), model.NewBoolVar(f'w_{d2}_{t}')
                    model.Add(w1 == x24[(d1,t)] + x16[(d1,t)])
                    model.Add(w2 == x24[(d2,t)] + x16[(d2,t)])
                    mm = model.NewIntVar(0, 1, f'mm_{d1}_{d2}_{t}')
                    model.AddAbsEquality(mm, w1 - w2)
                    penalties.append(mm * 100)

        model.Minimize(sum(penalties))
        
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(calc_time)
        stt.text("AI Çözüm Arıyor...")
        pb.progress(50)
        
        status = solver.Solve(model)
        pb.progress(100)
        stt.empty()

        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            
            # İhlal Raporlama
            violation_msgs = []
            if allow_break_constraints:
                for t in days:
                    for d in docs:
                        c = st.session_state.manual_constraints.get(f"{d}_{t}", "")
                        if c == "X":
                            if solver.Value(x24[(d,t)]) == 1 or solver.Value(x16[(d,t)]) == 1:
                                shift_type = "24h" if solver.Value(x24[(d,t)]) else "16h"
                                violation_msgs.append(f"⚠️ **DİKKAT:** {d} kişisi {t}. gün izinli ('X') olmasına rağmen liste tamamlanamadığı için **{shift_type}** nöbeti yazıldı.")

            if violation_msgs:
                st.error("### 🚨 Zorunlu Kısıt İhlalleri Oluştu!")
                for msg in violation_msgs:
                    st.markdown(msg)
            elif allow_break_constraints:
                 st.success("✅ 'Esnek Mod' açık olmasına rağmen hiçbir izin kuralını delmeye gerek kalmadı!")
            else:
                 st.success("✅ Çözüm Başarılı")

            # Sonuçları Göster
            rows = []
            grid = []
            for t in days:
                dt = datetime(st.session_state.year, st.session_state.month, t)
                d_str = f"{t:02d} {['Pzt','Sal','Çar','Per','Cum','Cmt','Paz'][dt.weekday()]}"
                r_l = {"Tarih": d_str, "24h": [], "16h": []}
                r_g = {"Tarih": d_str}
                for d in docs:
                    v = ""
                    if solver.Value(x24[(d,t)]): v="24"; r_l["24h"].append(d)
                    elif solver.Value(x16[(d,t)]): v="16"; r_l["16h"].append(d)
                    r_g[d] = v
                rows.append({"Tarih": d_str, "24h Ekibi": ", ".join(r_l["24h"]), "16h Ekibi": ", ".join(r_l["16h"])})
                grid.append(r_g)
            
            df_res = pd.DataFrame(rows)
            df_grid = pd.DataFrame(grid)
            
            st.markdown("### 📊 Liste")
            st.dataframe(df_res, use_container_width=True)
            
            st.markdown("### 🌈 Çizelge")
            def color(val):
                if val=="24": return 'background-color: #ef4444; color: white'
                if val=="16": return 'background-color: #22c55e; color: white'
                return ''
            st.dataframe(df_grid.style.map(color), use_container_width=True)
            
            # Excel İndirme
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
                df_res.to_excel(writer, sheet_name='Liste', index=False)
                df_grid.to_excel(writer, sheet_name='Cizelge', index=False)
                
                # Excel Renklendirme
                wb = writer.book
                ws = writer.sheets['Cizelge']
                fmt_red = wb.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'})
                fmt_grn = wb.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100'})
                
                ws.conditional_format(1, 1, len(df_grid), len(docs), 
                                      {'type': 'text', 'criteria': 'containing', 'value': '24', 'format': fmt_red})
                ws.conditional_format(1, 1, len(df_grid), len(docs), 
                                      {'type': 'text', 'criteria': 'containing', 'value': '16', 'format': fmt_grn})

                if violation_msgs:
                     pd.DataFrame({"UYARILAR": violation_msgs}).to_excel(writer, sheet_name='IHLALLER', index=False)

            st.download_button("📥 Excel İndir", buf.getvalue(), "Nobet_Final.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")

        else:
            st.error("❌ Çözüm Bulunamadı!")
            if not allow_break_constraints:
                st.info("💡 **İpucu:** Yan menüden 'Kısıtları Esnetmeye İzin Ver' seçeneğini işaretleyip tekrar deneyin.")
    
    st.markdown('</div>', unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# import time modülü dosya başında eksikse diye ekleyelim
import time
