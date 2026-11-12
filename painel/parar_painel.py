# Encerra o painel (main.py rodando na pasta app), inclusive o processo filho do venv.
# Rodado direto, também encerra o iniciador (painel/iniciar.py), que reabriria o main.py.
import os
import time
from pathlib import Path

import psutil

APP = Path(__file__).resolve().parent.parent


def _encerrar(fim_do_comando):
    n = 0
    eu = os.getpid()
    for p in psutil.process_iter(["pid", "cmdline", "cwd"]):
        try:
            if p.pid == eu:
                continue
            cmd = p.info.get("cmdline") or []
            if any(c.replace("\\", "/").endswith(fim_do_comando) for c in cmd) and p.info.get("cwd") \
                    and Path(p.info["cwd"]).resolve() == APP:
                p.kill()
                n += 1
        except Exception:
            pass
    return n


def parar_main():
    """Só o main.py. Se o iniciador estiver rodando, ele abre o main.py de novo sozinho."""
    return _encerrar("main.py")


def parar_iniciador():
    return _encerrar("painel/iniciar.py") + _encerrar("iniciar.py")


def iniciador_rodando():
    eu = os.getpid()
    for p in psutil.process_iter(["pid", "cmdline", "cwd"]):
        try:
            cmd = p.info.get("cmdline") or []
            if p.pid != eu and any(c.replace("\\", "/").endswith("iniciar.py") for c in cmd) \
                    and p.info.get("cwd") and Path(p.info["cwd"]).resolve() == APP:
                return True
        except Exception:
            pass
    return False


def parar_tudo():
    n = parar_iniciador() + _encerrar("config_ui.py")
    time.sleep(0.3)
    return n + parar_main()


if __name__ == "__main__":
    print(f"{parar_tudo()} processo(s) do painel encerrado(s).")
