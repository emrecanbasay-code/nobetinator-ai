import streamlit as st
import pandas as pd
from ortools.sat.python import cp_model
from datetime import datetime
import calendar
import io
import xlsxwriter

# ==========================================
# 👇 BURAYI KENDİNE GÖRE DÜZENLE (VERİ MERKEZİ)
# ==========================================

# 1. YIL VE AY AYARI
AYAR_YIL = 2026
AYAR_AY = 2  # Şubat

# 2. DOKTOR LİSTESİ (İsimleri tırnak içinde, virgülle ayırarak yaz)
DOKTORLAR = [
    "Dr. Ahmet",
    "Dr. Ayşe",
    "Dr. Mehmet",
    "Dr. Zeynep",
    "Dr. Can",
    "Dr. Burak"
]

# 3. KOTALAR (Her doktorun hedefi: [24h Sayısı, 16h Sayısı])
# Eğer bir doktor listede yoksa varsayılan 0 kabul edilir.
KOTALAR = {
    "Dr. Ahmet":  [5, 2],  # 5 tane 24h, 2 tane 16h
    "Dr. Ayşe":   [4, 3],
    "Dr. Mehmet": [6, 1],
    "Dr. Zeynep": [5, 2],
    "Dr. Can":    [4, 4],
    "Dr. Burak":  [3, 5]
}

# 4. SABİT KISITLAR (Özel durumlar)
# Format: "Doktor İsmi": {Gün: "Durum"}
# Durumlar: "X" (Yasak/İzin), "24" (Kesin Nöbet), "16" (Kesin 16h)
KISITLAR = {
    "Dr. Ahmet":  {14: "X", 15: "X"},      # Ahmet ayın 14-15'inde izinli
    "Dr. Ayşe":   {1: "24"},               # Ayşe ayın 1'inde kesin nöbetçi
    "Dr. Mehmet": {10: "X", 20: "X"},
    # Diğer doktorlar için satır ekleyebilirsin...
}

# 5. GÜNLÜK İHTİYAÇ (Hangi gün kaç kişi lazım?)
# Varsayılan: Her gün 1 nöbetçi (24h), 1 yardımcı (16h).
# Özel günler için aşağıya ekle: {Gün: [24h_sayısı, 16h_sayısı]}
GUNLUK_IHTIYAC_OZEL = {
    6: [2, 1],  # Ayın 6'sında 2 nöbetçi, 1 yardımcı lazım
    7: [2, 1],  # Ayın 7'sinde 2 nöbetçi, 1 yardımcı lazım
}

# ==========================================
# 👆 DÜZENLEME BİTTİ - AŞAĞISINA DOKUNMA ⛔
# ==========================================

st.set_page_config(page_title="Nobetinator Sabit", page_icon="🌑", layout="wide")

# --- CSS TASARIM ---
st.markdown("""
<style>
    .stApp { background-color: #0f172a !important; }
    h1, h2, h3, h4, h5, h6, p, span, div, label, li { color: #e2e8f0 !important; }
    .css-card { background-color: #1e293b; padding: 20px; border-radius: 12px; border: 1px solid #334155; margin-bottom: 20px; }
    .stButton>button { background-color: #3b82f6 !important; color: white !important; border-radius: 8px; width: 100%; border:none; padding:10px; font-weight:bold;}
    .stButton>button:hover { background-color: #2563eb !important; }
    div[data-testid="stMetric"] { background-color: #1e293b; border: 1px solid #334155; border-radius: 10px; text-align: center; }
    div[data-testid="stDataEditor"] { background-color: #1e293b; }
</style>
""", unsafe_allow_html=True)

# --- VERİLERİ YÜKLE ---
if 'initialized' not in st.session_state:
    st.session_state.year = AYAR_YIL
    st.session_state.month = AYAR_AY
    st.session_state.doctors = DOKTORLAR
    st.session_state.quotas_24h = {d: KOTALAR.get(d, [0,0])[0] for d in DOKTORLAR}
    st.session_state.quotas_16h = {d: KOTALAR.get(d, [0,0])[1] for d in DOKTORLAR}
    st.session_state.manual_constraints = {}
    
    # Kısıtları düzleştir
    for doc, days in KISITLAR.items():
        for d, val in days.items():
            st.session_state.manual_constraints[f"{doc}_{d}"] = val
            
    # Günlük ihtiyaçları hazırla
    num_days = calendar.monthrange(AYAR_YIL, AYAR_AY)[1]
    st.session_state.daily_needs_24h = {}
    st.session_state.daily_needs_16h = {}
    for d in range(1, num_days + 1):
        defaults = GUNLUK_IHTIYAC_OZEL.get(d, [1, 1])
        st.session_state.daily_needs_24h[d] = defaults[0]
        st.session_state.daily_needs_16h[d] = defaults[1]
        
    st.session_state.initialized = True

num_days = calendar.monthrange(st.session_state.year, st.session_state.month)[1]

# --- SIDEBAR ---
with st.sidebar:
    st.title("🌑 Sabit Mod")
    st.info(f"📅 {calendar.month_name[st.session_state.month]} {st.session_state.year}")
    st.success(f"👨‍⚕️ {len(st.session_state.doctors)} Kişilik Kadro Yüklendi")
    
    st.markdown("---")
    st.subheader("⚙️ Ayarlar")
    rest_days_24h = st.slider("24h Sonrası Yasak", 1, 5, 2)
    solver_mode = st.radio("Hesaplama Modu", ["Katı (Tam Hedef)", "Esnek (En İyi Çaba)"], index=1)
    
    if st.button("Verileri Sıfırla / Koddan Tekrar Oku"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

# --- ANA EKRAN ---
st.markdown(f"### 🗓️ Nöbet Planlayıcı: {calendar.month_name[st.session_state.month]}")

t1, t2, t3 = st.tabs(["📊 DURUM ÖZETİ", "📝 DETAYLI TABLO (Görüntüle)", "🚀 HESAPLA"])

with t1:
    # Basit İstatistikler
    c1, c2, c3 = st.columns(3)
    toplam_ih_24 = sum(st.session_state.daily_needs_24h.values())
    toplam_kot_24 = sum(st.session_state.quotas_24h.values())
    
    c1.metric("Toplam 24h İhtiyacı", toplam_ih_24)
    c2.metric("Doktorların Toplam Kotası", toplam_kot_24, delta=toplam_kot_24-toplam_ih_24)
    c3.metric("Kayıtlı Özel Kısıt", len(st.session_state.manual_constraints))
    
    st.markdown("##### Doktor Hedefleri")
    df_goals = pd.DataFrame({
        "Doktor": st.session_state.doctors,
        "Hedef 24h": [st.session_state.quotas_24h[d] for d in st.session_state.doctors],
        "Hedef 16h": [st.session_state.quotas_16h[d] for d in st.session_state.doctors]
    })
    st.dataframe(df_goals, use_container_width=True, hide_index=True)

with t2:
    st.write("Kod içine girdiğin kısıtların tablo görünümü:")
    # Kısıt Tablosu Oluşturma
    c_data = []
    for doc in st.session_state.doctors:
        row = {"Doktor": doc}
        for d in range(1, num_days+1):
            key = f"{doc}_{d}"
            val = st.session_state.manual_constraints.get(key, "")
            row[str(d)] = val
        c_data.append(row)
    
    df_cons = pd.DataFrame(c_data)
    st.dataframe(df_cons, use_container_width=True, hide_index=True)

with t3:
    st.markdown('<div class="css-card">', unsafe_allow_html=True)
    if st.button("🚀 NÖBETLERİ DAĞIT", type="primary"):
        with st.spinner("AI Hesaplıyor..."):
            model = cp_model.CpModel()
            docs = st.session_state.doctors
            days = range(1, num_days+1)
            x24, x16 = {}, {}

            # Değişkenler
            for d in docs:
                for t in days:
                    x24[(d,t)] = model.NewBoolVar(f'x24_{d}_{t}')
                    x16[(d,t)] = model.NewBoolVar(f'x16_{d}_{t}')
                    model.Add(x24[(d,t)] + x16[(d,t)] <= 1) # Aynı gün hem 24 hem 16 olamaz

            # İhtiyaçlar
            for t in days:
                n24 = st.session_state.daily_needs_24h.get(t, 1)
                n16 = st.session_state.daily_needs_16h.get(t, 1)
                model.Add(sum(x24[(d,t)] for d in docs) == n24)
                model.Add(sum(x16[(d,t)] for d in docs) == n16)

            # Dinlenme Kuralları
            for d in docs:
                # Arka arkaya gün yasağı (genel)
                for t in range(1, num_days):
                     model.Add(x24[(d,t)] + x16[(d,t)] + x24[(d,t+1)] + x16[(d,t+1)] <= 1)
                
                # 24h sonrası uzun dinlenme
                win = rest_days_24h + 1
                for i in range(len(days) - win + 1):
                    wd = [days[j] for j in range(i, i+win)]
                    model.Add(sum(x24[(d,k)] for k in wd) <= 1)

            # Manuel Kısıtlar (Koddan gelenler)
            for d in docs:
                for t in days:
                    c = st.session_state.manual_constraints.get(f"{d}_{t}", "")
                    if c == "24": model.Add(x24[(d,t)] == 1)
                    elif c == "16": model.Add(x16[(d,t)] == 1)
                    elif c == "X": 
                        model.Add(x24[(d,t)] == 0)
                        model.Add(x16[(d,t)] == 0)

            # Hedefler (Sapmayı minimize et)
            deviations = []
            for d in docs:
                # 24h Kotası
                total_24 = sum(x24[(d,t)] for t in days)
                target_24 = st.session_state.quotas_24h.get(d, 0)
                
                if "Katı" in solver_mode:
                    model.Add(total_24 <= target_24) # Asla geçme
                else:
                    # Esnek: Hedefe yaklaşmaya çalış
                    diff_24 = model.NewIntVar(0, 31, f'diff24_{d}')
                    # Mutlak değer farkı yerine basit fark karesi simülasyonu veya alt/üst limit
                    # Basit yöntem: Target ile Total arasındaki farkı değişkene ata
                    # model.AddAbsEquality(diff_24, total_24 - target_24) # AbsEquality bazen yavaştır
                    # Basitleştirilmiş: Sadece tavanı delme maliyeti ekleyelim veya tam eşitlik isteyelim
                    model.Add(total_24 <= target_24 + 1) # En fazla 1 sapmaya izin ver
                    model.Add(total_24 >= target_24 - 1)
                    
                    # Hedefin kendisine eşitlemeye çalış
                    delta = model.NewIntVar(0, 31, f'd_{d}')
                    model.AddAbsEquality(delta, total_24 - target_24)
                    deviations.append(delta)

                # 16h Kotası (Aynı mantık)
                total_16 = sum(x16[(d,t)] for t in days)
                target_16 = st.session_state.quotas_16h.get(d, 0)
                if "Katı" in solver_mode:
                    model.Add(total_16 <= target_16)
                else:
                    delta16 = model.NewIntVar(0, 31, f'd16_{d}')
                    model.AddAbsEquality(delta16, total_16 - target_16)
                    deviations.append(delta16)

            if "Esnek" in solver_mode:
                model.Minimize(sum(deviations))

            # Çöz
            solver = cp_model.CpSolver()
            status = solver.Solve(model)

            if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
                st.success("✅ Çizelge Hazırlandı!")
                
                # Sonuçları Hazırla
                res_list = []
                res_matrix = []
                stats = {d: {"24h":0, "16h":0} for d in docs}
                
                for t in days:
                    dt = datetime(st.session_state.year, st.session_state.month, t)
                    day_str = f"{t:02d} {['Pzt','Sal','Çar','Per','Cum','Cmt','Paz'][dt.weekday()]}"
                    
                    row_mat = {"Tarih": day_str}
                    l24, l16 = [], []
                    
                    for d in docs:
                        if solver.Value(x24[(d,t)]):
                            row_mat[d] = "24h"
                            stats[d]["24h"] += 1
                            l24.append(d)
                        elif solver.Value(x16[(d,t)]):
                            row_mat[d] = "16h"
                            stats[d]["16h"] += 1
                            l16.append(d)
                        else:
                            row_mat[d] = ""
                    
                    res_matrix.append(row_mat)
                    res_list.append({
                        "Gün": t,
                        "Tarih": day_str,
                        "24 Saat Nöbetçileri": ", ".join(l24),
                        "16 Saat Yardımcıları": ", ".join(l16)
                    })
                
                # İstatistik Tablosu
                df_stats = pd.DataFrame([
                    {
                        "Doktor": d,
                        "24h (Hedef)": st.session_state.quotas_24h[d],
                        "24h (Gerçek)": stats[d]["24h"],
                        "16h (Hedef)": st.session_state.quotas_16h[d],
                        "16h (Gerçek)": stats[d]["16h"]
                    } for d in docs
                ])
                
                st.write("### 📊 Sonuç Özeti")
                st.dataframe(df_stats, use_container_width=True)
                
                st.write("### 📅 Çizelge")
                df_mx = pd.DataFrame(res_matrix)
                # Renklendirme fonksiyonu
                def color_schedule(val):
                    if val == '24h': return 'background-color: #dc2626; color: white'
                    elif val == '16h': return 'background-color: #16a34a; color: white'
                    return ''
                st.dataframe(df_mx.style.applymap(color_schedule), use_container_width=True)

                # Excel İndir
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    pd.DataFrame(res_list).to_excel(writer, sheet_name='Liste', index=False)
                    df_mx.to_excel(writer, sheet_name='Tablo', index=False)
                    df_stats.to_excel(writer, sheet_name='Istatistik', index=False)
                
                st.download_button(
                    label="📥 Excel Dosyasını İndir",
                    data=buffer.getvalue(),
                    file_name="nobet_listesi_sabit.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

            else:
                st.error("⚠️ Çözüm bulunamadı! Kurallar çok sıkı olabilir. Kısıtları gevşetin veya 'Esnek Mod' deneyin.")
    st.markdown('</div>', unsafe_allow_html=True)
