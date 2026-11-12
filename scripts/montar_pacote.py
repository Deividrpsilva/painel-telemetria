#!/usr/bin/env python3
"""Monta o pacote e o instalador do Painel de Telemetria a partir deste repositório.

O que faz:
  1. baixa o turing-smart-screen-python (só as partes usadas: programa, LibreHardwareMonitor,
     fontes e temas de 3,5") na versão testada;
  2. aplica o pequeno ajuste no main.py (o ícone da bandeja passa a ser o do painel);
  3. junta com o código deste repositório (painel/, sensores/, instalador/);
  4. gera em dist/:
       PainelTelemetria-<versão>.zip   pacote com Instalar.bat (instalação manual)
       PainelTelemetria-Setup.exe      instalador (precisa do NSIS: "apt install nsis" ou "choco install nsis")

Uso (na raiz do repositório):
  python scripts/montar_pacote.py                 tudo
  python scripts/montar_pacote.py --sem-setup     só o .zip
  python scripts/montar_pacote.py --upstream DIR  usa uma cópia local do turing-smart-screen-python
"""
import argparse
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BUILD = RAIZ / "build"
DIST = RAIZ / "dist"

UPSTREAM_URL = "https://github.com/mathoudebine/turing-smart-screen-python.git"
UPSTREAM_TAG = "3.10.0"

FONTES = ["digital", "geforce", "generale-mono", "jetbrains-mono", "roboto", "roboto-mono"]
TEMAS = [
    "3.5inchTheme2", "BigClock", "Cyberdeck", "Cyberpunk", "Cyberpunk-net", "Landscape6Grid", "LandscapeEarth",
    "LandscapeMagicBlue", "LandscapeModernDevice35", "SimpleBlue", "SimpleBlueFall",
    "SimpleBlueGauge", "SimpleCyberpunkGauge", "SimpleFire", "SimpleFireGauge", "SimpleGreen", "SimpleGreenFall",
    "SimpleGreenGauge", "SimpleMulticolor", "SimpleNeon", "SimpleNeonGauge", "SimpleOarngeFall", "SimpleOrange",
    "SimpleOrangeGauge", "SimplePurple", "SimplePurpleFall", "SimplePurpleGauge", "SimpleRed", "SimpleRedFall",
    "SimpleRedGauge", "SimpleRedGaugeRedBg", "SimpleYellow", "SimpleYellowFall", "SimpleYellowGauge", "Terminal",
    "bash-dark-green", "bash-dark-green-gpu",
]
# o que vem do repositório original (sparse checkout: evita baixar ~1,9 GB de temas, testes e docs)
PADROES = (["/*", "!/tests/", "!/tools/", "!/res/docs/", "!/res/fonts/*/", "!/res/themes/*",
            "/res/themes/default.yaml", "/res/themes/theme_example.yaml"]
           + [f"/res/fonts/{f}/" for f in FONTES] + [f"/res/themes/{t}/" for t in TEMAS])

ARQUIVOS_INSTALADOR = ["instalar.ps1", "desinstalar.ps1", "Instalar.bat", "Instalar (simulador).bat",
                       "Atualizar tema.bat", "LEIAME.txt", "requirements-painel.txt"]


def rodar(*cmd, **kw):
    print("  $", " ".join(str(c) for c in cmd))
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def versao():
    m = re.search(r'!define VERSAO "([^"]+)"', (RAIZ / "instalador" / "setup.nsi").read_text(encoding="utf-8"))
    return m.group(1) if m else "dev"


def baixar_upstream() -> Path:
    destino = BUILD / f"upstream-{UPSTREAM_TAG}"
    if (destino / "main.py").is_file():
        print(f"Usando {destino} (já baixado)")
        return destino
    print(f"Baixando turing-smart-screen-python {UPSTREAM_TAG} (só o necessário)...")
    shutil.rmtree(destino, ignore_errors=True)
    rodar("git", "clone", "--depth", "1", "--branch", UPSTREAM_TAG, "--filter=blob:none", "--no-checkout",
          UPSTREAM_URL, destino)
    rodar("git", "-C", destino, "sparse-checkout", "set", "--no-cone", *PADROES)
    rodar("git", "-C", destino, "checkout", UPSTREAM_TAG)
    return destino


def ajustar_main(app: Path):
    """main.py: não cria o ícone próprio na bandeja quando aberto pelo painel (painel/iniciar.py)."""
    arq = app / "main.py"
    texto = arq.read_text(encoding="utf-8")
    if "PAINEL_SEM_BANDEJA" in texto:
        return
    antes = "    try:\n        tray_icon = pystray.Icon("
    depois = ("    try:\n"
              "        if os.environ.get(\"PAINEL_SEM_BANDEJA\"):  # Painel de Telemetria: o ícone fica com o painel/iniciar.py\n"
              "            raise RuntimeError(\"bandeja do Painel de Telemetria\")\n"
              "        tray_icon = pystray.Icon(")
    if antes not in texto:
        sys.exit("main.py do turing-smart-screen-python mudou: revise ajustar_main() em scripts/montar_pacote.py")
    arq.write_text(texto.replace(antes, depois, 1), encoding="utf-8", newline="")


def montar_pacote(upstream: Path) -> Path:
    pacote = BUILD / "pacote"
    print(f"Montando {pacote}...")
    shutil.rmtree(pacote, ignore_errors=True)
    app = pacote / "app"
    # *_preview.png: amostras das fontes (só servem para a documentação original)
    shutil.copytree(upstream, app, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", "*_preview.png"))
    ajustar_main(app)
    shutil.copytree(RAIZ / "painel", app / "painel", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(RAIZ / "sensores" / "sensors_custom.py", app / "library" / "sensors" / "sensors_custom.py")
    shutil.copy2(RAIZ / "sensores" / "sensors_custom.py", pacote / "sensors_custom.py")
    for nome in ARQUIVOS_INSTALADOR:
        shutil.copy2(RAIZ / "instalador" / nome, pacote / nome)
    shutil.copytree(RAIZ / "instalador" / "wheels", pacote / "wheels")
    return pacote


def gerar_zip(pacote: Path, ver: str) -> Path:
    DIST.mkdir(exist_ok=True)
    nome = f"PainelTelemetria-{ver}"
    arq = DIST / f"{nome}.zip"
    with zipfile.ZipFile(arq, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(pacote.rglob("*")):
            if f.is_file():
                z.write(f, Path(nome) / f.relative_to(pacote))
    print(f"Pacote: {arq} ({arq.stat().st_size / 1e6:.1f} MB)")
    return arq


def gerar_setup(pacote: Path) -> Path:
    makensis = shutil.which("makensis")
    if not makensis:
        sys.exit("makensis não encontrado. Instale o NSIS (Linux: apt install nsis | Windows: choco install nsis)")
    shutil.copy2(RAIZ / "instalador" / "setup.nsi", BUILD / "setup.nsi")
    rodar(makensis, "-INPUTCHARSET", "UTF8", "-V2", "setup.nsi", cwd=BUILD)
    DIST.mkdir(exist_ok=True)
    destino = DIST / "PainelTelemetria-Setup.exe"
    shutil.move(BUILD / "PainelTelemetria-Setup.exe", destino)
    print(f"Instalador: {destino} ({destino.stat().st_size / 1e6:.1f} MB)")
    return destino


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sem-setup", action="store_true", help="não gera o PainelTelemetria-Setup.exe")
    ap.add_argument("--upstream", type=Path, help="pasta com o turing-smart-screen-python já baixado")
    a = ap.parse_args()
    BUILD.mkdir(exist_ok=True)
    upstream = a.upstream.resolve() if a.upstream else baixar_upstream()
    pacote = montar_pacote(upstream)
    ver = versao()
    gerar_zip(pacote, ver)
    if not a.sem_setup:
        gerar_setup(pacote)


if __name__ == "__main__":
    main()
