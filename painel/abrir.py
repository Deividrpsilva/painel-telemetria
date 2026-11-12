# PULSE — System Telemetry - atalho "PULSE" (Área de Trabalho / Menu Iniciar)
#
# Pede ao iniciador (ícone da bandeja) para abrir a janela de configuração. Se ele não estiver
# rodando, inicia pela tarefa do Windows (que roda como administrador, necessário para as
# temperaturas) e, em último caso, abre o iniciador direto.
# A splash (painel/splash.py) aparece logo no início, a não ser que a janela já esteja aberta
# (aí ela só é trazida para a frente); a janela de configuração continua o progresso e a fecha.
import platform
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import splash  # noqa: E402

batimento = None
if not splash.splash_aberta():
    import socket
    try:
        socket.create_connection(("127.0.0.1", 5680), timeout=0.3).close()   # janela já aberta
    except OSError:
        splash.abrir_splash()
        batimento = splash.Batimento()

import iniciar  # noqa: E402

if not iniciar.enviar_comando("abrir"):
    splash.avisar("p 8 Iniciando o PULSE...")
    if platform.system() == "Windows":
        try:
            import ctypes
            ctypes.windll.user32.AllowSetForegroundWindow(-1)
        except Exception:
            pass
        subprocess.run(["schtasks", "/Run", "/TN", "PainelTelemetria"], capture_output=True, creationflags=0x08000000)
    for _ in range(30):
        time.sleep(0.5)
        if iniciar.enviar_comando("abrir"):
            break
    else:
        kw = {"creationflags": 0x00000008 | 0x00000200} if platform.system() == "Windows" else {"start_new_session": True}
        subprocess.Popen([iniciar._pythonw(), "painel/iniciar.py", "--abrir"], cwd=str(iniciar.APP), **kw)
if batimento:
    batimento.parar()       # daqui em diante quem dá notícias à splash é a janela de configuração
    splash.avisar("p 12 Abrindo a configuração...")
