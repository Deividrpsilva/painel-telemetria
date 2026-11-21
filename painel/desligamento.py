# PULSE — System Telemetry - apagar a tela ao desligar, reiniciar, sair da conta ou suspender o Windows
#
# A porta USB continua com energia depois que o Windows desliga (com a Inicialização Rápida ligada, o
# "Desligar" é uma hibernação do sistema; a suspensão também mantém a USB) e a tela 3,5" guarda a última
# imagem enquanto tiver energia. Se ninguém mandar "apagar", ela fica acesa com o PC desligado.
#
# O main.py original já tentava apagar ao receber WM_QUERYENDSESSION, mas:
#   - o "apagar" ia para o fim da fila de envio (atrás de imagens pendentes) e o Windows encerrava antes;
#   - chamava sys.exit() dentro do tratamento da mensagem, o que deixava a resposta ao Windows indefinida;
#   - o iniciador (painel/iniciar.py) via o main.py fechar e o abria de novo em 1,5 s: o novo main.py
#     reiniciava a tela e acendia tudo outra vez, já com o Windows desligando.
# Agora (substitui a tabela de mensagens da janela oculta do main.py, ver AJUSTES_MAIN):
#   - WM_QUERYENDSESSION: grava C:\PainelTelemetria\.desligando (o iniciador não reabre mais nada) e apaga a
#     tela NA HORA (brilho 0 + tela desligada), direto na porta, sem passar pela fila; responde "pode desligar";
#   - WM_ENDSESSION: se o desligamento seguiu, apaga de novo (garantia) e fecha; se foi cancelado, acende;
#   - suspensão (PBT_APMSUSPEND): apaga na hora; ao voltar, fecha com o código de reconexão para o iniciador
#     reabrir e redesenhar a tela inteira (a USB costuma reiniciar na volta).
import os
import threading
import time
from pathlib import Path

from library.log import logger

DESTINO = Path(__file__).resolve().parent.parent.parent      # C:\PainelTelemetria
MARCA = DESTINO / ".desligando"
CODIGO_RECONECTAR = 75                                      # o mesmo de painel/tela_usb.py

WM_QUERYENDSESSION = 0x0011
WM_ENDSESSION = 0x0016
WM_POWERBROADCAST = 0x0218
PBT_APMSUSPEND = 0x0004
PBT_APMRESUMESUSPEND = 0x0007
PBT_APMRESUMEAUTOMATIC = 0x0012
ENDSESSION_LOGOFF = 0x80000000

_trava = threading.Lock()
_estado = {"apagada": False, "suspenso": False, "fila": None}


class _Descarte:
    """Fila que joga fora: depois de apagar, um sensor que ainda desenhe não manda nada para a tela."""
    def put(self, *a, **kw):
        pass

    def empty(self):
        return True

    def qsize(self):
        return 0


def _flush_logs():
    import logging
    for h in logging.getLogger().handlers + logger.handlers:
        try:
            h.flush()
        except Exception:
            pass


def gravar_marca(motivo):
    try:
        MARCA.write_text(f"{time.time():.0f} {motivo}\n", encoding="utf-8")
    except OSError:
        pass


def apagar_marca():
    try:
        MARCA.unlink()
    except OSError:
        pass


def apagar_tela(display, motivo, espera_fila=1.5):
    """Brilho 0 e tela desligada, direto na porta. Segura a trava de desenho (ninguém enfileira mais nada),
    deixa a fila terminar o que já começou (até 'espera_fila' s) e descarta o resto."""
    import library.config as config
    import library.scheduler as scheduler
    with _trava:
        scheduler.STOPPING = True            # sensores param de reagendar; erros de envio são só descartados
        lcd = getattr(display, "lcd", None)
        if lcd is None:
            return False
        fila = getattr(config, "update_queue", None)
        trava = getattr(lcd, "update_queue_mutex", None)
        pegou = trava.acquire(timeout=1.0) if trava is not None else False
        try:
            fim = time.monotonic() + espera_fila
            while fila is not None and not fila.empty() and time.monotonic() < fim:
                time.sleep(0.02)
            descartados = 0
            while fila is not None:
                try:
                    fila.get_nowait()
                    descartados += 1
                except Exception:
                    break
            if descartados:
                time.sleep(0.2)              # o envio que estava no meio termina
            fila_original = _estado["fila"] or lcd.update_queue
            lcd.update_queue = None          # sem fila: cada comando vai direto para a porta
            try:
                for nome, args in (("SetBrightness", (0,)), ("ScreenOff", ())):
                    try:
                        getattr(lcd, nome)(*args)
                    except Exception as e:
                        logger.warning("Apagar a tela (%s): %s", nome, e)
                try:
                    s = getattr(lcd, "lcd_serial", None)
                    if s is not None:
                        s.flush()            # espera os bytes saírem antes do Windows encerrar o processo
                except Exception:
                    pass
            finally:
                _estado["fila"] = fila_original
                lcd.update_queue = _Descarte()   # nada mais vai para a tela até acender de novo
        finally:
            if pegou:
                trava.release()
        _estado["apagada"] = True
        logger.info("Tela apagada (%s).", motivo)
        _flush_logs()
        return True


def _acender(display):
    import library.scheduler as scheduler
    scheduler.STOPPING = False
    _estado["apagada"] = False
    lcd = getattr(display, "lcd", None)
    if lcd is not None and _estado["fila"] is not None:
        lcd.update_queue = _estado["fila"]
        _estado["fila"] = None
    try:
        display.turn_on()
        logger.info("Desligamento cancelado: tela acesa de novo.")
    except Exception as e:
        logger.warning("Acender a tela: %s", e)


def mapa_mensagens(original, display):
    """Recebe a tabela de mensagens do main.py original e devolve a do PULSE (as demais mensagens seguem
    para o tratamento original)."""
    tratar_original = original.get(WM_QUERYENDSESSION)

    def query_end(hwnd, msg, wparam, lparam):
        motivo = "sair da conta" if (lparam or 0) & ENDSESSION_LOGOFF else "Windows desligando ou reiniciando"
        logger.info("Windows avisou: %s. Apagando a tela.", motivo)
        gravar_marca(motivo)
        try:
            apagar_tela(display, motivo)
        except Exception as e:
            logger.warning("Não foi possível apagar a tela: %s", e)
        return 1                              # TRUE: pode encerrar

    def end_session(hwnd, msg, wparam, lparam):
        if wparam:                            # o desligamento vai acontecer
            if not _estado["apagada"]:
                try:
                    apagar_tela(display, "fim da sessão", espera_fila=0.5)
                except Exception:
                    pass
            logger.info("Encerrando o programa da tela (Windows desligando).")
            _flush_logs()
            os._exit(0)
        apagar_marca()                        # cancelado (ex.: o usuário cancelou na tela de aplicativos abertos)
        _acender(display)
        return 0

    def energia(hwnd, msg, wparam, lparam):
        if wparam == PBT_APMSUSPEND:
            _estado["suspenso"] = True
            logger.info("Windows entrando em suspensão: apagando a tela.")
            try:
                apagar_tela(display, "suspensão")
            except Exception as e:
                logger.warning("Não foi possível apagar a tela: %s", e)
        elif wparam in (PBT_APMRESUMESUSPEND, PBT_APMRESUMEAUTOMATIC) and _estado["suspenso"]:
            _estado["suspenso"] = False
            logger.info("Windows voltou da suspensão: reabrindo o programa da tela para redesenhar tudo.")
            _flush_logs()
            os._exit(CODIGO_RECONECTAR)
        return 1

    novo = dict(original)
    novo[WM_QUERYENDSESSION] = query_end
    novo[WM_ENDSESSION] = end_session
    novo[WM_POWERBROADCAST] = energia
    if tratar_original is None:
        logger.debug("Tabela de mensagens original sem WM_QUERYENDSESSION")
    logger.info("Desligamento do Windows: a tela apaga ao desligar, reiniciar, sair da conta ou suspender.")
    return novo
