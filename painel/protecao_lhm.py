# PULSE — System Telemetry - proteção contra a queda do LibreHardwareMonitor ao conectar/desconectar dispositivos
#
# O LibreHardwareMonitor 0.9.5 lê os SSDs pela biblioteca DiskInfoToolkit. Ela abre uma thread própria
# (StorageManager.DevicesChangedListener) que acorda sempre que o Windows avisa que um dispositivo entrou ou
# saiu (pendrive, leitor de cartão, celular, a própria tela USB reiniciando...). Quando aparece um disco sem
# partição, IdentifyStorageController() dá NullReferenceException DENTRO dessa thread do .NET; ninguém trata
# o erro e o .NET derruba o processo inteiro (0xC0000005). No PC do usuário: 16/11 23:21, 18/11 22:17 e
# 19/11 00:08, sempre com a mesma pilha no Visualizador de Eventos (.NET Runtime 1026). Para o usuário, o
# painel "reiniciava sozinho": o iniciador reabria o main.py, que resetava e redesenhava a tela.
#
# O Python não consegue capturar esse erro. A saída é parar essa thread logo depois de abrir o
# LibreHardwareMonitor (Thread.Abort, que o .NET Framework 4.8 aceita). Os SSDs que já existiam continuam
# com temperatura e uso; só um disco conectado DEPOIS de o painel abrir não entra até a próxima abertura.
import threading
import time

from library.log import logger

_abortadas = set()


def _thread_de_discos():
    import System
    from System.Reflection import BindingFlags
    for asm in System.AppDomain.CurrentDomain.GetAssemblies():
        if asm.GetName().Name == "DiskInfoToolkit":
            tipo = asm.GetType("DiskInfoToolkit.StorageManager")
            if tipo is None:
                return None, "StorageManager não encontrado"
            campo = tipo.GetField("_DevicesChangedThread", BindingFlags.NonPublic | BindingFlags.Static)
            if campo is None:
                return None, "campo _DevicesChangedThread não encontrado (versão diferente do DiskInfoToolkit)"
            return campo.GetValue(None), ""
    return None, "DiskInfoToolkit não carregado"


def _parar_uma_vez():
    th, motivo = _thread_de_discos()
    if th is None:
        return False, motivo
    chave = th.ManagedThreadId
    if chave in _abortadas or not th.IsAlive:
        return True, ""
    th.Abort()
    _abortadas.add(chave)
    logger.info("Proteção dos sensores: vigia de dispositivos USB do leitor de SSD desligada (ela derrubava o "
                "programa da tela quando um disco sem partição era conectado).")
    return True, ""


def _vigiar():
    # se a biblioteca recriar a thread (ex.: ao recarregar a lista de discos), para de novo
    while True:
        time.sleep(30)
        try:
            _parar_uma_vez()
        except Exception:
            pass


def proteger():
    """Chamado pelo sensors_librehardwaremonitor logo depois de handle.Open() (ver AJUSTES_LHM)."""
    try:
        ok, motivo = _parar_uma_vez()
        if not ok:
            logger.info("Proteção dos sensores: nada a fazer (%s).", motivo)
            return
    except Exception as e:
        logger.warning("Proteção dos sensores indisponível: %s", e)
        return
    threading.Thread(target=_vigiar, name="PULSE_protecao_lhm", daemon=True).start()
