"""Nobetinatör Ai portatif başlatıcı.

Streamlit sunucusunu programatik başlatır, varsayılan tarayıcıyı açar ve
uygulamayı kapatma penceresi (konsol) gösterir. PyInstaller bu dosyayı
Nobetinator.exe'ye derler; app.py ve nobet_*.py dosyaları EXE'nin yanında durur.

Test yardımcıları: NOBETINATOR_PORT=sabit_port, NOBETINATOR_NO_BROWSER=1,
ve `Nobetinator.exe --kontrol` (gömülü bağımlılık + modül doğrulaması).
"""
import os
import socket
import sys
import threading
import webbrowser
from pathlib import Path

# Uygulama modülleri bunları çalışma anında içe aktarır; buradaki doğrudan
# içe aktarmalar PyInstaller'ın hepsini EXE'ye gömmesini sağlar.
import pandas  # noqa: F401
import openpyxl  # noqa: F401
import xlsxwriter  # noqa: F401
from ortools.sat.python import cp_model  # noqa: F401
import streamlit  # noqa: F401

UYGULAMA_MODULLERI = ("app.py", "nobet_tani.py", "nobet_on_inceleme.py", "nobet_rotasyon.py")
BASLIK = "Nobetinator Ai  -  UYGULAMAYI KAPATMAK ICIN BU PENCEREYI KAPATIN"


def uygulama_klasoru():
    donuk = getattr(sys, "frozen", False)
    return Path(sys.executable).parent if donuk else Path(__file__).parent


def bos_port_bul():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def kontrol_modu():
    """Gömülü bağımlılıklar ve uygulama modülleri tam mı? (otomatik doğrulama)"""
    import py_compile
    klasor = uygulama_klasoru()
    for ad in UYGULAMA_MODULLERI:
        py_compile.compile(str(klasor / ad), doraise=True)
    print("KONTROL: OK - tum bagimliliklar gomulu, uygulama modulleri derlendi.")
    return 0


def ana():
    if "--kontrol" in sys.argv:
        return kontrol_modu()

    klasor = uygulama_klasoru()
    app_yolu = klasor / "app.py"
    if not app_yolu.exists():
        print("HATA: app.py bulunamadi:", app_yolu)
        print("EXE'nin yaninda app.py ve nobet_*.py dosyalari bulunmalidir.")
        return 1

    port = int(os.environ.get("NOBETINATOR_PORT") or 0) or bos_port_bul()
    os.system(f"title {BASLIK}")

    tarayici_ac = os.environ.get("NOBETINATOR_NO_BROWSER") != "1"
    if tarayici_ac:
        threading.Timer(3.0, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()

    print("=" * 62)
    print("  Nobetinator Ai baslatiliyor...")
    print(f"  Tarayicinizda acilacak adres: http://127.0.0.1:{port}")
    print("  Uygulamayi kapatmak icin bu pencereyi kapatin (X) veya Ctrl+C.")
    print("=" * 62)

    # Ayarlar sunucu kurulmadan önce dogrudan yapilandirmaya yazilir;
    # flag_options / ortam degiskenleri bu Streamlit surumunde uygulanmiyor.
    from streamlit import config as st_config
    st_config.set_option("server.port", port)
    st_config.set_option("server.address", "127.0.0.1")
    st_config.set_option("server.headless", True)
    st_config.set_option("browser.gatherUsageStats", False)
    st_config.set_option("global.developmentMode", False)

    from streamlit.web import bootstrap
    bootstrap.run(str(app_yolu), False, [], {})
    return 0


if __name__ == "__main__":
    sys.exit(ana())
