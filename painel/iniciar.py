# PULSE — System Telemetry - iniciador e ícone da bandeja
#
# É o que a tarefa "PainelTelemetria" abre ao entrar no Windows (como administrador, exigido
# pelo LibreHardwareMonitor). Ele:
#   1. mantém o programa da tela (main.py) rodando e o reabre se ele fechar;
#   2. troca o tema sozinho conforme o perfil (C:\PainelTelemetria\perfis.json):
#      - algum programa em TELA CHEIA (jogo) por alguns segundos  -> tema do perfil "Jogos";
#      - saiu da tela cheia por alguns segundos                   -> tema do perfil "Trabalho".
#      A troca só acontece quando muda de situação, então um tema escolhido à mão
#      fica na tela até o próximo jogo abrir ou fechar;
#   3. mostra o ícone na bandeja (perto do relógio, em "mostrar ícones ocultos") com atalhos
#      para abrir a configuração, trocar de perfil, mudar o brilho, reiniciar e sair;
#   4. recebe comandos em 127.0.0.1:5681 ("abrir", "aplicar", "reiniciar", "perfis", "sair", "ping")
#      da janela de configuração e do atalho "PULSE".
#   Trocar tema ou brilho não reinicia o main.py: o pedido vai para o painel/troca_tema.py, que roda
#   dentro dele (127.0.0.1:5682) e só redesenha a tela. Girar a tela 180° ainda reinicia.
# Rode a partir da pasta app:  pythonw painel/iniciar.py [--abrir]
import json
import logging
import os
import platform
import socket
import subprocess
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

PAINEL = Path(__file__).resolve().parent
APP = PAINEL.parent
DESTINO = APP.parent
PERFIS = DESTINO / "perfis.json"
CONFIG_YAML = APP / "config.yaml"
TEMAS_USUARIO = DESTINO / "temas"
PORTA_COMANDOS = 5681            # também impede dois iniciadores ao mesmo tempo
PORTA_CONFIG = 5680              # janela de configuração (painel/config_ui.py)
PORTA_MAIN = 5682                # main.py: troca de tema/brilho sem reiniciar (painel/troca_tema.py)
SIMULAR_JOGO = DESTINO / "simular_jogo.txt"   # para testes: se existir, finge que há um jogo em tela cheia
PEDIDO_REINICIO = DESTINO / ".reiniciar"      # alternativa ao comando "reiniciar"
SAIDA_MAIN = DESTINO / "main_saida.log"       # o que o main.py escreve fora do log (erros de import, tracebacks)
LOG_MAIN = APP / "log.log"                    # log da biblioteca da tela
ICONE_PNG = PAINEL / "pulse_tray.png"
WINDOWS = platform.system() == "Windows"

PERFIS_PADRAO = {"auto": True, "trabalho": "Meu_Trabalho", "jogos": "Meu_Jogos", "entrar_s": 5, "sair_s": 20}

sys.path.insert(0, str(PAINEL))
os.chdir(APP)
import tela_usb  # noqa: E402  (só as funções de estado: tela.json)

log = logging.getLogger("iniciar")


def _configurar_log():
    try:
        h = RotatingFileHandler(DESTINO / "iniciar.log", maxBytes=200_000, backupCount=1, encoding="utf-8")
    except OSError:
        h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%d/%m %H:%M:%S"))
    log.addHandler(h)
    log.setLevel(logging.INFO)


def ler_perfis():
    p = dict(PERFIS_PADRAO)
    try:
        p.update(json.loads(PERFIS.read_text(encoding="utf-8")))
    except FileNotFoundError:
        pass
    except Exception as e:
        log.info("perfis.json inválido: %s", e)
    return p


def gravar_perfis(p):
    PERFIS.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")


def enviar_comando(cmd, timeout=2.0):
    """Manda um comando para o iniciador. Devolve True se ele está rodando e respondeu."""
    try:
        with socket.create_connection(("127.0.0.1", PORTA_COMANDOS), timeout=timeout) as s:
            s.sendall((cmd + "\n").encode("utf-8"))
            return s.recv(16).startswith(b"ok")
    except OSError:
        return False


def enviar_main(cmd, timeout=15.0):
    """Manda um comando para o programa da tela (main.py). Devolve a resposta ou None."""
    try:
        with socket.create_connection(("127.0.0.1", PORTA_MAIN), timeout=timeout) as s:
            s.sendall((cmd + "\n").encode("utf-8"))
            return s.recv(64).decode("utf-8", "ignore").strip() or None
    except OSError:
        return None


def _pythonw():
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    return str(pyw if WINDOWS and pyw.exists() else exe)


# ------------------------------------------------------------------ tela cheia (Windows)
if WINDOWS:
    import ctypes
    from ctypes import wintypes

    _u32 = ctypes.windll.user32
    _u32.GetForegroundWindow.restype = wintypes.HWND
    _u32.MonitorFromWindow.restype = wintypes.HANDLE
    _u32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]

    class _MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    _IGNORAR = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Windows.UI.Core.CoreWindow",
                "ForegroundStaging", "MultitaskingViewFrame", "XamlExplorerHostIslandWindow", "LockScreenControllerProxyWindow"}

    def tela_cheia() -> bool:
        hwnd = _u32.GetForegroundWindow()
        if not hwnd or not _u32.IsWindowVisible(hwnd):
            return False
        nome = ctypes.create_unicode_buffer(256)
        _u32.GetClassNameW(hwnd, nome, 256)
        if nome.value in _IGNORAR:
            return False
        r = wintypes.RECT()
        if not _u32.GetWindowRect(hwnd, ctypes.byref(r)):
            return False
        mon = _u32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        if not _u32.GetMonitorInfoW(mon, ctypes.byref(mi)):
            return False
        m = mi.rcMonitor
        return r.left <= m.left and r.top <= m.top and r.right >= m.right and r.bottom >= m.bottom
else:
    def tela_cheia() -> bool:
        return False


def jogo_em_tela_cheia() -> bool:
    if SIMULAR_JOGO.exists():
        return True
    try:
        return tela_cheia()
    except Exception:
        return False


# ------------------------------------------------------------------ config.yaml e main.py
def _yaml():
    from ruamel.yaml import YAML
    y = YAML()
    y.preserve_quotes = True
    y.width = 4096
    return y


def tema_atual():
    with open(CONFIG_YAML, encoding="utf-8") as fh:
        return str(_yaml().load(fh)["config"].get("THEME", ""))


def definir_tema(pasta):
    y = _yaml()
    with open(CONFIG_YAML, encoding="utf-8") as fh:
        cfg = y.load(fh)
    cfg["config"]["THEME"] = pasta
    with open(CONFIG_YAML, "w", encoding="utf-8") as fh:
        y.dump(cfg, fh)


def ler_config():
    with open(CONFIG_YAML, encoding="utf-8") as fh:
        return _yaml().load(fh)


def definir_brilho(valor):
    y = _yaml()
    with open(CONFIG_YAML, encoding="utf-8") as fh:
        cfg = y.load(fh)
    cfg["display"]["BRIGHTNESS"] = int(valor)
    with open(CONFIG_YAML, "w", encoding="utf-8") as fh:
        y.dump(cfg, fh)


def nome_do_tema(pasta):
    try:
        return json.loads((TEMAS_USUARIO / f"{pasta}.json").read_text(encoding="utf-8")).get("nome") or pasta
    except Exception:
        return pasta


def abrir_main():
    # o ícone da bandeja é o deste iniciador; a saída do main.py vai para main_saida.log (no pythonw ela sumia)
    env = dict(os.environ, PAINEL_SEM_BANDEJA="1", PULSE_SAIDA="1", PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    try:
        saida = open(SAIDA_MAIN, "w", encoding="utf-8")
        saida.write(f"--- main.py aberto em {time.strftime('%d/%m %H:%M:%S')}\n")
        saida.flush()
    except OSError:
        saida = subprocess.DEVNULL
    try:
        if WINDOWS:
            return subprocess.Popen([_pythonw(), "main.py"], cwd=str(APP), env=env, stdout=saida,
                                    stderr=subprocess.STDOUT, creationflags=0x08000000)  # CREATE_NO_WINDOW
        return subprocess.Popen([sys.executable, "main.py"], cwd=str(APP), env=env, stdout=saida,
                                stderr=subprocess.STDOUT)
    finally:
        if saida is not subprocess.DEVNULL:
            saida.close()


def _tamanho(arq):
    try:
        return arq.stat().st_size
    except OSError:
        return 0


def _ler_trecho(arq, desde=0, maximo=64_000):
    try:
        with open(arq, "rb") as fh:
            tam = fh.seek(0, 2)
            if desde > tam:              # o log girou: lê do começo
                desde = 0
            fh.seek(max(desde, tam - maximo))
            dados = fh.read()
    except OSError:
        return []
    try:
        texto = dados.decode("utf-8")
    except UnicodeDecodeError:
        texto = dados.decode("cp1252" if WINDOWS else "latin-1", "replace")
    return [linha.strip() for linha in texto.splitlines() if linha.strip()]


def motivo_saida(log_desde):
    """Por que o main.py fechou: o último erro do log.log desta execução ou a última linha de um traceback."""
    linhas = _ler_trecho(LOG_MAIN, log_desde)
    saida = [x for x in _ler_trecho(SAIDA_MAIN) if not x.startswith("---")]

    def ultima(nivel):
        achadas = [x for x in linhas if nivel in x and "Too fast" not in x]
        return achadas[-1].split(nivel, 1)[1].strip()[:300] if achadas else ""

    erro_saida = next((x for x in reversed(saida) if "Error" in x or "error" in x or "Exception" in x), "")
    return (ultima("[CRITICAL]") or ultima("[ERROR]") or erro_saida[:300] or ultima("[WARNING]")
            or (saida[-1][:300] if saida else ""))


def config_aberta():
    try:
        with socket.create_connection(("127.0.0.1", PORTA_CONFIG), timeout=0.5):
            return True
    except OSError:
        return False


def abrir_configuracao():
    """Abre a janela de configuração, ou traz para a frente se já estiver aberta."""
    if WINDOWS:
        try:
            ctypes.windll.user32.AllowSetForegroundWindow(-1)  # ASFW_ANY
        except Exception:
            pass
    if config_aberta():
        try:
            import urllib.request
            urllib.request.urlopen(f"http://127.0.0.1:{PORTA_CONFIG}/api/focar", timeout=3).read()
            return
        except Exception as e:
            log.info("Não consegui focar a configuração: %s", e)
    kw = {"creationflags": 0x00000008 | 0x00000200} if WINDOWS else {"start_new_session": True}
    subprocess.Popen([_pythonw(), "painel/config_ui.py", "--janela"], cwd=str(APP),
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)


class Painel:
    def __init__(self):
        self.proc = None
        self.falhas = 0
        self.proxima_abertura = 0.0
        self.inicio_proc = 0.0
        self.em_jogo = False             # situação confirmada
        self.desde = None                # quando a situação começou a mudar
        self.perfis = ler_perfis()
        self.lido = 0.0
        self.tema = ""
        self.brilho = None
        self.icone = None
        self.reverso_em_uso = None       # DISPLAY_REVERSE com que o main.py abriu (mudar exige reiniciar)
        self.log_main_desde = 0          # tamanho do log.log quando o main.py abriu (para achar o erro desta vez)
        self.tela = ""                   # "Tela: funcionando (COM5)" (tela.json), mostrado na bandeja
        self.reinicio = threading.Event()
        self.fim = threading.Event()
        self.trava = threading.Lock()

    # ---------- estado (lido do disco a cada 3 s) ----------
    def atualizar_estado(self):
        antes = (self.tema, self.brilho, self.perfis.get("auto"), self.perfis.get("trabalho"), self.perfis.get("jogos"),
                 self.tela)
        self.perfis = ler_perfis()
        try:
            cfg = ler_config()
            self.tema = str(cfg["config"].get("THEME", ""))
            self.brilho = int(cfg["display"].get("BRIGHTNESS", 20))
        except Exception as e:
            log.info("config.yaml ilegível: %s", e)
        self.lido = time.monotonic()
        self.tela = tela_usb.resumo()
        depois = (self.tema, self.brilho, self.perfis.get("auto"), self.perfis.get("trabalho"), self.perfis.get("jogos"),
                  self.tela)
        if depois != antes:
            self.atualizar_icone()

    def atualizar_icone(self):
        if not self.icone:
            return
        try:
            rotulo = "Tema"
            if self.tema == self.perfis.get("jogos"):
                rotulo = "Perfil Jogos"
            elif self.tema == self.perfis.get("trabalho"):
                rotulo = "Perfil Trabalho"
            titulo = f"PULSE — System Telemetry\n{rotulo}: {nome_do_tema(self.tema)}"
            if self.tela:
                titulo += f"\n{self.tela}"
            self.icone.title = titulo[:127]
            self.icone.update_menu()
        except Exception as e:
            log.info("Falha ao atualizar o ícone: %s", e)

    # ---------- ações (menu da bandeja e comandos) ----------
    def pedir_reinicio(self):
        self.reinicio.set()

    def usar_perfil(self, perfil):
        alvo = self.perfis.get(perfil)
        if not alvo or not (APP / "res" / "themes" / alvo / "theme.yaml").is_file():
            log.info("Tema do perfil %s não encontrado: %s", perfil, alvo)
            return
        self.trocar_tema(alvo)

    def trocar_tema(self, alvo):
        """Troca na hora (main.py redesenha); se não der, reinicia o main.py."""
        with self.trava:
            definir_tema(alvo)
        r = enviar_main(f"tema {alvo}") if self.proc is not None else None
        if r != "ok":
            log.info("Troca rápida de tema indisponível (%s); reiniciando a tela", r)
            self.pedir_reinicio()
        self.atualizar_estado()

    def aplicar(self):
        """A configuração gravou o config.yaml (tema/brilho/girar): aplica do jeito mais rápido possível."""
        try:
            cfg = ler_config()
            tema = str(cfg["config"].get("THEME", ""))
            brilho = int(cfg["display"].get("BRIGHTNESS", 20))
            reverso = bool(cfg["display"].get("DISPLAY_REVERSE", False))
        except Exception as e:
            log.info("config.yaml ilegível: %s", e)
            self.pedir_reinicio()
            return
        r = None
        if self.proc is not None and reverso == self.reverso_em_uso:
            r = enviar_main(f"tema {tema}")
            if r == "ok":
                r = enviar_main(f"brilho {brilho}")
        if r != "ok":
            self.pedir_reinicio()
        self.atualizar_estado()

    def alternar_auto(self):
        p = ler_perfis()
        p["auto"] = not p.get("auto")
        gravar_perfis(p)
        self.desde = None
        self.atualizar_estado()

    def mudar_brilho(self, valor):
        with self.trava:
            definir_brilho(valor)
        if self.proc is None or enviar_main(f"brilho {valor}") != "ok":
            self.pedir_reinicio()
        self.atualizar_estado()

    def sair(self):
        log.info("Saindo pelo menu da bandeja.")
        self.fim.set()
        if self.icone:
            self.icone.stop()

    # ---------- laço principal ----------
    def laco(self):
        from parar_painel import parar_main
        while not self.fim.is_set():
            try:
                self.passo(parar_main)
            except Exception:
                log.exception("Erro no laço do iniciador")
            self.fim.wait(1)
        if self.proc is not None:
            parar_main()

    def passo(self, parar_main):
        agora = time.monotonic()
        if agora - self.lido > 3:
            self.atualizar_estado()
        pedido = self.reinicio.is_set()
        self.reinicio.clear()
        if PEDIDO_REINICIO.exists():
            PEDIDO_REINICIO.unlink(missing_ok=True)
            pedido = True

        # --- perfis automáticos
        if self.perfis.get("auto"):
            jogo = jogo_em_tela_cheia()
            if jogo != self.em_jogo:
                self.desde = self.desde or agora
                espera = float(self.perfis.get("entrar_s" if jogo else "sair_s", 5 if jogo else 20))
                if agora - self.desde >= espera:
                    self.em_jogo, self.desde = jogo, None
                    alvo = self.perfis.get("jogos" if jogo else "trabalho")
                    try:
                        if alvo and (APP / "res" / "themes" / alvo / "theme.yaml").is_file() and tema_atual() != alvo:
                            log.info("%s -> tema %s", "Jogo em tela cheia" if jogo else "Saiu do jogo", alvo)
                            with self.trava:
                                definir_tema(alvo)
                            if self.proc is None or enviar_main(f"tema {alvo}") != "ok":
                                pedido = True
                            self.atualizar_estado()
                    except Exception as e:
                        log.info("Falha ao trocar de tema: %s", e)
            else:
                self.desde = None
        else:
            self.desde = None

        # --- reinício pedido (tema/brilho trocado): fecha e reabre logo, sem contar como falha
        if pedido:
            if self.proc is not None:
                parar_main()
                try:
                    self.proc.wait(5)
                except Exception:
                    pass
                self.proc = None
            time.sleep(1.0)            # libera a porta da tela
            self.proxima_abertura = 0.0
            agora = time.monotonic()

        # --- mantém o main.py rodando
        if self.proc is not None and self.proc.poll() is not None:
            codigo = self.proc.returncode
            self.proc = None
            vida = agora - self.inicio_proc
            self.falhas = 0 if vida > 60 else self.falhas + 1
            espera = min(60, 2 * (2 ** min(self.falhas, 5))) if self.falhas else 1.5
            if codigo == tela_usb.CODIGO_RECONECTAR and self.falhas <= 3:
                espera = 1.0             # a tela caiu: reabre já para reconectar e redesenhar
            self.proxima_abertura = agora + espera
            motivo = motivo_saida(self.log_main_desde)
            log.info("main.py fechou (código %s)%s; reabrindo em %.0f s", codigo,
                     f": {motivo}" if motivo else "", espera)
            if codigo != tela_usb.CODIGO_RECONECTAR:
                tela_usb.gravar_estado("parado", mensagem="O programa da tela fechou", detalhe=motivo or
                                       f"código de saída {codigo}", codigo=codigo, pid=None)
            self.atualizar_estado()
        if self.proc is None and agora >= self.proxima_abertura and not self.fim.is_set():
            try:
                self.reverso_em_uso = bool(ler_config()["display"].get("DISPLAY_REVERSE", False))
            except Exception:
                self.reverso_em_uso = None
            self.log_main_desde = _tamanho(LOG_MAIN)
            if tela_usb.ler_estado().get("estado") != "reconectando":
                tela_usb.gravar_estado("iniciando", mensagem="Iniciando o programa da tela", detalhe="", pid=None)
            self.proc = abrir_main()
            self.inicio_proc = agora


def servidor_comandos(srv, painel):
    acoes = {
        "ping": lambda: None,
        "abrir": abrir_configuracao,
        "reiniciar": painel.pedir_reinicio,
        "aplicar": painel.aplicar,
        "perfis": painel.atualizar_estado,
        "trabalho": lambda: painel.usar_perfil("trabalho"),
        "jogos": lambda: painel.usar_perfil("jogos"),
        "sair": painel.sair,
    }
    while not painel.fim.is_set():
        try:
            con, _ = srv.accept()
        except OSError:
            break
        try:
            con.settimeout(2)
            cmd = con.recv(64).decode("utf-8", "ignore").strip()
            acao = acoes.get(cmd)
            con.sendall(b"ok\n" if acao else b"?\n")
            con.close()
            if acao:                      # em outra thread: uma troca de tema não segura os próximos comandos
                threading.Thread(target=acao, daemon=True).start()
        except Exception as e:
            log.info("Comando com erro: %s", e)


def criar_icone(painel):
    import pystray
    from PIL import Image

    def faz(f, *a):
        return lambda: f(*a)              # pystray chama ações sem argumentos

    def em_fundo(f, *a):                  # troca de tema/brilho fora da thread do menu
        return lambda: threading.Thread(target=f, args=a, daemon=True).start()

    def perfil_marcado(perfil):
        return lambda item: bool(painel.tema) and painel.tema == painel.perfis.get(perfil)

    def brilho_marcado(valor):
        return lambda item: painel.brilho == valor

    m = pystray.MenuItem
    menu = pystray.Menu(
        m("Abrir configurações", faz(abrir_configuracao), default=True),
        pystray.Menu.SEPARATOR,
        m("Perfil Trabalho", em_fundo(painel.usar_perfil, "trabalho"), checked=perfil_marcado("trabalho"), radio=True),
        m("Perfil Jogos", em_fundo(painel.usar_perfil, "jogos"), checked=perfil_marcado("jogos"), radio=True),
        m("Trocar sozinho ao jogar (tela cheia)", faz(painel.alternar_auto),
          checked=lambda item: bool(painel.perfis.get("auto"))),
        m("Brilho da tela", pystray.Menu(*[m(f"{v}%", em_fundo(painel.mudar_brilho, v), checked=brilho_marcado(v), radio=True)
                                           for v in (5, 10, 20, 35, 50, 75, 100)])),
        pystray.Menu.SEPARATOR,
        m("Reiniciar a tela", faz(painel.pedir_reinicio)),
        m("Sair (a tela para de atualizar)", faz(painel.sair)),
    )
    return pystray.Icon("PULSE", Image.open(ICONE_PNG), "PULSE — System Telemetry", menu)


def main():
    abrir = "--abrir" in sys.argv
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        srv.bind(("127.0.0.1", PORTA_COMANDOS))
        srv.listen(5)
    except OSError:
        srv.close()
        if abrir:
            enviar_comando("abrir")
        return                            # já está rodando
    _configurar_log()
    from parar_painel import parar_main
    parar_main()                          # um main.py antigo, aberto por fora, seguraria a porta da tela
    PEDIDO_REINICIO.unlink(missing_ok=True)
    admin = tela_usb.eh_admin()
    log.info("Iniciador ligado (administrador: %s).", "sim" if admin else "não")
    if not admin:
        log.info("Sem administrador algumas leituras (temperatura da CPU) ficam vazias. A tarefa '%s' "
                 "do Windows abre o PULSE como administrador.", "PainelTelemetria")

    painel = Painel()
    painel.atualizar_estado()
    threading.Thread(target=servidor_comandos, args=(srv, painel), daemon=True).start()
    if abrir:
        threading.Timer(1.0, abrir_configuracao).start()

    icone = None
    if not os.environ.get("PAINEL_SEM_ICONE"):
        try:
            icone = criar_icone(painel)
        except Exception as e:
            log.info("Sem ícone na bandeja: %s", e)
    if icone is None:
        painel.laco()
        return
    painel.icone = icone
    laco = threading.Thread(target=painel.laco, daemon=True)
    laco.start()

    def pronto(ic):
        ic.visible = True
        painel.atualizar_icone()

    try:
        icone.run(setup=pronto)           # fica aqui até "Sair"
    except Exception as e:                # sem bandeja (ex.: Explorer travado): segue mantendo a tela
        log.info("Ícone da bandeja parou (%s); seguindo sem ícone", e)
        painel.icone = None
        laco.join()
    painel.fim.set()
    laco.join(10)
    srv.close()
    log.info("Iniciador desligado.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        _configurar_log()
        log.exception("Iniciador parou com erro")
        raise
