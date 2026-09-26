"""Nobetinatör Ai portable sürümünü (tek klasör, EXE'li) üretir.

Kullanım:  python portable_olustur.py
Çıktı:     dist/Nobetinator/  (klasörü olduğu gibi kopyalayıp çalıştırabilirsiniz)

Adımlar:
  1. PyInstaller derlemesi (streamlit ve ortools tam toplanır; OR-Tools'un
     yerel DLL'leri ortools\\.libs altındadır, --collect-all bunları gömer).
  2. app.py + nobet_*.py dosyaları EXE'nin yanına kopyalanır.
  3. Nobetinator.exe --kontrol ile gömülü bağımlılık doğrulaması çalıştırılır.
"""
import shutil
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent
MODULLER = ["app.py", "nobet_tani.py", "nobet_on_inceleme.py", "nobet_rotasyon.py"]


def ana():
    komut = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--name", "Nobetinator",
        "--onedir",
        "--collect-all", "streamlit",
        "--collect-all", "ortools",
        # Uygulama bunları kullanmaz; Streamlit'in bağımlıları aracılığıyla
        # çekiliyorlar ve paketi gereksiz büyütüyorlar.
        "--exclude-module", "torch",
        "--exclude-module", "torchvision",
        "--exclude-module", "tensorflow",
        "--exclude-module", "tensorboard",
        "--exclude-module", "onnxruntime",
        str(KOK / "nobetinator_launcher.py"),
    ]
    print("Derleme basliyor (birkaç dakika surebilir)...")
    sonuc = subprocess.run(komut, cwd=KOK)
    if sonuc.returncode != 0:
        print("HATA: PyInstaller derlemesi basarisiz.")
        return 1

    hedef = KOK / "dist" / "Nobetinator"
    for ad in MODULLER:
        shutil.copy2(KOK / ad, hedef / ad)
    print("Uygulama modülleri EXE yanina kopyalandi:", ", ".join(MODULLER))

    print("Gömülü bagimlilik dogrulamasi (--kontrol)...")
    kontrol = subprocess.run([str(hedef / "Nobetinator.exe"), "--kontrol"],
                             capture_output=True, text=True)
    print(kontrol.stdout.strip() or kontrol.stderr.strip())
    if kontrol.returncode != 0:
        print("HATA: dogrulama basarisiz.")
        return 1
    print(f"TAMAM: {hedef}")
    return 0


if __name__ == "__main__":
    sys.exit(ana())
