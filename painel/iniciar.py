# PULSE — System Telemetry - iniciador e ícone da bandeja
#
# É o que a tarefa "PainelTelemetria" abre ao entrar no Windows (como administrador, exigido
# pelo LibreHardwareMonitor). Ele:
#   1. mantém o programa da tela (main.py) rodando e o reabre se ele fechar;
#   2. liga e desliga o MODO GAMER (configuração em C:\PainelTelemetria\perfis.json):
#      - algum programa em TELA CHEIA (jogo) por alguns segundos  -> tema do modo gamer (e o brilho dele,
#        se escolhido);
#      - saiu da tela cheia por alguns segundos                   -> volta ao tema (e brilho) que estava
#        antes do jogo, ou ao tema de Trabalho, conforme a opção.
#      Também pela bandeja ("Modo gamer"). O estado fica em modo_gamer.json, então sobrevive a reinícios;
#   2b. fecha o TURMO quando ele abre (ele pega a porta da tela no boot), se a opção estiver ligada;
#   3. mostra o ícone na bandeja (perto do relógio, em "mostrar ícones ocultos") com atalhos
#      para abrir a configuração, trocar de perfil, mudar o brilho, reiniciar e sair;
#   4. recebe comandos em 127.0.0.1:5681 ("abrir", "aplicar", "reiniciar", "perfis", "jogos", "trabalho",
#      "gamer", "sair_gamer", "sair", "ping")
#      da janela de configuração e do atalho "PULSE".
#   Trocar tema ou brilho não reinicia o main.py: o pedido vai para o painel/troca_tema.py, que roda
#   dentro dele (127.0.0.1:5682) e só redesenha a tela. Girar a tela 180° ainda reinicia.
# Rode a partir da pasta app:  pythonw painel/iniciar.py [--abrir]
import json
import logging
import os
import platform
import re
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
DESLIGANDO = DESTINO / ".desligando"          # o main.py grava ao receber o aviso de desligamento (painel/desligamento.py)
SAIDA_MAIN = DESTINO / "main_saida.log"       # o que o main.py escreve fora do log (erros de import, tracebacks)
LOG_MAIN = APP / "log.log"                    # log da biblioteca da tela
ICONE_PNG = PAINEL / "pulse_tray.png"
WINDOWS = platform.system() == "Windows"

MODO_GAMER = DESTINO / "modo_gamer.json"     # {"ativo", "origem": auto|manual, "antes": {"tema", "brilho"}}

# jogos_brilho: brilho no modo gamer (None = não muda); voltar_anterior: ao sair do modo gamer volta ao tema que
# estava antes (False = vai para o tema de Trabalho); fechar_turmo: fecha o TURMO quando ele abrir
PERFIS_PADRAO = {"auto": True, "trabalho": "Meu_Trabalho", "jogos": "Meu_Jogos", "entrar_s": 3, "sair_s": 5,
                 "jogos_brilho": None, "voltar_anterior": True, "fechar_turmo": True, "versao": 2}
TURMO = re.compile(r"^(turmo|turzx)", re.I)   # nomes de processo do TURMO (ex.: TURMO.exe)

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
        lido = json.loads(PERFIS.read_text(encoding="utf-8"))
        if not lido.get("versao"):
            # até a 7.0 o padrão era entrar após 5 s e voltar após 20 s (lento demais): quem não mudou ganha o novo
            if lido.get("entrar_s") == 5:
                lido["entrar_s"] = PERFIS_PADRAO["entrar_s"]
            if lido.get("sair_s") == 20:
                lido["sair_s"] = PERFIS_PADRAO["sair_s"]
            lido["versao"] = PERFIS_PADRAO["versao"]
        p.update(lido)
    except FileNotFoundError:
        pass
    except Exception as e:
        log.info("perfis.json inválido: %s", e)
    return p


def ler_modo_gamer():
    try:
        d = json.loads(MODO_GAMER.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {"ativo": False}
    except Exception:
        return {"ativo": False}


def gravar_modo_gamer(d):
    try:
        tmp = MODO_GAMER.with_name(MODO_GAMER.name + ".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, MODO_GAMER)
    except OSError as e:
        log.info("Não consegui gravar o modo_gamer.json: %s", e)


def tema_existe(pasta):
    return bool(pasta) and (APP / "res" / "themes" / pasta / "theme.yaml").is_file()


def pawnio_instalado():
    """Driver que o LibreHardwareMonitor 0.9.5 usa para ler a temperatura da CPU. None fora do Windows."""
    if not WINDOWS:
        return None
    try:
        import winreg
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                       r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\PawnIO"))
        return True
    except OSError:
        pass
    try:
        r = subprocess.run(["sc", "query", "PawnIO"], capture_output=True, text=True, timeout=10,
                           creationflags=0x08000000)
        return r.returncode == 0
    except Exception:
        return False


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


def windows_desligando():
    """True se o Windows está desligando, reiniciando ou saindo da conta: aí o main.py NÃO pode ser reaberto,
    senão ele reinicia a tela e ela fica acesa com o PC desligado."""
    try:
        if time.time() - DESLIGANDO.stat().st_mtime < 300:
            return True
    except OSError:
        pass
    if WINDOWS:
        try:
            import ctypes
            return bool(ctypes.windll.user32.GetSystemMetrics(0x2000))   # SM_SHUTTINGDOWN
        except Exception:
            pass
    return False


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


# códigos de saída do Windows quando o processo cai sem passar pelo Python (falha em código nativo)
FALHAS_WINDOWS = {
    0xC0000005: "falha de acesso à memória em código nativo",
    0xC0000409: "falha grave em código nativo",
    0xC00000FD: "estouro de pilha",
    0xC0000374: "memória corrompida em código nativo",
    0xE0434352: "erro não tratado no .NET (LibreHardwareMonitor)",
    0xC000013A: "encerrado pelo Windows",
}


def descrever_codigo(codigo):
    if codigo is None:
        return "?"
    c = int(codigo) & 0xFFFFFFFF
    if c >= 0xC0000000:
        return f"0x{c:08X}" + (f", {FALHAS_WINDOWS[c]}" if c in FALHAS_WINDOWS else "")
    return str(codigo)


def motivo_saida(log_desde, codigo=None):
    """Por que o main.py fechou: o último erro do log.log desta execução ou a última linha de um traceback.
    Sem erro registrado, diz isso e mostra a última mensagem do log só como contexto (um aviso qualquer,
    como o de várias GPUs, não é a causa)."""
    linhas = _ler_trecho(LOG_MAIN, log_desde)
    saida = [x for x in _ler_trecho(SAIDA_MAIN) if not x.startswith("---")]

    def ultima(nivel):
        achadas = [x for x in linhas if nivel in x and "Too fast" not in x]
        return achadas[-1].split(nivel, 1)[1].strip()[:300] if achadas else ""

    erro_saida = next((x for x in reversed(saida) if "Error" in x or "error" in x or "Exception" in x), "")
    erro = ultima("[CRITICAL]") or ultima("[ERROR]") or erro_saida[:300]
    if erro:
        return erro
    contexto = ""
    for x in reversed(linhas):
        m = re.search(r"\[(DEBUG|INFO|WARNING)\]\s*(.*)", x)
        if m and "Too fast" not in x:
            contexto = m.group(2).strip()[:200]
            break
    c = None if codigo is None else int(codigo) & 0xFFFFFFFF
    if c is not None and c >= 0xC0000000:
        texto = f"O programa da tela travou ({descrever_codigo(codigo)})"
    else:
        texto = f"O programa da tela fechou sem registrar erro (código {descrever_codigo(codigo)})"
    return texto + (f". Última mensagem do log: {contexto}" if contexto else "")


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
        self.desligando = False          # Windows desligando (painel/desligamento.py): não reabre o main.py
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
        self.trava_gamer = threading.RLock()
        self.gamer = ler_modo_gamer()
        # ligado sozinho por um jogo antes de reiniciar: se o jogo já fechou, desliga depois de "sair_s"
        self.em_jogo = bool(self.gamer.get("ativo")) and self.gamer.get("origem") == "auto"
        self.turmo_visto = set()         # PIDs do TURMO já tratados (para não repetir o log)
        self.turmo_conferido = 0.0
        self.pawnio = pawnio_instalado()
        self.pawnio_conferido = time.monotonic()

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
            if self.gamer.get("ativo"):
                rotulo = "Modo gamer"
            elif self.tema == self.perfis.get("jogos"):
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
        if perfil == "jogos":
            return self.entrar_gamer("manual")
        alvo = self.perfis.get(perfil)
        if not tema_existe(alvo):
            log.info("Tema do perfil %s não encontrado: %s", perfil, alvo)
            return
        with self.trava_gamer:
            if self.gamer.get("ativo"):      # escolheu o Trabalho à mão: o modo gamer acaba aqui
                self._encerrar_gamer("tema de Trabalho escolhido", restaurar_brilho=True)
        self.trocar_tema(alvo)

    # ---------- modo gamer ----------
    def entrar_gamer(self, origem):
        """origem: "auto" (jogo em tela cheia) ou "manual" (bandeja/configuração)."""
        with self.trava_gamer:
            self.perfis = ler_perfis()
            alvo = self.perfis.get("jogos")
            if not tema_existe(alvo):
                log.info("Tema do modo gamer não encontrado: %s", alvo)
                return
            try:
                cfg = ler_config()
                tema = str(cfg["config"].get("THEME", ""))
                brilho = int(cfg["display"].get("BRIGHTNESS", 20))
            except Exception:
                tema, brilho = self.tema, self.brilho
            if not self.gamer.get("ativo"):
                self.gamer = {"ativo": True, "origem": origem, "desde": time.time(),
                              "antes": {"tema": tema, "brilho": brilho}}
            elif origem == "manual":
                self.gamer["origem"] = "manual"   # ligado à mão: só desliga à mão
            gravar_modo_gamer(self.gamer)
            log.info("Modo gamer ligado (%s) -> tema %s", "jogo em tela cheia" if origem == "auto" else "à mão",
                     alvo)
            if tema != alvo:
                self.trocar_tema(alvo)
            b = self.perfis.get("jogos_brilho")
            if isinstance(b, int) and not isinstance(b, bool) and b != brilho:
                self.mudar_brilho(b)
            self.atualizar_estado()
            self.atualizar_icone()

    def sair_gamer(self, origem):
        with self.trava_gamer:
            if not self.gamer.get("ativo"):
                return
            self.perfis = ler_perfis()
            antes = self.gamer.get("antes") or {}
            jogos = self.perfis.get("jogos")
            alvo = None
            if self.perfis.get("voltar_anterior", True):
                t = antes.get("tema")
                if t and t != jogos and tema_existe(t):
                    alvo = t
            if not alvo:
                alvo = self.perfis.get("trabalho")
            self._encerrar_gamer("saiu do jogo" if origem == "auto" else "à mão", restaurar_brilho=True,
                                 alvo=alvo)
            if tema_existe(alvo) and tema_atual() != alvo:
                self.trocar_tema(alvo)
            self.atualizar_estado()
            self.atualizar_icone()

    def _encerrar_gamer(self, motivo, restaurar_brilho=False, alvo=None):
        antes = self.gamer.get("antes") or {}
        self.gamer = {"ativo": False}
        gravar_modo_gamer(self.gamer)
        log.info("Modo gamer desligado (%s)%s", motivo, f" -> tema {alvo}" if alvo else "")
        b = antes.get("brilho")
        if restaurar_brilho and isinstance(self.perfis.get("jogos_brilho"), int) and isinstance(b, int) \
                and b != self.brilho:
            self.mudar_brilho(b)

    def alternar_gamer(self):
        if self.gamer.get("ativo"):
            self.sair_gamer("manual")
        else:
            self.entrar_gamer("manual")

    # ---------- TURMO ----------
    def fechar_turmo(self):
        """O TURMO abre com o Windows (tarefa agendada) e pega a porta da tela enquanto o PULSE a reinicia."""
        try:
            import psutil
        except ImportError:
            return
        for p in psutil.process_iter(["pid", "name", "exe"]):
            try:
                nome = p.info.get("name") or ""
                if not TURMO.match(nome) or p.pid == os.getpid():
                    continue
                novo = p.pid not in self.turmo_visto
                self.turmo_visto.add(p.pid)
                p.kill()
                if novo:
                    log.info("TURMO aberto (%s, PID %s) foi fechado: ele disputa a tela com o PULSE. "
                             "Para deixar ele aberto, desligue 'Fechar o TURMO' na configuração.",
                             p.info.get("exe") or nome, p.pid)
            except psutil.NoSuchProcess:
                continue
            except psutil.AccessDenied:
                if p.pid not in self.turmo_visto:
                    self.turmo_visto.add(p.pid)
                    log.info("O TURMO (PID %s) está aberto e não consegui fechar (sem permissão).", p.pid)
            except Exception as e:
                log.info("Falha ao fechar o TURMO: %s", e)

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
        with self.trava_gamer:
            if self.gamer.get("ativo") and tema != self.perfis.get("jogos"):
                self._encerrar_gamer("outro tema escolhido na configuração")
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

        # --- TURMO: fecha quando ele abrir (a cada 2 s)
        if self.perfis.get("fechar_turmo", True) and agora - self.turmo_conferido >= 2:
            self.turmo_conferido = agora
            self.fechar_turmo()

        # --- PawnIO instalado depois (botão da configuração): reabre o main.py para ler a temperatura da CPU
        if self.pawnio is False and agora - self.pawnio_conferido >= 15:
            self.pawnio_conferido = agora
            if pawnio_instalado():
                self.pawnio = True
                log.info("Driver PawnIO instalado: reiniciando a tela para ler a temperatura da CPU.")
                pedido = True

        # --- modo gamer automático (jogo em tela cheia)
        if self.perfis.get("auto"):
            jogo = jogo_em_tela_cheia()
            if jogo != self.em_jogo:
                self.desde = self.desde or agora
                espera = float(self.perfis.get("entrar_s" if jogo else "sair_s", 3 if jogo else 5))
                if agora - self.desde >= espera:
                    self.em_jogo, self.desde = jogo, None
                    try:
                        if jogo:
                            self.entrar_gamer("auto")
                        elif self.gamer.get("ativo") and self.gamer.get("origem") == "auto":
                            self.sair_gamer("auto")
                    except Exception as e:
                        log.info("Falha ao trocar o modo gamer: %s", e)
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

        # --- Windows desligando: não reabre nada (o main.py já apagou a tela)
        if windows_desligando():
            if not self.desligando:
                self.desligando = True
                log.info("Windows desligando: a tela foi apagada e não será reaberta.")
            return
        if self.desligando:
            self.desligando = False
            log.info("Desligamento cancelado: a tela segue normalmente.")

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
            motivo = motivo_saida(self.log_main_desde, codigo)
            log.info("main.py fechou (código %s)%s; reabrindo em %.0f s", descrever_codigo(codigo),
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
        "jogos": lambda: painel.entrar_gamer("manual"),
        "gamer": painel.alternar_gamer,
        "sair_gamer": lambda: painel.sair_gamer("manual"),
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

    def brilho_marcado(valor):
        return lambda item: painel.brilho == valor

    m = pystray.MenuItem
    menu = pystray.Menu(
        m("Abrir configurações", faz(abrir_configuracao), default=True),
        pystray.Menu.SEPARATOR,
        m("Modo gamer", em_fundo(painel.alternar_gamer), checked=lambda item: bool(painel.gamer.get("ativo"))),
        m("Perfil Trabalho", em_fundo(painel.usar_perfil, "trabalho"),
          checked=lambda item: not painel.gamer.get("ativo") and painel.tema == painel.perfis.get("trabalho"),
          radio=True),
        m("Modo gamer sozinho ao jogar (tela cheia)", faz(painel.alternar_auto),
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
    DESLIGANDO.unlink(missing_ok=True)    # sobra do último desligamento
    admin = tela_usb.eh_admin()
    log.info("Iniciador ligado (administrador: %s).", "sim" if admin else "não")
    if not admin:
        log.info("Sem administrador algumas leituras (temperatura da CPU) ficam vazias. A tarefa '%s' "
                 "do Windows abre o PULSE como administrador.", "PainelTelemetria")

    painel = Painel()
    if painel.pawnio is False:
        log.info("Driver PawnIO não instalado: a temperatura da CPU fica vazia. Instale pela janela de "
                 "configuração (aviso no topo) ou reinstale o PULSE.")
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
