#!/usr/bin/env python3
"""Monta o pacote e o instalador do PULSE — System Telemetry a partir deste repositório.

O que faz:
  1. baixa o turing-smart-screen-python (só as partes usadas: programa, LibreHardwareMonitor,
     fontes e temas de 3,5") na versão testada;
  2. aplica pequenos ajustes no main.py (a bandeja fica com o painel e a troca de tema é feita sem reiniciar);
  3. junta com o código deste repositório (painel/, sensores/, instalador/);
  4. gera em dist/:
       PULSE-<versão>.zip   pacote com Instalar.bat (instalação manual)
       PULSE-Setup.exe      instalador (precisa do NSIS: "apt install nsis" ou "choco install nsis")

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


AJUSTES_MAIN = [
    # o ícone da bandeja passa a ser o do painel (painel/iniciar.py)
    ("    try:\n        tray_icon = pystray.Icon(",
     "    try:\n"
     "        if os.environ.get(\"PAINEL_SEM_BANDEJA\"):  # PULSE: o ícone fica com o painel/iniciar.py\n"
     "            raise RuntimeError(\"bandeja do PULSE\")\n"
     "        tray_icon = pystray.Icon("),
    # troca de tema sem reiniciar: precisa entrar antes do agendador ler os intervalos do tema
    ("    import library.scheduler as scheduler\n",
     "    try:  # PULSE: troca de tema e brilho sem reiniciar (painel/troca_tema.py)\n"
     "        import painel.troca_tema as troca_tema\n"
     "    except Exception as e:\n"
     "        troca_tema = None\n"
     "        print(\"Troca rápida de tema indisponível:\", e)\n"
     "    import library.scheduler as scheduler\n"),
    ("    scheduler.PingStats(); time.sleep(0.25)\n",
     "    scheduler.PingStats(); time.sleep(0.25)\n"
     "    if troca_tema:\n"
     "        troca_tema.iniciar(display)\n"),
    # conexão com a tela USB que espera, reconecta e explica (painel/tela_usb.py): precisa entrar antes
    # de qualquer import que abra a porta (library.display abre a porta já no import)
    ("    from library.log import logger\n",
     "    from library.log import logger\n"
     "    try:  # PULSE: conexão com a tela USB que espera, reconecta e explica (painel/tela_usb.py)\n"
     "        import painel.tela_usb as tela_usb\n"
     "        tela_usb.instalar()\n"
     "    except Exception as e:\n"
     "        tela_usb = None\n"
     "        logger.exception(\"Conexão robusta com a tela indisponível: %s\", e)\n"),
    ("    display.initialize_display()\n",
     "    display.initialize_display()\n"
     "    if tela_usb:\n"
     "        tela_usb.tela_inicializada(display)\n"),
    ("    # Create all static images\n    display.display_static_images()\n",
     "    # Create all static images\n"
     "    if tela_usb:\n"
     "        tela_usb.envio_iniciado()\n"
     "    display.display_static_images()\n"),
    ("    wait_for_empty_queue(10)\n",
     "    wait_for_empty_queue(10)\n"
     "    if tela_usb:\n"
     "        tela_usb.envio_concluido(display, scheduler.is_queue_empty())\n"),
]

# Sem administrador o LibreHardwareMonitor não lê alguns sensores (temperatura da CPU, por exemplo), e a
# biblioteca fechava o programa da tela sem aviso: a tela ficava apagada. Agora ela só avisa e segue com
# o que der para ler. Com administrador (o normal, pela tarefa "PainelTelemetria") nada muda.
AJUSTES_LHM = [
    ("if ctypes.windll.shell32.IsUserAnAdmin() == 0:\n"
     "    logger.error(\n"
     "        \"Program is not running as administrator. Please run with admin rights or choose another HW_SENSORS option in \"\n"
     "        \"config.yaml\")\n"
     "    try:\n"
     "        sys.exit(0)\n"
     "    except:\n"
     "        os._exit(0)\n",
     "if ctypes.windll.shell32.IsUserAnAdmin() == 0:\n"
     "    # PULSE: sem administrador a tela continua; só as leituras que exigem admin ficam vazias\n"
     "    logger.warning(\n"
     "        \"Sem permissão de administrador: a tela continua, mas leituras como a temperatura da CPU podem ficar \"\n"
     "        \"vazias. Abra o PULSE pelo atalho ou reinicie o PC (a tarefa 'PainelTelemetria' roda como administrador).\")\n"),
]


def _ajustar(arq: Path, ajustes):
    texto = arq.read_text(encoding="utf-8")
    for antes, depois in ajustes:
        if depois in texto:
            continue
        if texto.count(antes) != 1:
            sys.exit(f"{arq.name} do turing-smart-screen-python mudou: revise os ajustes em scripts/montar_pacote.py")
        texto = texto.replace(antes, depois, 1)
    arq.write_text(texto, encoding="utf-8", newline="")


def ajustar_main(app: Path):
    """Pequenos ajustes no código original (ver AJUSTES_MAIN e AJUSTES_LHM)."""
    _ajustar(app / "main.py", AJUSTES_MAIN)
    _ajustar(app / "library" / "sensors" / "sensors_librehardwaremonitor.py", AJUSTES_LHM)


def montar_pacote(upstream: Path) -> Path:
    pacote = BUILD / "pacote"
    print(f"Montando {pacote}...")
    shutil.rmtree(pacote, ignore_errors=True)
    app = pacote / "app"
    # *_preview.png: amostras das fontes (só servem para a documentação original)
    shutil.copytree(upstream, app, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", "*_preview.png"))
    ajustar_main(app)
    shutil.copytree(RAIZ / "painel", app / "painel", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (app / "painel" / "versao.txt").write_text(versao(), encoding="utf-8")   # mostrada na tela Sobre
    shutil.copy2(RAIZ / "sensores" / "sensors_custom.py", app / "library" / "sensors" / "sensors_custom.py")
    shutil.copy2(RAIZ / "sensores" / "sensors_custom.py", pacote / "sensors_custom.py")
    for nome in ARQUIVOS_INSTALADOR:
        shutil.copy2(RAIZ / "instalador" / nome, pacote / nome)
    shutil.copytree(RAIZ / "instalador" / "wheels", pacote / "wheels")
    return pacote


def gerar_zip(pacote: Path, ver: str) -> Path:
    DIST.mkdir(exist_ok=True)
    nome = f"PULSE-{ver}"
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
    for bmp in ("pulse_instalador_lateral.bmp", "pulse_instalador_cabecalho.bmp"):
        shutil.copy2(RAIZ / "instalador" / bmp, BUILD / bmp)
    rodar(makensis, "-INPUTCHARSET", "UTF8", "-V2", "setup.nsi", cwd=BUILD)
    DIST.mkdir(exist_ok=True)
    destino = DIST / "PULSE-Setup.exe"
    shutil.move(BUILD / "PULSE-Setup.exe", destino)
    print(f"Instalador: {destino} ({destino.stat().st_size / 1e6:.1f} MB)")
    return destino


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sem-setup", action="store_true", help="não gera o PULSE-Setup.exe")
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
