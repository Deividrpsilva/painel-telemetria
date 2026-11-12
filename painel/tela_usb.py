# PULSE - conexão com a tela USB (roda dentro do main.py)
#
# A biblioteca turing-smart-screen-python fecha o programa da tela com sys.exit(0) quando não acha a
# porta COM, quando a porta está ocupada por outro programa ou quando a tela demora a voltar do reset
# (ela reabre no mesmo número de COM depois de 5 s fixos). E um erro de escrita no meio do uso mata em
# silêncio a thread que envia as imagens. Em todos esses casos a tela fica apagada ou congelada e
# nada diz o porquê: o iniciador só via "main.py fechou (código 0)".
#
# Este módulo troca só duas funções da biblioteca (LcdComm.openSerial e LcdComm.WriteLine):
#   - procura a tela pela VID 1A86 / PID 5722 (ou série USB35INCHIPSV2) em qualquer número de COM;
#     um COM_PORT fixo no config.yaml continua valendo enquanto abrir;
#   - tela ausente ou porta ocupada: espera e tenta de novo (2 s no primeiro minuto, depois 5 s),
#     dizendo no log o motivo e quem pode estar segurando a porta;
#   - várias telas compatíveis: prefere a que funcionou da última vez (mesma entrada USB e mesmo COM),
#     depois a que tem o número de série da Turing, e usa a primeira que abrir; a escolha vai para o log;
#   - depois do reset da tela a porta é procurada de novo (ela pode voltar com outro número);
#   - falha de escrita durante o uso, porta que sumiu ou envio travado: registra e fecha o main.py com
#     o código 75; o iniciador (painel/iniciar.py) o reabre na hora, e ele reconecta e redesenha a tela.
# O estado fica em C:\PainelTelemetria\tela.json, que a janela de configuração e a bandeja mostram.
# As funções de estado (ler_estado, gravar_estado, resumo) não dependem da biblioteca da tela.
import json
import logging
import os
import platform
import sys
import threading
import time
from pathlib import Path

PAINEL = Path(__file__).resolve().parent
APP = PAINEL.parent
DESTINO = APP.parent
ARQ_ESTADO = DESTINO / "tela.json"
WINDOWS = platform.system() == "Windows"

VID, PID = 0x1A86, 0x5722
SERIE_TURING = "USB35INCHIPSV2"
CODIGO_RECONECTAR = 75          # main.py sai com este código para o iniciador reabrir na hora
ESPERA_CURTA, ESPERA_LONGA, FASE_CURTA = 2.0, 5.0, 60.0
LOG_REPETIDO = 30.0             # s entre mensagens iguais enquanto espera a tela
VIGIA_INTERVALO = 3.0
ENVIO_TRAVADO = 20.0            # s sem conseguir enviar nada com pedidos na fila
VOLTA_ESPERADA = 20.0           # s em que é normal a porta sumir depois do reset da tela ou de uma queda

# nomes de processo de outros programas que costumam segurar a porta da tela
SUSPEITOS = ("turmo", "turzx", "turing", "aida64", "smartmonitor", "usbmonitor", "lcdmonitor", "systemmonitor")

RESUMOS = {
    "iniciando": "iniciando",
    "procurando": "procurando a tela USB",
    "ausente": "tela USB não encontrada",
    "ocupada": "porta ocupada por outro programa",
    "erro_porta": "erro ao abrir a porta",
    "conectada": "conectada",
    "enviando": "enviando imagem",
    "ok": "funcionando",
    "reconectando": "reconectando",
    "parado": "programa da tela parado",
}

MENSAGENS = {   # título do aviso na janela de configuração
    "ausente": "Tela USB não encontrada",
    "ocupada": "A porta {porta} está ocupada por outro programa",
    "erro_porta": "Não foi possível abrir a porta {porta}",
}

logger = logging.getLogger("turing")      # o mesmo logger da biblioteca (library/log.py -> app\log.log)

_trava_estado = threading.Lock()


# ------------------------------------------------------------------ estado (tela.json)
def ler_estado():
    try:
        return json.loads(ARQ_ESTADO.read_text(encoding="utf-8"))
    except Exception:
        return {}


def gravar_estado(estado, **campos):
    """Atualiza o tela.json mantendo o que já estava lá (ex.: a última porta que funcionou). Nunca falha."""
    with _trava_estado:
        try:
            d = ler_estado()
            d.update(campos)
            d["estado"] = estado
            d["quando"] = time.time()
            tmp = ARQ_ESTADO.with_name(ARQ_ESTADO.name + ".tmp")
            tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            for _ in range(5):
                try:
                    os.replace(tmp, ARQ_ESTADO)
                    break
                except PermissionError:          # Windows: alguém lendo o arquivo neste instante
                    time.sleep(0.05)
        except Exception:
            pass


def resumo(d=None):
    """Uma linha curta para a bandeja: 'Tela: funcionando (COM5)'."""
    d = ler_estado() if d is None else d
    e = d.get("estado")
    if not e:
        return ""
    texto = RESUMOS.get(e, e)
    if d.get("porta") and e in ("conectada", "enviando", "ok", "ocupada", "erro_porta", "reconectando"):
        texto += f" ({d['porta']})"
    return "Tela: " + texto


# ------------------------------------------------------------------ portas
def _descrever(p):
    if p is None:
        return "?"
    txt = p.device
    if p.description and p.description not in ("n/a", p.device):
        txt += f" - {p.description}"
    ids = []
    if p.vid is not None:
        ids.append(f"VID {p.vid:04X} PID {p.pid or 0:04X}")
    if p.serial_number:
        ids.append(f"série {p.serial_number}")
    if p.location:
        ids.append(f"USB {p.location}")
    return txt + (f" ({', '.join(ids)})" if ids else "")


def _compativel(p):
    return p.serial_number == SERIE_TURING or (p.vid == VID and p.pid == PID)


def _numero(dev):
    n = "".join(c for c in dev if c.isdigit())
    return (int(n) if n else 1 << 30, dev)


def _candidatos(lcd, portas):
    try:
        from library.lcd.lcd_comm_rev_a import LcdCommRevA
        rev_a = isinstance(lcd, LcdCommRevA)
    except Exception:
        rev_a = True
    if rev_a:
        return [p for p in portas if _compativel(p)]
    try:                                   # outras revisões: a detecção original de cada uma
        achada = type(lcd).auto_detect_com_port()
    except Exception:
        achada = None
    return [p for p in portas if p.device == achada]


def _ordenar(cands):
    lembrada = ler_estado()

    def chave(p):
        return (0 if lembrada.get("local") and p.location == lembrada.get("local") else 1,
                0 if p.device == lembrada.get("porta_boa") else 1,
                0 if p.serial_number == SERIE_TURING else 1,
                _numero(p.device))
    return sorted(cands, key=chave)


def _tipo_erro(e):
    t = f"{e!r} {e}".lower()
    if any(x in t for x in ("permissionerror", "access is denied", "acesso negado", "busy", "in use", "em uso")):
        return "ocupada"
    if any(x in t for x in ("filenotfounderror", "cannot find the file", "não pode encontrar", "no such file")):
        return "ausente"
    return "erro_porta"


def _quem_segura():
    """Programas abertos que podem estar usando a porta da tela (só uma dica para o log)."""
    try:
        import psutil
    except ImportError:
        return []
    meus = {os.getpid(), os.getppid()}
    achados = []
    for pr in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            nome = pr.info["name"] or ""
            if pr.info["pid"] in meus:
                continue
            if any(s in nome.lower() for s in SUSPEITOS):
                achados.append(nome)
            elif nome.lower().startswith("python") and any(str(a).endswith("main.py") for a in (pr.info["cmdline"] or [])):
                try:
                    pasta = pr.cwd()
                except Exception:
                    pasta = "?"
                achados.append(f"outro main.py (PID {pr.info['pid']}, pasta {pasta})")
        except Exception:
            continue
    return sorted(set(achados))


def _parando():
    sch = sys.modules.get("library.scheduler")
    return bool(sch and getattr(sch, "STOPPING", False))


# ------------------------------------------------------------------ abrir a porta (substitui LcdComm.openSerial)
class _Envio:
    ultimo = 0.0                # monotonic do último envio bem-sucedido
    primeira_imagem = False     # main.py já mandou o fundo do tema
    vigia = None


def _abrir_serial(self):
    import serial
    from serial.tools.list_ports import comports

    if getattr(self, "_pulse_cfg", None) is None:          # COM_PORT do config.yaml ("AUTO" ou "COM3")
        self._pulse_cfg = str(self.com_port or "AUTO").strip()
    manual = self._pulse_cfg.upper() != "AUTO"
    inicio = time.monotonic()
    vistas = None
    anunciadas = set()
    ultimo_motivo, ultimo_log = None, 0.0
    # depois do reset da tela (ou de uma queda) a porta some por alguns segundos: isso é esperado
    volta = getattr(self, "_pulse_aberturas", 0) > 0 or ler_estado().get("estado") == "reconectando"
    logger.info("Procurando tela USB... (COM_PORT %s)", self._pulse_cfg)
    gravar_estado("reconectando" if volta else "procurando",
                  mensagem="Aguardando a tela voltar" if volta else "Procurando a tela USB", detalhe="", pid=os.getpid())

    while True:
        try:
            portas = list(comports())
        except Exception as e:
            portas = []
            logger.warning("Não foi possível listar as portas COM: %s", e)
        desc = sorted(_descrever(p) for p in portas)
        if desc != vistas:
            vistas = desc
            logger.info("Portas COM no sistema: %s", "; ".join(desc) if desc else "nenhuma")
        info = {p.device: p for p in portas}
        cands = _ordenar(_candidatos(self, portas))
        tentativas = [self._pulse_cfg] if manual else []
        tentativas += [p.device for p in cands if p.device not in tentativas]

        if len(cands) > 1 and ("varias", tuple(tentativas)) not in anunciadas:
            anunciadas.add(("varias", tuple(tentativas)))
            logger.warning("Encontradas %d telas compatíveis: %s. Vou usar a primeira que abrir, nesta ordem "
                           "(primeiro a que funcionou da última vez, depois a de série %s): %s",
                           len(cands), "; ".join(_descrever(p) for p in cands), SERIE_TURING, ", ".join(tentativas))

        falhas = []
        for dev in tentativas:
            p = info.get(dev)
            if dev not in anunciadas:
                anunciadas.add(dev)
                if p is not None and _compativel(p):
                    logger.info("Dispositivo encontrado: %s", _descrever(p))
                elif manual and dev == self._pulse_cfg:
                    logger.info("Usando a porta fixa do config.yaml: %s%s", dev,
                                "" if p else " (ela não aparece na lista de portas)")
                logger.info("Porta COM identificada: %s", dev)
            try:
                s = serial.Serial(dev, 115200, timeout=1, rtscts=True)
            except Exception as e:
                falhas.append((dev, _tipo_erro(e), e))
                continue
            self.lcd_serial = s
            self.com_port = dev
            self._pulse_aberturas = getattr(self, "_pulse_aberturas", 0) + 1
            self._pulse_listada = p is not None
            _Envio.ultimo = time.monotonic()
            if manual and dev != self._pulse_cfg:
                logger.warning("A porta fixa %s do config.yaml não abriu; usei %s, detectada pela VID/PID.",
                               self._pulse_cfg, dev)
            elif falhas:
                logger.warning("Usando %s porque %s", dev, "; ".join(f"{d} não abriu ({e})" for d, _, e in falhas))
            logger.info("Conexão estabelecida com a tela na porta %s.", dev)
            gravar_estado("conectada", mensagem=f"Conectada na porta {dev}", detalhe="", porta=dev, porta_boa=dev,
                          local=getattr(p, "location", None), serie=getattr(p, "serial_number", None),
                          dispositivo=_descrever(p) if p else dev, pid=os.getpid())
            _iniciar_vigia(self)
            return

        # nenhuma porta abriu: explica o motivo e tenta de novo
        espera = ESPERA_CURTA if time.monotonic() - inicio < FASE_CURTA else ESPERA_LONGA
        if not tentativas:
            tipo, porta, tecnico = "ausente", None, ""
            detalhe = (f"Nenhuma porta COM com VID 1A86 / PID 5722 (série {SERIE_TURING}). Confira o cabo, "
                       "troque de entrada USB e veja em Gerenciador de Dispositivos > Portas (COM e LPT).")
        else:
            tipos = [t for _, t, _ in falhas]
            tipo = "ocupada" if "ocupada" in tipos else ("erro_porta" if "erro_porta" in tipos else "ausente")
            porta, _, erro = next(f for f in falhas if f[1] == tipo)
            if tipo == "ocupada":
                detalhe = f"A porta {porta} existe, mas outro programa está usando."
            elif tipo == "ausente":
                detalhe = f"A porta {porta} não existe mais."
            else:
                detalhe = f"A porta {porta} existe, mas não abriu. Tente outra entrada USB ou reconecte o cabo."
            tecnico = f" Detalhe técnico: {erro}"
        agora = time.monotonic()
        chave = (tipo, porta, tuple(tentativas))
        if volta and tipo == "ausente" and agora - inicio < VOLTA_ESPERADA:
            if ultimo_motivo != "volta":
                logger.info("Aguardando a tela voltar (ela reinicia e pode aparecer em outra porta COM)...")
                ultimo_motivo = "volta"
        elif chave != ultimo_motivo or agora - ultimo_log >= LOG_REPETIDO:
            if tipo == "ocupada" and chave != ultimo_motivo:
                suspeitos = _quem_segura()
                detalhe += (" Programas abertos que podem estar com ela: " + ", ".join(suspeitos) + ". Feche-os"
                            if suspeitos else " Feche o TURMO ou outro programa da tela")
                detalhe += " (inclusive no ícone perto do relógio)."
            logger.warning("%s%s Nova tentativa a cada %.0f s (aguardando há %.0f s).", detalhe, tecnico, espera,
                           agora - inicio)
            gravar_estado(tipo, mensagem=MENSAGENS[tipo].format(porta=porta or "da tela"), detalhe=detalhe + tecnico,
                          porta=porta, pid=os.getpid())
            ultimo_motivo, ultimo_log = chave, agora
        if _parando():
            raise SystemExit(0)
        time.sleep(espera)


# ------------------------------------------------------------------ escrever (substitui LcdComm.WriteLine)
def _escrever_linha(self, line):
    import serial
    try:
        self.serial_write(line)
        if platform.system() == "Darwin":
            self.lcd_serial.flush()
    except serial.SerialTimeoutException:
        logger.warning("(Write line) Too fast! Slow down!")
        return
    except Exception as e:
        falha_comunicacao(f"erro ao escrever na porta {self.com_port}: {type(e).__name__}: {e}")
        return
    _Envio.ultimo = time.monotonic()


_saindo = threading.Lock()


def falha_comunicacao(motivo):
    """A tela parou de responder: registra e fecha o main.py para o iniciador reabrir e redesenhar."""
    if _parando():                        # o programa já está fechando: só descarta o envio
        logger.warning("Falha na comunicação com a tela ao fechar: %s", motivo)
        return
    if not _saindo.acquire(blocking=False):
        while True:                       # outra thread já está cuidando disso
            time.sleep(1)
    logger.error("Falha na comunicação com a tela: %s", motivo)
    logger.warning("Tentando reconectar: o programa da tela será reaberto para reabrir a porta e redesenhar a tela.")
    gravar_estado("reconectando", mensagem="Reconectando com a tela", detalhe=motivo)
    for h in logging.getLogger().handlers + logger.handlers:
        try:
            h.flush()
        except Exception:
            pass
    os._exit(CODIGO_RECONECTAR)


# ------------------------------------------------------------------ vigia: porta que sumiu, envio travado
def _iniciar_vigia(lcd):
    if _Envio.vigia is None:
        _Envio.vigia = threading.Thread(target=_vigiar, args=(lcd,), name="PULSE_vigia_tela", daemon=True)
        _Envio.vigia.start()


def _vigiar(lcd):
    from serial.tools.list_ports import comports
    import library.config as config
    ausente_desde = None
    ultimo_ciclo = time.monotonic()
    while True:
        time.sleep(VIGIA_INTERVALO)
        try:
            agora = time.monotonic()
            if _parando():
                return
            if agora - ultimo_ciclo > 4 * VIGIA_INTERVALO:     # o PC dormiu: recomeça a contagem
                _Envio.ultimo, ausente_desde = agora, None
            ultimo_ciclo = agora
            s = getattr(lcd, "lcd_serial", None)
            if s is None or not s.is_open:                    # fechada de propósito (reset): o openSerial cuida
                ausente_desde = None
                continue
            if getattr(lcd, "_pulse_listada", False):
                if any(p.device == lcd.com_port for p in comports()):
                    ausente_desde = None
                else:
                    ausente_desde = ausente_desde or agora
                    if agora - ausente_desde >= 2 * VIGIA_INTERVALO:
                        falha_comunicacao(f"a porta {lcd.com_port} sumiu da lista de portas (cabo desconectado "
                                          "ou a tela reiniciou)")
            fila = config.update_queue
            pendentes = fila.qsize()
            if pendentes and agora - _Envio.ultimo > ENVIO_TRAVADO:
                falha_comunicacao(f"nada foi enviado à tela em {ENVIO_TRAVADO:.0f} s, com {pendentes} pedidos na "
                                  "fila (envio travado)")
            if not pendentes and _Envio.primeira_imagem and ler_estado().get("estado") == "enviando":
                logger.info("Imagem enviada com sucesso para a tela (%s).", lcd.com_port)
                gravar_estado("ok", mensagem=f"Funcionando na porta {lcd.com_port}", detalhe="")
        except Exception as e:
            logger.warning("Vigia da tela: %s", e)


# ------------------------------------------------------------------ etapas avisadas pelo main.py
def tela_inicializada(display):
    porta = getattr(getattr(display, "lcd", None), "com_port", "?")
    logger.info("Tela inicializada na porta %s (reset, brilho e orientação).", porta)


def envio_iniciado():
    _Envio.primeira_imagem = False
    logger.info("Envio de imagem iniciado (fundo do tema e textos fixos).")
    gravar_estado("enviando", mensagem="Enviando a imagem para a tela", detalhe="")


def envio_concluido(display, fila_vazia):
    _Envio.primeira_imagem = True
    porta = getattr(getattr(display, "lcd", None), "com_port", "?")
    if fila_vazia:
        logger.info("Imagem enviada com sucesso para a tela (%s).", porta)
        gravar_estado("ok", mensagem=f"Funcionando na porta {porta}", detalhe="")
    else:
        import library.config as config
        logger.warning("A imagem inicial ainda não terminou de ir para a tela após 10 s (%d pedidos na fila); "
                       "seguindo. Se a tela não mudar, veja as mensagens acima.", config.update_queue.qsize())


# ------------------------------------------------------------------ instalação
def _excecao_thread(args):
    if args.exc_type is SystemExit:
        return
    logger.error("Erro na thread %s: %s: %s", getattr(args.thread, "name", "?"), args.exc_type.__name__,
                 args.exc_value, exc_info=(args.exc_type, args.exc_value, args.exc_traceback))


def _excecao(tipo, valor, tb):
    if not issubclass(tipo, (SystemExit, KeyboardInterrupt)):
        logger.error("Erro no programa da tela: %s: %s", tipo.__name__, valor, exc_info=(tipo, valor, tb))
    sys.__excepthook__(tipo, valor, tb)


def eh_admin():
    if not WINDOWS:
        return True
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def instalar():
    """Chamado pelo main.py logo depois de carregar o log, antes de qualquer coisa abrir a porta da tela."""
    import library.lcd.lcd_comm as lcd_comm
    lcd_comm.LcdComm.openSerial = _abrir_serial
    lcd_comm.LcdComm.WriteLine = _escrever_linha

    # erros que antes sumiam (pythonw não tem console) passam a ir para o log.log
    threading.excepthook = _excecao_thread
    sys.excepthook = _excecao
    if os.environ.get("PULSE_SAIDA"):        # saída redirecionada pelo iniciador: lá só o que for erro
        for h in logging.getLogger().handlers:
            if type(h) is logging.StreamHandler:
                h.setLevel(logging.ERROR)

    admin = eh_admin()
    logger.info("PULSE: programa da tela iniciado (PID %d, administrador: %s).", os.getpid(), "sim" if admin else "não")
    gravar_estado("iniciando", mensagem="Iniciando o programa da tela", detalhe="", admin=admin, pid=os.getpid())
