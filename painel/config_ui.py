# Painel de Telemetria - interface de configuração
#
# Janela própria "Painel de Telemetria" (pywebview + WebView2 do Windows, sem navegador) para escolher o
# tema da tela, criar e editar temas próprios (blocos, ordem, cores, fontes, estilo), perfis, brilho e
# aplicar na tela. A página é servida em http://127.0.0.1:5680.
# Rode a partir da pasta app:
#   pythonw painel/config_ui.py --janela    abre a janela (é o que o ícone da bandeja faz)
#   python  painel/config_ui.py             abre no navegador (modo antigo)
import base64
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gerador  # noqa: E402
import iniciar  # noqa: E402  (perfis e caminhos do iniciador)
from parar_painel import parar_main  # noqa: E402

APP_DIR = gerador.APP_DIR
DESTINO = gerador.DESTINO                     # C:\PainelTelemetria
FUNDOS_DIR = DESTINO / "fundos"               # imagens de fundo enviadas pelo usuário
CONFIG_YAML = APP_DIR / "config.yaml"
THEMES_DIR = gerador.THEMES_DIR
NOME_TAREFA = "PainelTelemetria"
PORTA = 5680
HTML = Path(__file__).resolve().parent / "ui.html"

os.chdir(APP_DIR)
_lock = threading.Lock()
JANELA = None                  # janela do pywebview, quando aberta com --janela
ULTIMO_CONTATO = time.monotonic()


# ---------------------------------------------------------------- config.yaml
def _yaml_rt():
    from ruamel.yaml import YAML
    y = YAML()
    y.preserve_quotes = True
    y.width = 4096
    return y


def ler_config():
    with open(CONFIG_YAML, encoding="utf-8") as fh:
        return _yaml_rt().load(fh)


def gravar_config(dados):
    with open(CONFIG_YAML, "w", encoding="utf-8") as fh:
        _yaml_rt().dump(dados, fh)


# ---------------------------------------------------------------- temas
def listar_temas():
    meus = set(gerador.listar_temas_usuario())
    temas = []
    for d in THEMES_DIR.iterdir():
        f = d / "theme.yaml"
        if not d.is_dir() or not f.is_file():
            continue
        texto = f.read_text(encoding="utf-8", errors="ignore")
        tamanho, orient = '3.5"', "portrait"
        for linha in texto.splitlines():
            s = linha.strip()
            if s.startswith("DISPLAY_SIZE:"):
                tamanho = s.split(":", 1)[1].strip().strip("'")
            elif s.startswith("DISPLAY_ORIENTATION:"):
                orient = s.split(":", 1)[1].strip()
        if tamanho not in ('3.5"', '"3.5\\""'):
            continue
        meu = d.name in meus
        nome = gerador.carregar_tema_usuario(d.name)["nome"] if meu else d.name
        temas.append({"pasta": d.name, "nome": nome, "editavel": meu,
                      "orientacao": "retrato" if "portrait" in orient else "paisagem",
                      "previa": (d / "preview.png").is_file()})
    temas.sort(key=lambda t: (not t["editavel"], t["nome"].lower()))
    return temas


def pasta_livre(nome):
    base = gerador.nome_para_pasta(nome)
    pasta, i = base, 2
    while (THEMES_DIR / pasta).exists() or (gerador.TEMAS_USUARIO / f"{pasta}.json").exists():
        pasta = f"{base}_{i}"
        i += 1
    return pasta


def tema_atual():
    return str(ler_config()["config"].get("THEME", gerador.TEMA_PADRAO))


def definir_tema_atual(pasta):
    cfg = ler_config()
    cfg["config"]["THEME"] = pasta
    gravar_config(cfg)


# ---------------------------------------------------------------- painel em execução
def _eh_admin():
    if platform.system() != "Windows":
        return True
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _abrir_iniciador():
    kw = {"creationflags": 0x00000008 | 0x00000200} if platform.system() == "Windows" else \
        {"start_new_session": True, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    subprocess.Popen([iniciar._pythonw(), "painel/iniciar.py"], cwd=str(APP_DIR), **kw)


def painel_rodando():
    return iniciar.enviar_comando("ping")


def reiniciar_painel():
    """O iniciador (painel/iniciar.py, ícone da bandeja) mantém o main.py aberto; basta pedir para ele reabrir."""
    if iniciar.enviar_comando("reiniciar"):
        return "Painel reiniciado."
    # iniciador parado: abre pela tarefa do Windows (roda como administrador) ou direto
    parar_main()
    time.sleep(1.0)  # dá tempo da porta COM ser liberada
    if platform.system() == "Windows":
        r = subprocess.run(["schtasks", "/Run", "/TN", NOME_TAREFA], capture_output=True, creationflags=0x08000000)
        if r.returncode == 0:
            return "Painel iniciado."
    _abrir_iniciador()
    return "Painel iniciado."


def gravar_perfis(d):
    p = iniciar.ler_perfis()
    for k in ("auto", "trabalho", "jogos", "entrar_s", "sair_s"):
        if k in d:
            p[k] = d[k]
    p["auto"] = bool(p.get("auto"))
    p["entrar_s"] = max(1, min(120, int(p.get("entrar_s", 5))))
    p["sair_s"] = max(1, min(600, int(p.get("sair_s", 20))))
    iniciar.gravar_perfis(p)
    iniciar.enviar_comando("perfis")   # atualiza o menu da bandeja
    return p


# ---------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def handle_one_request(self):
        global ULTIMO_CONTATO
        ULTIMO_CONTATO = time.monotonic()
        return super().handle_one_request()

    def _send(self, code, corpo: bytes, tipo="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", tipo)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _corpo(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def do_GET(self):
        caminho = unquote(self.path.split("?", 1)[0])
        try:
            if caminho == "/api/ping":
                return self._json({"ok": True})
            if caminho == "/api/focar":
                focar()
                return self._json({"ok": True})
            if caminho in ("/", "/index.html"):
                return self._send(200, HTML.read_bytes(), "text/html; charset=utf-8")
            if caminho == "/api/estado":
                cfg = ler_config()
                return self._json({
                    "temas": listar_temas(),
                    "tema_atual": str(cfg["config"].get("THEME", gerador.TEMA_PADRAO)),
                    "brilho": int(cfg["display"].get("BRIGHTNESS", 20)),
                    "inverter": bool(cfg["display"].get("DISPLAY_REVERSE", False)),
                    "paletas": gerador.PALETAS,
                    "fontes": list(gerador.FONTES),
                    "blocos_info": gerador.BLOCOS_INFO,
                    "modelos": list(gerador.MODELOS),
                    "perfis": iniciar.ler_perfis(),
                    "padrao": gerador.completar(None),
                    "admin": _eh_admin() or painel_rodando(),
                })
            if caminho.startswith("/api/tema/"):
                pasta = caminho[len("/api/tema/"):]
                return self._json(gerador.carregar_tema_usuario(pasta))
            if caminho.startswith("/api/miniatura/"):
                arq = (THEMES_DIR / caminho[len("/api/miniatura/"):] / "preview.png").resolve()
                if THEMES_DIR.resolve() in arq.parents and arq.is_file():
                    return self._send(200, arq.read_bytes(), "image/png")
                return self._send(404, b"{}")
            self._send(404, b"{}")
        except Exception as e:
            self._json({"erro": f"{type(e).__name__}: {e}"}, 500)

    def do_POST(self):
        try:
            d = self._corpo()
            if self.path == "/api/previa":
                with _lock, tempfile.TemporaryDirectory() as tmp:
                    _, omitidos = gerador.gerar(d, Path(tmp), com_previa=False)
                    img = gerador.renderizar_previa(Path(tmp))
                buf = BytesIO()
                img.save(buf, "PNG")
                corpo = buf.getvalue()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Omitidos", base64.b64encode(json.dumps(omitidos).encode("utf-8")).decode("ascii"))
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)
                return

            if self.path == "/api/fundo":  # recebe imagem (data URL) e devolve o caminho salvo
                from PIL import Image
                FUNDOS_DIR.mkdir(parents=True, exist_ok=True)
                img = Image.open(BytesIO(base64.b64decode(d["imagem"].split(",", 1)[-1]))).convert("RGB")
                arq = FUNDOS_DIR / f"fundo_{int(time.time())}.png"
                img.save(arq)
                return self._json({"ok": True, "caminho": str(arq)})

            if self.path == "/api/tema/novo":
                with _lock:
                    base = d.get("base") or gerador.modelo(d.get("modelo") or "Padrão")
                    base["nome"] = d.get("nome") or "Novo tema"
                    pasta = pasta_livre(base["nome"])
                    gerador.salvar_tema_usuario(pasta, base)
                return self._json({"ok": True, "pasta": pasta})

            if self.path == "/api/tema/salvar":
                with _lock:
                    gerador.salvar_tema_usuario(d["pasta"], d["cfg"])
                return self._json({"ok": True})

            if self.path == "/api/tema/excluir":
                pasta = d["pasta"]
                with _lock:
                    meus = gerador.listar_temas_usuario()
                    if pasta not in meus:
                        return self._json({"erro": "Só é possível excluir temas criados por você."}, 400)
                    if len(meus) <= 1:
                        return self._json({"erro": "Mantenha pelo menos um tema seu."}, 400)
                    (gerador.TEMAS_USUARIO / f"{pasta}.json").unlink(missing_ok=True)
                    shutil.rmtree(THEMES_DIR / pasta, ignore_errors=True)
                    msg = ""
                    if tema_atual() == pasta:
                        novo = [p for p in meus if p != pasta][0]
                        definir_tema_atual(novo)
                        msg = reiniciar_painel()
                return self._json({"ok": True, "mensagem": msg})

            if self.path == "/api/perfis":
                with _lock:
                    p = gravar_perfis(d.get("perfis") or {})
                    msg = ""
                    if d.get("usar"):  # "Usar agora": coloca o tema do perfil na tela
                        alvo = p.get(d["usar"])
                        if not (THEMES_DIR / str(alvo) / "theme.yaml").is_file():
                            return self._json({"erro": f"Tema '{alvo}' não encontrado."}, 400)
                        definir_tema_atual(alvo)
                        msg = reiniciar_painel()
                    elif not painel_rodando() and platform.system() == "Windows":
                        msg = reiniciar_painel()
                return self._json({"ok": True, "perfis": p, "mensagem": msg})

            if self.path == "/api/aplicar":
                pasta = d.get("tema") or gerador.TEMA_PADRAO
                with _lock:
                    if d.get("cfg") and pasta in gerador.listar_temas_usuario():
                        gerador.salvar_tema_usuario(pasta, d["cfg"])
                    if not (THEMES_DIR / pasta / "theme.yaml").is_file():
                        return self._json({"erro": f"Tema '{pasta}' não encontrado."}, 400)
                    cfg = ler_config()
                    cfg["config"]["THEME"] = pasta
                    cfg["display"]["BRIGHTNESS"] = max(0, min(100, int(d.get("brilho", 20))))
                    cfg["display"]["DISPLAY_REVERSE"] = bool(d.get("inverter", False))
                    gravar_config(cfg)
                    msg = reiniciar_painel()
                aviso = ""
                return self._json({"ok": True, "mensagem": f"Aplicado. {msg}{aviso}"})

            self._send(404, b"{}")
        except Exception as e:
            self._json({"erro": f"{type(e).__name__}: {e}"}, 500)


# ---------------------------------------------------------------- janela própria
ICONE_ICO = Path(__file__).resolve().parent / "painel.ico"
TITULO = "Painel de Telemetria"


def _hwnd():
    import ctypes
    return ctypes.windll.user32.FindWindowW(None, TITULO)


def _icone_e_frente(primeira=False):
    """Põe o ícone do painel na janela/barra de tarefas e traz a janela para a frente (Windows)."""
    if platform.system() != "Windows":
        return
    try:
        import ctypes
        u32 = ctypes.windll.user32
        u32.LoadImageW.restype = ctypes.c_void_p
        u32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
        hwnd = _hwnd()
        if not hwnd:
            return
        if primeira and ICONE_ICO.is_file():
            for tipo, tam in ((1, 32), (0, 16)):         # ICON_BIG, ICON_SMALL
                h = u32.LoadImageW(None, str(ICONE_ICO), 1, tam, tam, 0x10)  # IMAGE_ICON, LR_LOADFROMFILE
                if h:
                    u32.SendMessageW(hwnd, 0x80, tipo, h)                    # WM_SETICON
        u32.ShowWindow(hwnd, 9)                                               # SW_RESTORE
        u32.SetForegroundWindow(hwnd)
    except Exception:
        pass


def focar():
    if JANELA is not None:
        try:
            JANELA.restore()
            JANELA.show()
            JANELA.on_top = True
            time.sleep(0.15)
            JANELA.on_top = False
        except Exception:
            pass
        _icone_e_frente()
    else:
        webbrowser.open(f"http://127.0.0.1:{PORTA}/")


def abrir_janela(url, srv):
    """Abre a janela própria. Devolve False se não der (sem pywebview ou sem WebView2)."""
    global JANELA
    try:
        import webview
    except Exception as e:
        print("Janela própria indisponível:", e)
        return False
    if platform.system() == "Windows":
        try:  # agrupa na barra de tarefas como um programa próprio (e não como "Python")
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PainelTelemetria.Configuracao")
        except Exception:
            pass
    try:
        JANELA = webview.create_window(TITULO, url, width=1320, height=900, min_size=(980, 640),
                                       background_color="#0b0e17")
        JANELA.events.shown += lambda: threading.Timer(0.3, _icone_e_frente, kwargs={"primeira": True}).start()
        webview.start()
        return True
    except Exception as e:
        print("Falha ao abrir a janela:", e)
        JANELA = None
        return False


def main():
    url = f"http://127.0.0.1:{PORTA}/"
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", PORTA), Handler)
    except OSError:
        # já está aberta: traz a janela existente para a frente
        try:
            import urllib.request
            urllib.request.urlopen(url + "api/focar", timeout=3).read()
        except Exception:
            webbrowser.open(url)
        return
    with _lock:
        gerador.migrar_antigo()
        gerador.criar_modelos_iniciais()
        for p in gerador.listar_temas_usuario():  # garante que todo tema salvo exista em res/themes
            if not (THEMES_DIR / p / "theme.yaml").is_file():
                gerador.gerar(gerador.carregar_tema_usuario(p), THEMES_DIR / p)
    if "--janela" in sys.argv:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        if abrir_janela(url, srv):
            srv.shutdown()        # janela fechada: o painel continua na bandeja
            return
        # sem janela própria: usa o navegador e fecha sozinho quando a página for fechada
        webbrowser.open(url)
        while time.monotonic() - ULTIMO_CONTATO < 120:
            time.sleep(5)
        srv.shutdown()
        return
    print("Configuração do Painel de Telemetria aberta em", url)
    print("Deixe esta janela aberta enquanto configura. Feche-a para sair.")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
