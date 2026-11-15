# PULSE - escolha da placa de vídeo
#
# Com mais de uma GPU (ex.: Ryzen 5 8500G, que tem a Radeon 740M integrada, junto com uma RX 6650 XT), a
# biblioteca da tela usa a ÚLTIMA placa AMD que tiver sensor de carga, que pode ser a integrada. Aqui:
#   - automático: prefere a placa dedicada (nome RX/RTX/GTX/Arc..., ventoinha, memória própria);
#   - manual: a placa escolhida na janela de configuração;
#   - as placas encontradas, a que está em uso e a escolha ficam em C:\PainelTelemetria\gpus.json
#     (fora da pasta app, então a escolha continua valendo depois de reinstalar).
# escolher() roda dentro do main.py: o sensors_librehardwaremonitor.get_gpu_name() chama esta função
# (ajuste em scripts/montar_pacote.py) e volta para a lógica original se algo der errado.
# ler() e gravar() não dependem da biblioteca da tela (a janela de configuração usa as duas).
import json
import logging
import os
import re
import threading
import time
from pathlib import Path

DESTINO = Path(__file__).resolve().parent.parent.parent
ARQ = DESTINO / "gpus.json"

logger = logging.getLogger("turing")
_trava = threading.Lock()

_DEDICADA = re.compile(r"\b(RX|RTX|GTX|GT|Arc\s*A\d|Arc\s*B\d|Radeon\s*Pro|Radeon\s*VII|Quadro|Titan|Tesla|FirePro)\b", re.I)
_INTEGRADA = re.compile(r"(Graphics\s*$|\b\d{3}M\b|\bVega\s*\d+\b|\bUHD\b|\bIris\b|\bHD Graphics\b)", re.I)


def limpar_nome(nome):
    return " ".join(str(nome).replace("(R)", "").replace("(TM)", "").replace("(tm)", "").split())


# ------------------------------------------------------------------ arquivo gpus.json
def ler():
    try:
        return json.loads(ARQ.read_text(encoding="utf-8"))
    except Exception:
        return {}


def gravar(**campos):
    """Atualiza o gpus.json mantendo o resto. Devolve False se não conseguiu gravar."""
    with _trava:
        try:
            d = ler()
            d.update(campos)
            tmp = ARQ.with_name(ARQ.name + ".tmp")
            tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            for _ in range(5):
                try:
                    os.replace(tmp, ARQ)
                    return True
                except PermissionError:
                    time.sleep(0.05)
        except Exception:
            pass
        return False


# ------------------------------------------------------------------ dentro do main.py
def _info(lhm, hw):
    """Dados de uma placa sem chamar Update() (ler sensores de uma placa que não vai ser usada é desnecessário
    e, em alguns drivers, arriscado)."""
    H = lhm.Hardware
    fabricante = {H.HardwareType.GpuAmd: "AMD", H.HardwareType.GpuNvidia: "Nvidia",
                  H.HardwareType.GpuIntel: "Intel"}.get(hw.HardwareType, "?")
    nome = str(hw.Name)
    ventoinha = carga = False
    memoria = 0.0
    for s in hw.Sensors:
        try:
            tipo, sn = s.SensorType, str(s.Name)
            if tipo in (H.SensorType.Fan, H.SensorType.Control):
                ventoinha = True
            elif tipo == H.SensorType.Load and sn.startswith("GPU Core"):
                carga = True
            elif tipo == H.SensorType.SmallData and "Memory Total" in sn and s.Value is not None:
                memoria = max(memoria, float(s.Value))
        except Exception:
            continue
    limpo = limpar_nome(nome)
    pelo_nome_dedicada = bool(_DEDICADA.search(limpo))
    pelo_nome_integrada = bool(_INTEGRADA.search(limpo))
    integrada = not pelo_nome_dedicada and (pelo_nome_integrada or (not ventoinha and memoria < 2500))
    pontos = (0 if integrada else 100) + (10 if ventoinha else 0) + (5 if carga else 0) + min(memoria, 64000) / 1024
    return {"nome": nome, "fabricante": fabricante, "integrada": integrada, "memoria_mb": round(memoria),
            "ventoinha": ventoinha, "pontos": round(pontos, 1)}


def escolher(lhm):
    """Nome da placa que o PULSE vai usar (substitui sensors_librehardwaremonitor.get_gpu_name)."""
    H = lhm.Hardware.HardwareType
    placas = [hw for hw in lhm.handle.Hardware if hw.HardwareType in (H.GpuAmd, H.GpuNvidia, H.GpuIntel)]
    infos = [_info(lhm, hw) for hw in placas]
    escolha = str(ler().get("escolha") or "").strip()
    nomes = [i["nome"] for i in infos]
    descr = "; ".join(f"{limpar_nome(i['nome'])} ({'integrada' if i['integrada'] else 'dedicada'})" for i in infos)

    if not infos:
        logger.warning("Nenhuma placa de vídeo suportada encontrada: os valores da GPU ficam vazios.")
        gravar(detectadas=[], em_uso="", modo="auto", quando=time.time())
        return ""
    if escolha and escolha in nomes:
        usar, modo = escolha, "manual"
        logger.info("Placas de vídeo: %s. Usando %s (escolhida na configuração).", descr, limpar_nome(usar))
    else:
        if escolha:
            logger.warning("A placa de vídeo escolhida (%s) não foi encontrada; voltando para a escolha automática.",
                           escolha)
        usar, modo = max(infos, key=lambda i: i["pontos"])["nome"], "auto"
        if len(infos) > 1:
            logger.info("Placas de vídeo: %s. Usando %s (automático: prefere a placa dedicada).",
                        descr, limpar_nome(usar))
        else:
            logger.info("Placa de vídeo: %s.", descr)
    gravar(detectadas=infos, em_uso=usar, modo=modo, quando=time.time())
    return usar
