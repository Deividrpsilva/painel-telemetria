# Painel de Telemetria - atalho "Painel de Telemetria" (Área de Trabalho / Menu Iniciar)
#
# Pede ao iniciador (ícone da bandeja) para abrir a janela de configuração. Se ele não estiver
# rodando, inicia pela tarefa do Windows (que roda como administrador, necessário para as
# temperaturas) e, em último caso, abre o iniciador direto.
import platform
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import iniciar  # noqa: E402

if not iniciar.enviar_comando("abrir"):
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
