# SPDX-License-Identifier: GPL-3.0-or-later
#
# turing-smart-screen-python - a Python system monitor and library for USB-C displays like Turing Smart Screen or XuanFang
# https://github.com/mathoudebine/turing-smart-screen-python/
#
# Copyright (C) 2021 Matthieu Houdebine (mathoudebine)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# This file allows to add custom data source as sensors and display them in System Monitor themes
# There is no limitation on how much custom data source classes can be added to this file
# See CustomDataExample theme for the theme implementation part

import math
import platform
from abc import ABC, abstractmethod
from typing import List


# Custom data classes must be implemented in this file, inherit the CustomDataSource and implement its 2 methods
class CustomDataSource(ABC):
    @abstractmethod
    def as_numeric(self) -> float:
        # Numeric value will be used for graph and radial progress bars
        # If there is no numeric value, keep this function empty
        pass

    @abstractmethod
    def as_string(self) -> str:
        # Text value will be used for text display and radial progress bar inner text
        # Numeric value can be formatted here to be displayed as expected
        # It is also possible to return a text unrelated to the numeric value
        # If this function is empty, the numeric value will be used as string without formatting
        pass

    @abstractmethod
    def last_values(self) -> List[float]:
        # List of last numeric values will be used for plot graph
        # If you do not want to draw a line graph or if your custom data has no numeric values, keep this function empty
        pass


# Example for a custom data class that has numeric and text values
class ExampleCustomNumericData(CustomDataSource):
    # This list is used to store the last 10 values to display a line graph
    last_val = [math.nan] * 10  # By default, it is filed with math.nan values to indicate there is no data stored

    def as_numeric(self) -> float:
        # Numeric value will be used for graph and radial progress bars
        # Here a Python function from another module can be called to get data
        # Example: self.value = my_module.get_rgb_led_brightness() / audio.system_volume() ...
        self.value = 75.845

        # Store the value to the history list that will be used for line graph
        self.last_val.append(self.value)
        # Also remove the oldest value from history list
        self.last_val.pop(0)

        return self.value

    def as_string(self) -> str:
        # Text value will be used for text display and radial progress bar inner text.
        # Numeric value can be formatted here to be displayed as expected
        # It is also possible to return a text unrelated to the numeric value
        # If this function is empty, the numeric value will be used as string without formatting
        # Example here: format numeric value: add unit as a suffix, and keep 1 digit decimal precision
        return f'{self.value:>5.1f}%'
        # Important note! If your numeric value can vary in size, be sure to display it with a default size.
        # E.g. if your value can range from 0 to 9999, you need to display it with at least 4 characters every time.
        # --> return f'{self.as_numeric():>4}%'
        # Otherwise, part of the previous value can stay displayed ("ghosting") after a refresh

    def last_values(self) -> List[float]:
        # List of last numeric values will be used for plot graph
        return self.last_val


# Example for a custom data class that only has text values
class ExampleCustomTextOnlyData(CustomDataSource):
    def as_numeric(self) -> float:
        # If there is no numeric value, keep this function empty
        pass

    def as_string(self) -> str:
        # If a custom data class only has text values, it won't be possible to display graph or radial bars
        return "Python: " + platform.python_version()

    def last_values(self) -> List[float]:
        # If a custom data class only has text values, it won't be possible to display line graph
        pass


# =====================================================================================
# PainelTelemetria: sensores próprios (volume, FPS, frametime, SSD)
# =====================================================================================
# Obs.: o System Monitor cria uma instância nova de cada classe a cada atualização,
# por isso o histórico fica em atributos de classe.
import sys
import time
import logging

_log = logging.getLogger("PainelTelemetria")


def _lhm_module():
    """Retorna o módulo do LibreHardwareMonitor se ele já foi carregado pelo System Monitor (Windows/admin)."""
    return sys.modules.get("library.sensors.sensors_librehardwaremonitor")


def _push(history: List[float], value: float, size: int = 40):
    if len(history) != size:
        history[:] = [math.nan] * size
    history.append(value)
    history.pop(0)


# ---------------- FPS e frametime ----------------
class _FpsReader:
    """Lê o FPS do jogo em tela cheia pelo sensor 'Fullscreen FPS' que o LibreHardwareMonitor expõe
    para placas AMD (via driver Adrenalin). Retorna 0 quando nenhum jogo está rodando."""
    last_read = 0.0
    fps = 0.0

    @classmethod
    def read(cls) -> float:
        now = time.monotonic()
        if now - cls.last_read < 0.5:  # FrameTime e Fps leem o mesmo valor no mesmo ciclo
            return cls.fps
        cls.last_read = now
        cls.fps = 0.0
        lhm = _lhm_module()
        if lhm is None:
            return cls.fps
        try:
            gpu = lhm.Gpu.get_gpu_to_use()
            if gpu is not None:
                for sensor in gpu.Sensors:
                    if sensor.SensorType == lhm.Hardware.SensorType.Factor and "FPS" in str(sensor.Name) \
                            and sensor.Value is not None and float(sensor.Value) > 0:
                        cls.fps = float(sensor.Value)
                        break
        except Exception as e:
            _log.debug("FPS indisponível: %s" % e)
        cls._sessao(now)
        return cls.fps

    # ---- média da sessão de jogo ----
    # Uma sessão começa quando aparece FPS e termina depois de 15 s sem FPS (jogo fechado/minimizado).
    soma = 0.0
    amostras = 0
    ultimo_fps = 0.0  # instante (monotonic) da última leitura com FPS

    @classmethod
    def _sessao(cls, now):
        if cls.fps > 0:
            if now - cls.ultimo_fps > 15:
                cls.soma, cls.amostras = 0.0, 0
            cls.soma += cls.fps
            cls.amostras += 1
            cls.ultimo_fps = now

    @classmethod
    def media(cls) -> float:
        return cls.soma / cls.amostras if cls.amostras else 0.0


class Fps(CustomDataSource):
    history = []

    def as_numeric(self) -> float:
        fps = _FpsReader.read()
        _push(Fps.history, fps if fps > 0 else math.nan)
        return fps

    def as_string(self) -> str:
        fps = _FpsReader.fps
        return f"{int(round(fps)):>3}" if fps > 0 else " --"

    def last_values(self) -> List[float]:
        return Fps.history


class FrameTime(CustomDataSource):
    def as_numeric(self) -> float:
        fps = _FpsReader.read()
        return 1000.0 / fps if fps > 0 else math.nan

    def as_string(self) -> str:
        fps = _FpsReader.fps
        return f"{1000.0 / fps:5.1f} ms" if fps > 0 else "   -- ms"

    def last_values(self) -> List[float]:
        pass


# ---------------- SSD (temperatura e atividade) ----------------
def _storage_sensors(sensor_type_name: str, name_filter: str = None) -> List[float]:
    lhm = _lhm_module()
    values = []
    if lhm is None:
        return values
    try:
        stype = getattr(lhm.Hardware.SensorType, sensor_type_name)
        for hw in lhm.handle.Hardware:
            if hw.HardwareType == lhm.Hardware.HardwareType.Storage:
                hw.Update()
                for sensor in hw.Sensors:
                    if sensor.SensorType == stype and sensor.Value is not None \
                            and (name_filter is None or name_filter in str(sensor.Name)):
                        values.append(float(sensor.Value))
                        if sensor_type_name == "Temperature":
                            break  # 1ª temperatura de cada SSD (a principal)
    except Exception as e:
        _log.debug("SSD indisponível: %s" % e)
    return values


class SsdTemperatura(CustomDataSource):
    """Maior temperatura entre os SSDs/discos."""

    def as_numeric(self) -> float:
        temps = _storage_sensors("Temperature")
        t = max(temps) if temps else math.nan
        _cor_dinamica("SsdTemperatura", t)
        return t

    def as_string(self) -> str:
        t = self.as_numeric()
        return f"{int(t):>3}°C" if not math.isnan(t) else " --°C"

    def last_values(self) -> List[float]:
        pass


class SsdAtividade(CustomDataSource):
    """Maior atividade (% do tempo ocupado) entre os SSDs/discos."""
    value = math.nan

    def as_numeric(self) -> float:
        loads = _storage_sensors("Load", "Total Activity")
        if loads:
            SsdAtividade.value = max(loads)
        else:
            # Sem LHM: estima pela variação de tempo ocupado do psutil
            SsdAtividade.value = _psutil_disk_busy()
        return SsdAtividade.value

    def as_string(self) -> str:
        v = SsdAtividade.value
        return f"{int(v):>3}%" if not math.isnan(v) else " --%"

    def last_values(self) -> List[float]:
        pass


_busy_prev = None


def _psutil_disk_busy() -> float:
    global _busy_prev
    try:
        import psutil
        c = psutil.disk_io_counters()
        busy_ms = getattr(c, "busy_time", None)
        if busy_ms is None:
            return math.nan
        now = time.monotonic()
        prev, _busy_prev = _busy_prev, (now, busy_ms)
        if prev is None:
            return 0.0
        return max(0.0, min(100.0, (busy_ms - prev[1]) / ((now - prev[0]) * 10.0)))
    except Exception:
        return math.nan


# ---------------- Volume do sistema ----------------
class _VolumeReader:
    endpoint = None

    @classmethod
    def get(cls, microfone: bool = False):
        """Retorna (volume 0-100, mudo) ou (nan, False) se não for possível ler."""
        if platform.system() != "Windows":
            return math.nan, False
        try:
            import comtypes
            try:
                comtypes.CoInitialize()  # cada thread do agendador precisa inicializar o COM
            except OSError:
                pass
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            speakers = AudioUtilities.GetMicrophone() if microfone else AudioUtilities.GetSpeakers()
            if speakers is None:
                return math.nan, False
            if hasattr(speakers, "EndpointVolume"):  # pycaw >= 20240316
                endpoint = speakers.EndpointVolume
            else:
                from ctypes import cast, POINTER
                from comtypes import CLSCTX_ALL
                iface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                endpoint = cast(iface, POINTER(IAudioEndpointVolume))
            return endpoint.GetMasterVolumeLevelScalar() * 100.0, bool(endpoint.GetMute())
        except Exception as e:
            _log.debug("Volume indisponível: %s" % e)
            return math.nan, False


class Volume(CustomDataSource):
    value = math.nan
    muted = False

    def as_numeric(self) -> float:
        Volume.value, Volume.muted = _VolumeReader.get()
        return 0.0 if Volume.muted else Volume.value

    def as_string(self) -> str:
        if Volume.muted:
            return "MUDO"
        return f"{int(round(Volume.value)):>3}%" if not math.isnan(Volume.value) else " --%"

    def last_values(self) -> List[float]:
        pass


class FpsMedio(CustomDataSource):
    """Média de FPS da sessão de jogo atual (ou da última, depois que o jogo fecha)."""

    def as_numeric(self) -> float:
        _FpsReader.read()
        return _FpsReader.media()

    def as_string(self) -> str:
        m = _FpsReader.media()
        return f"méd {int(round(m)):>3}" if m > 0 else "méd  --"

    def last_values(self) -> List[float]:
        pass


class FpsMedioGrande(CustomDataSource):
    """Mesma média, só o número (para o layout sem gráfico)."""

    def as_numeric(self) -> float:
        _FpsReader.read()
        return _FpsReader.media()

    def as_string(self) -> str:
        m = _FpsReader.media()
        return f"{int(round(m)):>3}" if m > 0 else " --"

    def last_values(self) -> List[float]:
        pass


# ---------------- VRAM ----------------
class Vram(CustomDataSource):
    """Memória de vídeo usada/total da GPU monitorada (LibreHardwareMonitor)."""
    usado = math.nan
    total = math.nan
    pct = math.nan

    def as_numeric(self) -> float:
        mod = _lhm_module() or sys.modules.get("library.sensors.sensors_python")
        Vram.usado = Vram.total = Vram.pct = math.nan
        if mod is not None:
            try:
                _load, pct, usado_mb, total_mb, _temp = mod.Gpu.stats()
                Vram.pct, Vram.usado, Vram.total = pct, usado_mb, total_mb
                if (math.isnan(pct) or pct is None) and total_mb and not math.isnan(total_mb):
                    Vram.pct = 100.0 * usado_mb / total_mb
            except Exception as e:
                _log.debug("VRAM indisponível: %s" % e)
        return Vram.pct

    def as_string(self) -> str:
        u, t = Vram.usado, Vram.total
        if u is None or t is None or math.isnan(u) or math.isnan(t) or t <= 0:
            return "VRAM --"
        return f"VRAM {u / 1024:4.1f}/{t / 1024:.0f} GB"

    def last_values(self) -> List[float]:
        pass



# =====================================================================================
# Rodada 2: cores dinâmicas, temperaturas, consumo (W), nomes do hardware, microfone
# =====================================================================================
def _cor_dinamica(nome: str, valor: float):
    """Troca a cor do texto/barra deste sensor conforme faixas definidas no tema:
       CUSTOM.<nome>.COR_DINAMICA: {LIMITES: [70, 85], CORES: ["verde", "amarelo", "vermelho"]}"""
    try:
        import library.config as config
        dados = config.THEME_DATA["STATS"]["CUSTOM"].get(nome) or {}
        regra = dados.get("COR_DINAMICA")
        if not regra or valor is None or math.isnan(valor):
            return
        limites, cores = regra["LIMITES"], regra["CORES"]
        idx = sum(1 for lim in limites if valor >= lim)
        cor = cores[min(idx, len(cores) - 1)]
        for parte, chave in (("TEXT", "FONT_COLOR"), ("GRAPH", "BAR_COLOR"), ("RADIAL", "BAR_COLOR")):
            if parte in dados and isinstance(dados[parte], dict):
                dados[parte][chave] = cor
    except Exception as e:
        _log.debug("Cor dinâmica falhou: %s" % e)


def _sensores_mod():
    return _lhm_module() or sys.modules.get("library.sensors.sensors_python")


def _fmt_temp(t):
    return f"{int(round(t)):>3}°C" if t is not None and not math.isnan(t) else " --°C"


class TempCpu(CustomDataSource):
    def as_numeric(self) -> float:
        t = math.nan
        mod = _sensores_mod()
        try:
            t = float(mod.Cpu.temperature()) if mod else math.nan
        except Exception:
            pass
        TempCpu.v = t
        _cor_dinamica("TempCpu", t)
        return t

    def as_string(self) -> str:
        return _fmt_temp(getattr(TempCpu, "v", math.nan))

    def last_values(self) -> List[float]:
        pass


class TempGpu(CustomDataSource):
    def as_numeric(self) -> float:
        t = math.nan
        mod = _sensores_mod()
        try:
            t = float(mod.Gpu.stats()[4]) if mod else math.nan
        except Exception:
            pass
        TempGpu.v = t
        _cor_dinamica("TempGpu", t)
        return t

    def as_string(self) -> str:
        return _fmt_temp(getattr(TempGpu, "v", math.nan))

    def last_values(self) -> List[float]:
        pass


# ---------------- consumo de energia (W) ----------------
def _potencia(tipo: str) -> float:
    """tipo = 'cpu' ou 'gpu'. Lê sensores Power do LibreHardwareMonitor."""
    lhm = _lhm_module()
    if lhm is None:
        return math.nan
    try:
        H = lhm.Hardware
        if tipo == "cpu":
            hw = lhm.get_hw_and_update(H.HardwareType.Cpu)
        else:
            hw = lhm.Gpu.get_gpu_to_use()
        if hw is None:
            return math.nan
        valores = {}
        for s in hw.Sensors:
            if s.SensorType == H.SensorType.Power and s.Value is not None:
                valores[str(s.Name)] = float(s.Value)
        if not valores:
            return math.nan
        for preferido in ("Package", "PPT", "Total", "Board"):
            for nome, v in valores.items():
                if preferido.lower() in nome.lower():
                    return v
        return max(valores.values())
    except Exception as e:
        _log.debug("Potência indisponível: %s" % e)
        return math.nan


def _fmt_w(w):
    return f"{int(round(w)):>3} W" if w is not None and not math.isnan(w) else " -- W"


class PotCpu(CustomDataSource):
    def as_numeric(self) -> float:
        PotCpu.v = _potencia("cpu")
        _cor_dinamica("PotCpu", PotCpu.v)
        return PotCpu.v

    def as_string(self) -> str:
        return _fmt_w(PotCpu.v)

    def last_values(self) -> List[float]:
        pass


class PotGpu(CustomDataSource):
    def as_numeric(self) -> float:
        PotGpu.v = _potencia("gpu")
        _cor_dinamica("PotGpu", PotGpu.v)
        return PotGpu.v

    def as_string(self) -> str:
        return _fmt_w(PotGpu.v)

    def last_values(self) -> List[float]:
        pass


class PotTotal(CustomDataSource):
    """CPU + GPU (o restante do PC não é medido pelos sensores)."""

    def as_numeric(self) -> float:
        partes = [v for v in (_potencia("cpu"), _potencia("gpu")) if not math.isnan(v)]
        PotTotal.v = sum(partes) if partes else math.nan
        return PotTotal.v

    def as_string(self) -> str:
        return _fmt_w(PotTotal.v)

    def last_values(self) -> List[float]:
        pass


# ---------------- nomes do hardware (lidos uma vez) ----------------
class _Hw:
    cache = {}

    @classmethod
    def _wmi(cls, consulta_ps: str):
        if platform.system() != "Windows":
            return None
        import json as _json
        import subprocess
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-Command", consulta_ps + " | ConvertTo-Json -Compress"],
                               capture_output=True, text=True, timeout=20, creationflags=0x08000000)
            dados = _json.loads(r.stdout) if r.stdout.strip() else None
            return dados if isinstance(dados, list) else ([dados] if dados else [])
        except Exception as e:
            _log.debug("WMI falhou: %s" % e)
            return None

    @classmethod
    def cpu(cls):
        if "cpu" not in cls.cache:
            nome = ""
            lhm = _lhm_module()
            try:
                if lhm:
                    hw = lhm.get_hw_and_update(lhm.Hardware.HardwareType.Cpu)
                    nome = str(hw.Name) if hw else ""
            except Exception:
                pass
            if not nome and platform.system() == "Windows":
                try:
                    import winreg
                    k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
                    nome = winreg.QueryValueEx(k, "ProcessorNameString")[0]
                except Exception:
                    pass
            if not nome:
                nome = platform.processor() or "CPU"
            cls.cache["cpu"] = " ".join(nome.replace("(R)", "").replace("(TM)", "").split())
        return cls.cache["cpu"]

    @classmethod
    def gpu(cls):
        if "gpu" not in cls.cache:
            nome = ""
            lhm = _lhm_module()
            try:
                if lhm:
                    hw = lhm.Gpu.get_gpu_to_use()
                    nome = str(hw.Name) if hw else ""
            except Exception:
                pass
            if not nome:
                placas = cls._wmi("Get-CimInstance Win32_VideoController | Select-Object Name, AdapterRAM") or []
                nomes = [p.get("Name", "") for p in placas if p.get("Name")]
                # prefere placa dedicada (as integradas costumam ter "Graphics" no nome)
                nomes.sort(key=lambda n: ("Graphics" in n, n))
                nome = nomes[0] if nomes else "GPU"
            cls.cache["gpu"] = nome.replace("(R)", "").replace("(TM)", "").strip()
        return cls.cache["gpu"]

    @classmethod
    def ram(cls):
        if "ram" not in cls.cache:
            texto = ""
            pentes = cls._wmi("Get-CimInstance Win32_PhysicalMemory | Select-Object Capacity, Speed, "
                              "ConfiguredClockSpeed, SMBIOSMemoryType, Manufacturer, PartNumber")
            if pentes:
                tipos = {20: "DDR", 21: "DDR2", 24: "DDR3", 26: "DDR4", 34: "DDR5", 35: "LPDDR5"}
                total = sum(int(p.get("Capacity") or 0) for p in pentes) / 1024 ** 3
                vel = max(int(p.get("ConfiguredClockSpeed") or p.get("Speed") or 0) for p in pentes)
                tipo = tipos.get(int(pentes[0].get("SMBIOSMemoryType") or 0), "")
                tam = int(pentes[0].get("Capacity") or 0) / 1024 ** 3
                fab = (pentes[0].get("Manufacturer") or "").strip()
                fab = "" if fab.lower() in ("", "unknown", "undefined") or fab.startswith("0") else fab
                texto = f"{total:.0f} GB {tipo} {vel} MHz ({len(pentes)}x{tam:.0f})".replace("  ", " ")
                if fab:
                    texto = f"{fab} {texto}"
            if not texto:
                try:
                    import psutil
                    texto = f"{psutil.virtual_memory().total / 1024 ** 3:.0f} GB"
                except Exception:
                    texto = "RAM"
            cls.cache["ram"] = texto
        return cls.cache["ram"]


def _cortar(txt, n):
    return txt if len(txt) <= n else txt[:n - 1] + "…"


class NomeCpu(CustomDataSource):
    def as_numeric(self) -> float:
        return math.nan

    def as_string(self) -> str:
        return _cortar(_Hw.cpu(), 34)

    def last_values(self) -> List[float]:
        pass


class NomeGpu(CustomDataSource):
    def as_numeric(self) -> float:
        return math.nan

    def as_string(self) -> str:
        return _cortar(_Hw.gpu(), 34)

    def last_values(self) -> List[float]:
        pass


class NomeRam(CustomDataSource):
    def as_numeric(self) -> float:
        return math.nan

    def as_string(self) -> str:
        return _cortar(_Hw.ram(), 34)

    def last_values(self) -> List[float]:
        pass


# ---------------- microfone ----------------
class Microfone(CustomDataSource):
    value = math.nan
    muted = False

    def as_numeric(self) -> float:
        Microfone.value, Microfone.muted = _VolumeReader.get(microfone=True)
        return 0.0 if Microfone.muted else Microfone.value

    def as_string(self) -> str:
        if Microfone.muted:
            return "MUDO"
        return f"{int(round(Microfone.value)):>3}%" if not math.isnan(Microfone.value) else " --%"

    def last_values(self) -> List[float]:
        pass


class VramCurta(Vram):
    """Mesma VRAM, sem o prefixo (ex.: "3.3/8 GB")."""

    def as_string(self) -> str:
        return super().as_string().replace("VRAM ", "", 1)
