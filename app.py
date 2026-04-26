import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import pandas as pd

# ==========================================
# 1. SAYFA AYARLARI VE CSS
# ==========================================
st.set_page_config(page_title="Pro Hasta Takip v11 (Final)", layout="centered", page_icon="🏥")

st.markdown("""
<style>
    .stMarkdown { margin-bottom: -10px; }
    div[data-testid="column"] { align-items: center; display: flex; }
    .etiket-box {
        font-weight: bold; font-size: 13px; color: #0044cc;
        text-align: right; padding-right: 10px; width: 100%;
    }
    .stTextInput, .stNumberInput, .stDateInput, .stSelectbox { width: 100%; }
    .row-container { padding: 4px 0; border-bottom: 1px solid #eee; }
    div[data-testid="stCheckbox"] { display: flex; align-items: center; }
    /* Buton stilleri */
    .stButton>button { border-radius: 5px; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

st.title("🏥 Dikey Hızlı Veri Girişi (v11 - Tam Sürüm)")

# Checkbox Olarak Görünecek Başlıklar Listesi
CHECKBOX_LIST = [
    "1. Basamak Ybü", "2. Basamak Ybü", "3. Basamak Ybü", "Servis",
    "HT", "DM", "KBY", "KAH", "AF", "KOAH", "SVH", "Malignite", "KKY", "ALZHEİMER",
    "Entübasyon", "İnotrop", "Mükerrer tetkik Ya da tedavi istemi", 
    "Kesin tanı koyulamaması", "8 saati aşıp yatmaması", "Birden fazla kliniği ilgilendirmesi",
    "KOAG", "TİT", "TROP", "Hmg", "Bk", "Kan Gazı", "MALİYET", "Cr", "Ct", "Mr", "Usg",
    "Dahilye", "Göğüs Hast", "Genel Cerrahi", "Nrş", "KVC", "Kbb", "Plastik", "Göz", 
    "Üroloji", "Göğüs C.", "Kardiyoloji", "Nöroloji", "Göğüs H.", "Enfeksiyon H.", 
    "Psikiyatri", "Cildiye", "Anestezi", "Radyoloji",
    "08.00-16.00", "16.00-24.00", "00.00-08.00", "DEVİR", "Taburcu", "Ölüm", "T. RED"
]

# ==========================================
# 2. GOOGLE SHEETS BAĞLANTISI
# ==========================================
@st.cache_resource
def get_connection():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
    return gspread.authorize(creds)

def verileri_hazirla():
    client = get_connection()
    sh = client.open("Hasta_Takip_Sistemi")
    w_veri = sh.worksheet("Veri")
    w_liste = sh.worksheet("Liste")
    w_atlanan = sh.worksheet("Atlananlar")
    
    # --- BAŞLIKLARI DÜZELTME (1. ve 2. Satırı Birleştir) ---
    raw_headers = w_veri.get_all_values()
    row1 = raw_headers[0] # Üst başlıklar (Tarih vb.)
    row2 = raw_headers[1] # Alt başlıklar (İsim, Yaş vb.)
    
    headers = []
    max_len = max(len(row1), len(row2))
    
    for i in range(max_len):
        v1 = row1[i].strip() if i < len(row1) else ""
        v2 = row2[i].strip() if i < len(row2) else ""
        
        # 2. satır doluysa onu al, boşsa 1. satırı al
        final_header = v2 if v2 else v1
        # Satır sonu karakterlerini temizle
        headers.append(final_header.replace("\n", " ").strip())
        
    return w_veri, w_atlanan, headers, w_liste.get_all_values()

# Bağlantıyı başlat
try:
    w_veri, w_atlanan, headers, liste_rows = verileri_hazirla()
except Exception as e:
    st.error(f"Bağlantı Hatası: {e}")
    st.stop()

# ==========================================
# 3. SIDEBAR: GERİ AL (SİLME) İŞLEMİ
# ==========================================
with st.sidebar:
    st.header("⚙️ İşlemler")
    st.write("Son eklenen hatalı satırı silmek için:")
    if st.button("⏪ SON KAYDI SİL (GERİ AL)", type="primary", use_container_width=True):
        mevcut_veri = w_veri.get_all_values()
        # Başlık satırları (2 satır) hariç veri varsa sil
        if len(mevcut_veri) > 2:
            w_veri.delete_rows(len(mevcut_veri))
            st.success("✅ Son kayıt silindi.")
            time.sleep(1)
            st.rerun()
        else:
            st.warning("Silinecek veri yok.")

# ==========================================
# 4. HASTA SEÇİMİ VE VERİ HAZIRLIĞI
# ==========================================
with st.container():
    yapilacaklar = []
    # Liste.csv dosyası 4. satırdan (index 3) itibaren veri içeriyor
    for row in liste_rows[3:]:
        if len(row) > 10:
            # Sütun Haritası:
            # Index 4 (E): İsim
            # Index 6 (G): Tarih
            # Index 8 (I): Saat
            # Index 10 (K): Karar Süresi
            # Index 11 (L): Transfer Süresi
            
            p_isim = str(row[4]).strip()
            
            # Başlık satırı tekrarı veya boş satır değilse ekle
            if p_isim and "isim" not in p_isim.lower():
                yapilacaklar.append({
                    "isim": p_isim,
                    "tarih": str(row[6]).strip(),
                    "saat": str(row[8]).strip() if len(row) > 8 else "-",
                    "karar": str(row[10]).strip(),
                    "transfer": str(row[11]).strip()
                })

    if not yapilacaklar:
        st.success("🎉 Liste tamamlandı! Bekleyen hasta yok.")
        st.stop()

    st.info(f"Kalan Hasta Sayısı: **{len(yapilacaklar)}**")
    
    # Seçim Kutusu
    secenekler = [f"{x['isim']} | {x['tarih']}" for x in yapilacaklar]
    secilen_str = st.selectbox("👇 Sıradaki Hasta:", secenekler)
    
    # Seçilen objeyi bulma
    secilen_ad = secilen_str.split(" | ")[0]
    secilen_veri = next((x for x in yapilacaklar if x['isim'] == secilen_ad), None)
    
    # Bilgi Gösterimi ve Butonlar
    col_info, col_btn = st.columns([2, 1])
    col_info.warning(f"⏰ **Yatış Saati:** {secilen_veri['saat']}")
    
    # --- VERİLERİ DOLDUR BUTONU ---
    getir_btn = col_btn.button("⬇️ BİLGİLERİ DOLDUR", type="primary", use_container_width=True)

    # Butona basılınca State'i güncelle
    if getir_btn and secilen_veri:
        # Tarih Okuma (Dosyadan okurken)
        # Dosyada format: YYYY-MM-DD (2022-09-26)
        tarih_obj = datetime.now()
        d_str = secilen_veri['tarih'].split(" ")[0]
        
        try:
            # Önce Liste dosyasındaki formatı dene (YYYY-MM-DD)
            tarih_obj = datetime.strptime(d_str, "%Y-%m-%d")
        except:
            try:
                # Olmazsa Gün.Ay.Yıl dene
                tarih_obj = datetime.strptime(d_str, "%d.%m.%Y")
            except:
                # Hiçbiri olmazsa bugün kalsın
                tarih_obj = datetime.now()

        # Session State Güncelleme Döngüsü
        for idx, h in enumerate(headers):
            h_clean = h.lower().replace("İ", "i").replace("I", "ı")
            key_id = f"input_{idx}"
            
            # 1. İSİM (Liste E -> Veri İsim)
            if "isim" in h_clean or "adı soyadı" in h_clean:
                st.session_state[key_id] = secilen_veri['isim']
            
            # 2. TARİH (Liste G -> Veri Tarih)
            elif "tarih" in h_clean:
                st.session_state[key_id] = tarih_obj
                
            # 3. KARAR SÜRESİ (Liste K -> Veri Karar Süresi)
            elif "karar" in h_clean and "süre" in h_clean:
                st.session_state[key_id] = secilen_veri['karar']
                
            # 4. TRANSFER SÜRESİ (Liste L -> Veri Transfer Süresi)
            # "Transver" yazım hatasını da kapsar
            elif ("transfer" in h_clean or "transver" in h_clean) and "süre" in h_clean:
                st.session_state[key_id] = secilen_veri['transfer']

        st.toast(f"{secilen_veri['isim']} bilgileri form alanlarına taşındı!", icon="✅")

st.markdown("---")

# ==========================================
# 5. FORM OLUŞTURMA (DİNAMİK YAP)
# ==========================================
input_values = {}

with st.form("veri_giris_formu", clear_on_submit=False):
    st.write(f"### 📝 Kayıt Formu")
    
    for i, baslik in enumerate(headers):
        if not baslik.strip(): continue
        
        # Her kutucuğun benzersiz kimliği (ID)
        key_id = f"input_{i}"
        
        # State Başlatma (Eğer daha önce oluşturulmadıysa boş yarat)
        if key_id not in st.session_state:
            if "tarih" in baslik.lower(): 
                st.session_state[key_id] = datetime.now()
            elif baslik in CHECKBOX_LIST: 
                st.session_state[key_id] = False
            else: 
                st.session_state[key_id] = ""

        # Başlık temizliği ve küçük harf dönüşümü
        baslik_clean = baslik
        baslik_lower = baslik.lower().replace("İ", "i").replace("I", "ı")
        
        # Tasarım: Sol taraf Etiket, Sağ taraf Kutucuk
        c1, c2 = st.columns([1.5, 3])
        c1.markdown(f"<div class='etiket-box'>{baslik_clean}:</div>", unsafe_allow_html=True)
        
        with c2:
            # A. CHECKBOX OLANLAR (HT, DM, KOAH vs.)
            if baslik_clean in CHECKBOX_LIST:
                val = st.checkbox("Var", key=key_id)
                input_values[baslik] = 1 if val else 0
            
            # B. İSİM ALANI
            elif "isim" in baslik_lower or "adı soyadı" in baslik_lower:
                input_values[baslik] = st.text_input("İsim", key=key_id, label_visibility="collapsed")
            
            # C. TARİH ALANI (Önemli: format="DD.MM.YYYY" eklendi)
            elif "tarih" in baslik_lower:
                # State'den veriyi al, yoksa bugünü al
                val_date = st.session_state[key_id] if st.session_state[key_id] else datetime.now()
                input_values[baslik] = st.date_input(
                    "Tarih", 
                    value=val_date,
                    key=key_id, 
                    label_visibility="collapsed",
                    format="DD.MM.YYYY"  # <-- İstenilen Görüntü Formatı
                )
            
            # D. SÜRELER
            elif "süre" in baslik_lower and ("karar" in baslik_lower or "transver" in baslik_lower or "transfer" in baslik_lower):
                input_values[baslik] = st.text_input("Süre", key=key_id, label_visibility="collapsed")
            
            # E. CİNSİYET
            elif "cinsiyet" in baslik_lower:
                input_values[baslik] = st.selectbox("Cinsiyet", ["", "E", "K"], key=key_id, label_visibility="collapsed")
            
            # F. SAYISAL DEĞERLER (Yaş, Ateş, Nabız vb.)
            elif any(x in baslik_lower for x in ['yaş', 'ateş', 'nabız', 'tansiyon', 'spo2']):
                try:
                    current_val = float(st.session_state[key_id]) if st.session_state[key_id] else 0.0
                except:
                    current_val = 0
                input_values[baslik] = st.number_input("Değer", value=current_val, step=1.0, format="%.2f", key=f"num_{i}", label_visibility="collapsed")
            
            # G. NOT / AÇIKLAMA
            elif any(x in baslik_lower for x in ['açıklama', 'not']):
                input_values[baslik] = st.text_area("Not", key=key_id, height=70, label_visibility="collapsed")
            
            # H. DİĞER STANDART METİN ALANLARI
            else:
                input_values[baslik] = st.text_input("Sonuç", key=key_id, label_visibility="collapsed")

        st.markdown("<div class='row-container'></div>", unsafe_allow_html=True)

    st.markdown("---")
    
    # Alt Butonlar
    col_s1, col_s2 = st.columns([3, 1])
    kaydet_btn = col_s1.form_submit_button("✅ VERİYİ KAYDET", type="primary", use_container_width=True)

pas_gec_btn = st.button("🚫 PAS GEÇ (LİSTEDEN ATLA)", use_container_width=True)

# ==========================================
# 6. KAYIT VE PAS GEÇME MANTIĞI
# ==========================================
if kaydet_btn:
    try:
        yeni_satir = []
        for baslik in headers:
            if not baslik.strip():
                yeni_satir.append("")
            else:
                val = input_values.get(baslik, "")
                
                # Tarih verisini kaydederken Excel formatına (Gün.Ay.Yıl) çevir
                if isinstance(val, (datetime, pd.Timestamp)):
                    val = val.strftime("%d.%m.%Y")
                    
                yeni_satir.append(str(val))
        
        # Google Sheet'e yaz
        w_veri.append_row(yeni_satir)
        st.success("✅ Veri başarıyla kaydedildi!")
        
        # Formu temizlemek için Session State'deki inputları sil
        for key in st.session_state.keys():
            if key.startswith("input_"):
                del st.session_state[key]
        
        time.sleep(1)
        st.rerun()
    except Exception as e:
        st.error(f"Kayıt sırasında hata oluştu: {e}")

if pas_gec_btn:
    try:
        # Atlananlar sayfasına ekle: İsim ve Bugünün Tarihi
        w_atlanan.append_row([secilen_ad, datetime.now().strftime("%Y-%m-%d")])
        st.warning(f"⏩ {secilen_ad} pas geçildi.")
        time.sleep(1)
        st.rerun()
    except Exception as e:
        st.error(f"Pas geçme hatası: {e}")

