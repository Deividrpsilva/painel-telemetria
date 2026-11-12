# Painel de Telemetria - troca de tema sem reiniciar o programa da tela
#
# O main.py do turing-smart-screen-python carrega o tema uma vez só e agenda as leituras dos
# sensores com os intervalos desse tema. Para trocar de tema na hora (como o TURMO), este módulo,
# carregado pelo main.py antes do agendador:
#   1. fixa intervalos iguais para todos os temas, assim o agendamento serve para qualquer tema;
#   2. só lê um sensor quando o tema atual mostra alguma coisa dele (evita leituras à toa);
#   3. abre um canal em 127.0.0.1:5682 que recebe "tema <pasta>" e "brilho <0-100>": troca os
#      dados do tema, redesenha o fundo e volta a atualizar os valores, sem fechar o programa.
# Se o tema novo tiver outra orientação ou outro tamanho de tela, responde "reiniciar".
import copy
import platform
import socket
import threading
import time
from pathlib import Path

import library.config as config
from library.log import logger

PORTA = 5682

# intervalos (s) usados para todos os temas
INTERVALOS = {
    ("CPU", "PERCENTAGE"): 1, ("CPU", "FREQUENCY"): 2, ("CPU", "LOAD"): 2, ("CPU", "TEMPERATURE"): 2,
    ("CPU", "FAN_SPEED"): 2, ("GPU",): 1, ("MEMORY",): 2, ("DISK",): 5, ("NET",): 1, ("DATE",): 1,
    ("UPTIME",): 1, ("CUSTOM",): 1, ("WEATHER",): 600, ("PING",): 5,
}

_pausado = threading.Event()   # durante a troca, os sensores não desenham
_trava = threading.Lock()
_display = None
_em_andamento = 0              # leituras de sensor desenhando agora
_contador = threading.Lock()


def normalizar(tema):
    stats = tema.setdefault("STATS", {})
    for caminho, intervalo in INTERVALOS.items():
        d = stats
        for parte in caminho:
            if not isinstance(d.get(parte), dict):
                d[parte] = {}
            d = d[parte]
        d["INTERVAL"] = intervalo
    return tema


def _visivel(d):
    if isinstance(d, dict):
        if d.get("SHOW") is True:
            return True
        return any(_visivel(v) for k, v in d.items() if k != "INTERVAL")
    return False


normalizar(config.THEME_DATA)   # antes do library.scheduler ler os intervalos

import library.stats as stats  # noqa: E402  (depois de normalizar)

_SENSORES = [  # (classe, função, caminho no tema)
    (stats.CPU, "percentage", ("CPU", "PERCENTAGE")), (stats.CPU, "frequency", ("CPU", "FREQUENCY")),
    (stats.CPU, "load", ("CPU", "LOAD")), (stats.CPU, "temperature", ("CPU", "TEMPERATURE")),
    (stats.CPU, "fan_speed", ("CPU", "FAN_SPEED")), (stats.Gpu, "stats", ("GPU",)),
    (stats.Memory, "stats", ("MEMORY",)), (stats.Disk, "stats", ("DISK",)), (stats.Date, "stats", ("DATE",)),
    (stats.SystemUptime, "stats", ("UPTIME",)), (stats.Custom, "stats", ("CUSTOM",)),
    (stats.Weather, "stats", ("WEATHER",)), (stats.Ping, "stats", ("PING",)),
]


def _guardado(original, caminho, sempre=False):
    def f(*a, **kw):
        if _pausado.is_set():
            return None
        d = config.THEME_DATA.get("STATS", {})
        for parte in caminho:
            d = d.get(parte, {}) if isinstance(d, dict) else {}
        if not (sempre or _visivel(d)):
            return None
        global _em_andamento
        with _contador:
            _em_andamento += 1
        try:
            return original(*a, **kw)
        finally:
            with _contador:
                _em_andamento -= 1
    f.original = original
    return f


for _cls, _nome, _caminho in _SENSORES:
    setattr(_cls, _nome, staticmethod(_guardado(getattr(_cls, _nome), _caminho)))
# a rede calcula a velocidade pela diferença desde a última leitura: lê sempre para não dar picos
stats.Net.stats = staticmethod(_guardado(stats.Net.stats, ("NET",), sempre=True))


# ------------------------------------------------------------------ troca
def _esperar_fila(limite):
    fim = time.time() + limite
    while not config.update_queue.empty() and time.time() < fim:
        time.sleep(0.02)


def _carregar(pasta):
    pasta_tema = Path(config.MAIN_DIRECTORY) / "res" / "themes" / pasta
    tema = config.load_yaml(pasta_tema / "theme.yaml")
    tema["PATH"] = str(pasta_tema) + "/"
    config.copy_default(copy.deepcopy(config.THEME_DEFAULT), tema)
    return normalizar(tema)


def _atualizar_valores():
    """Desenha os valores logo depois do fundo, sem esperar o próximo ciclo de cada sensor."""
    for cls, nome, _ in _SENSORES:
        if cls in (stats.Weather, stats.Ping):
            continue
        try:
            getattr(cls, nome)()
        except Exception as e:
            logger.debug("Atualização imediata de %s.%s falhou: %s" % (cls.__name__, nome, e))


def trocar_tema(pasta):
    try:
        novo = _carregar(pasta)
    except Exception as e:
        logger.error("Tema %s não carregou: %s" % (pasta, e))
        return "erro"
    atual = config.THEME_DATA.get("display", {})
    nd = novo.get("display", {})
    if nd.get("DISPLAY_ORIENTATION", "portrait") != atual.get("DISPLAY_ORIENTATION", "portrait") \
            or nd.get("DISPLAY_SIZE", '3.5"') != atual.get("DISPLAY_SIZE", '3.5"'):
        return "reiniciar"            # outra orientação/tamanho: só reiniciando
    with _trava:
        inicio = time.time()
        _pausado.set()
        fim = time.time() + 3         # deixa terminar as leituras que já começaram (desenham no tema antigo)
        while _em_andamento > 0 and time.time() < fim:
            time.sleep(0.02)
        _esperar_fila(3)
        config.CONFIG_DATA["config"]["THEME"] = pasta
        config.THEME_DATA = novo
        lcd = _display.lcd
        for chave in [k for k in lcd.image_cache if str(k).startswith(novo["PATH"])]:
            del lcd.image_cache[chave]  # tema editado: o fundo mudou com o mesmo nome de arquivo
        _display.display_static_images()
        _display.display_static_text()
        _pausado.clear()
        _atualizar_valores()
        _esperar_fila(5)
        logger.info("Tema trocado para %s em %.1f s (sem reiniciar)" % (pasta, time.time() - inicio))
    return "ok"


def mudar_brilho(valor):
    valor = max(0, min(100, int(valor)))
    config.CONFIG_DATA["display"]["BRIGHTNESS"] = valor
    _display.lcd.SetBrightness(valor)
    return "ok"


def _atender(con):
    with con:
        con.settimeout(5)
        cmd = con.recv(256).decode("utf-8", "ignore").strip()
        try:
            if cmd == "ping":
                r = "ok"
            elif cmd.startswith("tema "):
                r = trocar_tema(cmd[5:].strip())
            elif cmd.startswith("brilho "):
                r = mudar_brilho(cmd[7:].strip())
            else:
                r = "?"
        except Exception as e:
            logger.error("Comando '%s' falhou: %s" % (cmd, e))
            r = "erro"
        con.sendall((r + "\n").encode("utf-8"))


def _servidor(srv):
    while True:
        try:
            con, _ = srv.accept()
        except OSError:
            return
        threading.Thread(target=_atender, args=(con,), daemon=True).start()


def _abrir_porta():
    # a porta pode estar presa por alguns segundos depois de o main.py anterior fechar: tenta por 20 s
    fim = time.time() + 20
    while True:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if platform.system() != "Windows":   # no Windows esta opção deixaria outro programa usar a mesma porta
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            srv.bind(("127.0.0.1", PORTA))
            srv.listen(4)
            break
        except OSError as e:
            srv.close()
            if time.time() > fim:
                logger.warning("Troca rápida de tema indisponível (porta %d): %s" % (PORTA, e))
                return
            time.sleep(1)
    logger.info("Troca rápida de tema pronta em 127.0.0.1:%d" % PORTA)
    _servidor(srv)


def iniciar(display):
    """Chamado pelo main.py depois que a tela e os sensores começaram."""
    global _display
    _display = display
    threading.Thread(target=_abrir_porta, daemon=True, name="Troca_Tema").start()
