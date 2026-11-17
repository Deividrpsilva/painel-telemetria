# PULSE — System Telemetry - gerador de temas personalizados
#
# Cada tema do usuário é um JSON em C:\PainelTelemetria\temas\<pasta>.json (blocos, ordem, cores,
# estilo...). Este módulo transforma esse JSON em res/themes/<pasta>/{background.png, theme.yaml,
# preview.png}, no formato do turing-smart-screen-python.
#
# Linha de comando (a partir da pasta app):
#   python painel/gerador.py                 regenera todos os temas do usuário (cria os modelos se não houver)
#   python painel/gerador.py arquivo.json    gera só esse tema
import copy
import json
import os
import re
import sys
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont, ImageColor

APP_DIR = Path(__file__).resolve().parent.parent
DESTINO = APP_DIR.parent
TEMAS_USUARIO = DESTINO / "temas"          # fica fora de app/, sobrevive a reinstalações
THEMES_DIR = APP_DIR / "res" / "themes"
FONTS_DIR = APP_DIR / "res" / "fonts"
TEMA_PADRAO = "PainelTelemetria"
W, H = 320, 480

# ----------------------------------------------------------------------------------------------
# Catálogo
# ----------------------------------------------------------------------------------------------
BLOCOS_INFO = {
    "relogio": "Relógio e data",
    "hardware": "Nome e modelo (CPU, GPU, RAM)",
    "cpu_gpu": "CPU e GPU (uso, temperatura, clock, VRAM, W)",
    "ram": "Memória RAM",
    "fps": "FPS, frametime e média da sessão",
    "energia": "Consumo de energia (W)",
    "rede": "Rede (download e upload)",
    "ssd": "SSD (temperatura, atividade, disco C:)",
    "volume": "Áudio (alto-falante e microfone)",
}

FONTES = {  # nome visível -> (bold, medium, extra-bold usada nos números grandes)
    "JetBrains Mono": ("jetbrains-mono/JetBrainsMono-Bold.ttf", "jetbrains-mono/JetBrainsMono-Medium.ttf",
                       "jetbrains-mono/JetBrainsMono-ExtraBold.ttf"),
    "Roboto Mono": ("roboto-mono/RobotoMono-Bold.ttf", "roboto-mono/RobotoMono-Medium.ttf",
                    "roboto-mono/RobotoMono-Bold.ttf"),
    "Roboto Mono Fina": ("roboto-mono/RobotoMono-Regular.ttf", "roboto-mono/RobotoMono-Light.ttf",
                         "roboto-mono/RobotoMono-Medium.ttf"),
    "Generale (retrô)": ("generale-mono/GeneraleMonoA.ttf", "generale-mono/GeneraleMonoA.ttf",
                         "generale-mono/GeneraleMonoA.ttf"),
    # a fonte digital não tem "°" e fica ilegível pequena: só os números grandes usam ela
    "Digital (LED)": ("jetbrains-mono/JetBrainsMono-Bold.ttf", "jetbrains-mono/JetBrainsMono-Medium.ttf",
                      "digital/DIGITAL-7.TTF"),
}
ESCALA_FONTE = {"Digital (LED)": 1.15}
DESLOC_Y_FONTE = {"Digital (LED)": 4}

PALETAS = {
    "Neon": {
        "fundo": {"topo": "#080b14", "base": "#0e0a1a", "cartao": "#141928", "borda": "#242c42",
                  "texto": "#e1e8f5", "rotulo": "#7884a0", "trilho": "#283046"},
        "cores": {"relogio": "#3dd6f5", "cpu": "#3dd6f5", "gpu": "#ff4fa3", "ram": "#a77dff", "fps": "#ffa03c",
                  "rede": "#50e696", "upload": "#ffa03c", "ssd": "#fad250", "volume": "#3dd6f5",
                  "microfone": "#ff4fa3", "energia": "#fad250", "hardware": "#a77dff"},
    },
    "Grafite": {
        "fundo": {"topo": "#0c0c0e", "base": "#141416", "cartao": "#1c1c20", "borda": "#2c2c32",
                  "texto": "#f0f0f0", "rotulo": "#8a8a92", "trilho": "#303036"},
        "cores": {"relogio": "#ffffff", "cpu": "#e8e8e8", "gpu": "#e8e8e8", "ram": "#c8c8c8", "fps": "#ffffff",
                  "rede": "#d0d0d0", "upload": "#9a9aa2", "ssd": "#c8c8c8", "volume": "#e8e8e8",
                  "microfone": "#b0b0b8", "energia": "#e8e8e8", "hardware": "#c8c8c8"},
    },
    "Oceano": {
        "fundo": {"topo": "#04121c", "base": "#062030", "cartao": "#0a2638", "borda": "#16405a",
                  "texto": "#e0f4ff", "rotulo": "#6f9ab4", "trilho": "#163a50"},
        "cores": {"relogio": "#4fd1ff", "cpu": "#4fd1ff", "gpu": "#3cf0d2", "ram": "#7aa8ff", "fps": "#ffd166",
                  "rede": "#3cf0d2", "upload": "#ffd166", "ssd": "#9be7ff", "volume": "#4fd1ff",
                  "microfone": "#3cf0d2", "energia": "#ffd166", "hardware": "#7aa8ff"},
    },
    "Pôr do sol": {
        "fundo": {"topo": "#160812", "base": "#22090c", "cartao": "#2a1018", "borda": "#4a1e2a",
                  "texto": "#fff0e6", "rotulo": "#b48a8a", "trilho": "#45202a"},
        "cores": {"relogio": "#ff9a3c", "cpu": "#ff9a3c", "gpu": "#ff4f6e", "ram": "#ffcf5c", "fps": "#ff6fb5",
                  "rede": "#ffcf5c", "upload": "#ff4f6e", "ssd": "#ff9a3c", "volume": "#ff9a3c",
                  "microfone": "#ff6fb5", "energia": "#ffcf5c", "hardware": "#ff9a3c"},
    },
    "Matrix": {
        "fundo": {"topo": "#020804", "base": "#030c06", "cartao": "#07140b", "borda": "#123a1c",
                  "texto": "#c8ffd4", "rotulo": "#4f8a5c", "trilho": "#103018"},
        "cores": {"relogio": "#39ff6a", "cpu": "#39ff6a", "gpu": "#39ff6a", "ram": "#39ff6a", "fps": "#b6ff39",
                  "rede": "#39ff6a", "upload": "#b6ff39", "ssd": "#39ff6a", "volume": "#39ff6a",
                  "microfone": "#b6ff39", "energia": "#b6ff39", "hardware": "#39ff6a"},
    },
    "Rosa": {
        "fundo": {"topo": "#14070f", "base": "#1c0a18", "cartao": "#260f20", "borda": "#45203c",
                  "texto": "#ffe6f4", "rotulo": "#b07ea0", "trilho": "#401c36"},
        "cores": {"relogio": "#ff7ac8", "cpu": "#ff7ac8", "gpu": "#c77dff", "ram": "#ffa6d9", "fps": "#ffd1ec",
                  "rede": "#c77dff", "upload": "#ff7ac8", "ssd": "#ffa6d9", "volume": "#ff7ac8",
                  "microfone": "#c77dff", "energia": "#ffd1ec", "hardware": "#c77dff"},
    },
    "AMD Vermelho": {
        "fundo": {"topo": "#0a0a0a", "base": "#140606", "cartao": "#1a0d0d", "borda": "#3a1414",
                  "texto": "#f5f5f5", "rotulo": "#9a7a7a", "trilho": "#3a1a1a"},
        "cores": {"relogio": "#ed1c24", "cpu": "#ed1c24", "gpu": "#ff5a36", "ram": "#ff8a80", "fps": "#ffffff",
                  "rede": "#ff5a36", "upload": "#ffffff", "ssd": "#ff8a80", "volume": "#ed1c24",
                  "microfone": "#ff8a80", "energia": "#ffffff", "hardware": "#ff8a80"},
    },
    "Editor (One Dark)": {  # pensada para o layout de código
        "fundo": {"topo": "#1e2127", "base": "#21252b", "cartao": "#282c34", "borda": "#3a3f4b",
                  "texto": "#abb2bf", "rotulo": "#5c6370", "trilho": "#3a3f4b"},
        "cores": {"relogio": "#c678dd", "cpu": "#e06c75", "gpu": "#61afef", "ram": "#e5c07b", "fps": "#d19a66",
                  "rede": "#98c379", "upload": "#56b6c2", "ssd": "#e5c07b", "volume": "#56b6c2",
                  "microfone": "#c678dd", "energia": "#d19a66", "hardware": "#98c379"},
    },
}

OPCOES_PADRAO = {
    "layout": "cartoes",            # cartoes | codigo
    # estilo geral
    "fonte_numeros": "JetBrains Mono",
    "estilo_cartao": "cartao",      # cartao | contorno | nenhum
    "cantos": 8,
    "faixa_cor": True,
    # temperatura com cor dinâmica
    "temp_dinamica": True,
    "temp_limites": [70, 85],
    "temp_cores": ["#3ee07f", "#ffc93c", "#ff4d4d"],
    # relógio
    "segundos": False,
    "relogio_12h": False,
    "formato_data": "completo",     # completo | curto | dia_semana | nenhum
    # cpu / gpu
    "mostrar_cpu": True,
    "mostrar_gpu": True,
    "estilo_uso": "medidor",        # medidor | barra
    "cpu_extra": "clock",           # clock | potencia | nenhum
    "gpu_extra": "vram",            # vram | potencia | nenhum
    # ram
    "ram_detalhes": True,
    "ram_modelo": False,            # mostra o modelo da RAM no lugar de usada/livre
    # fps
    "fps_media": True,
    "fps_grafico": True,
    "fps_grande": False,
    "fps_max_grafico": 165,
    # rede
    "rede_grafico": True,
    # ssd
    "ssd_livre": True,
    # áudio
    "volume_mic": True,
}

PADRAO = {
    "nome": "Meu painel",
    "paleta": "Neon",
    "fundo": copy.deepcopy(PALETAS["Neon"]["fundo"]),
    "cores": copy.deepcopy(PALETAS["Neon"]["cores"]),
    "blocos": [{"id": b, "ativo": b not in ("hardware", "energia")} for b in BLOCOS_INFO],
    "opcoes": copy.deepcopy(OPCOES_PADRAO),
    "imagem_fundo": "",
}


def _pal(nome):
    return {"paleta": nome, "fundo": copy.deepcopy(PALETAS[nome]["fundo"]),
            "cores": copy.deepcopy(PALETAS[nome]["cores"])}


def _blocos(*ativos):
    ordem = list(ativos) + [b for b in BLOCOS_INFO if b not in ativos]
    return [{"id": b, "ativo": b in ativos} for b in ordem]


MODELOS = {
    "Padrão": {},
    "Trabalho / Produtividade": dict(
        nome="Trabalho", **_pal("Oceano"),
        blocos=_blocos("relogio", "hardware", "cpu_gpu", "ram", "rede", "ssd", "volume"),
        opcoes={"mostrar_gpu": False, "cpu_extra": "clock", "ram_detalhes": True, "ssd_livre": True,
                "formato_data": "completo", "volume_mic": True}),
    "Jogos": dict(
        nome="Jogos", **_pal("AMD Vermelho"),
        blocos=_blocos("relogio", "fps", "cpu_gpu", "energia", "volume"),
        opcoes={"fps_grande": True, "fps_media": True, "mostrar_cpu": False, "gpu_extra": "vram",
                "formato_data": "nenhum", "segundos": False}),
    "Código (programação)": dict(
        nome="Código", **_pal("Editor (One Dark)"),
        blocos=_blocos("relogio", "hardware", "cpu_gpu", "ram", "fps", "rede", "ssd", "volume"),
        opcoes={"layout": "codigo"}),
}


def modelo(nome: str) -> dict:
    return completar(copy.deepcopy(MODELOS.get(nome, {})))


def completar(cfg: dict) -> dict:
    """Preenche o que faltar com os valores padrão (aceita JSONs antigos/incompletos)."""
    out = copy.deepcopy(PADRAO)
    if not cfg:
        return out
    for k in ("nome", "paleta", "imagem_fundo"):
        if cfg.get(k) is not None:
            out[k] = cfg[k]
    for k in ("fundo", "cores", "opcoes"):
        out[k].update(cfg.get(k) or {})
    o = out["opcoes"]
    # compatibilidade com a v4
    if "cpu_clock" in o:
        o["cpu_extra"] = "clock" if o.pop("cpu_clock") else "nenhum"
    if "gpu_vram" in o:
        o["gpu_extra"] = "vram" if o.pop("gpu_vram") else "nenhum"
    if o.get("fonte_numeros") not in FONTES:
        o["fonte_numeros"] = "JetBrains Mono"
    if cfg.get("blocos"):
        vistos, blocos = [], []
        for b in cfg["blocos"]:
            if b.get("id") in BLOCOS_INFO and b["id"] not in vistos:
                blocos.append({"id": b["id"], "ativo": bool(b.get("ativo", True))})
                vistos.append(b["id"])
        for b in BLOCOS_INFO:
            if b not in vistos:
                blocos.append({"id": b, "ativo": False})
        out["blocos"] = blocos
    return out


def nome_para_pasta(nome: str) -> str:
    base = re.sub(r"[^A-Za-z0-9 _-]+", "", (nome or "").strip()).strip().replace(" ", "_")
    if not base:
        return "Meu_tema"
    return base if base.startswith("Meu_") or base == TEMA_PADRAO else "Meu_" + base


# ----------------------------------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------------------------------
def rgb(hexcor: str):
    return ImageColor.getrgb(hexcor)[:3]


def yc(hexcor: str) -> str:
    r, g, b = rgb(hexcor)
    return f"{r}, {g}, {b}"


def fonte(nome, tam):
    return ImageFont.truetype(str(FONTS_DIR / nome), tam)


ROB_B = "roboto/Roboto-Bold.ttf"
ROB_M = "roboto/Roboto-Medium.ttf"


class Construtor:
    def __init__(self, cfg):
        self.cfg = cfg
        self.f = cfg["fundo"]
        self.c = cfg["cores"]
        self.o = cfg["opcoes"]
        nome_fonte = self.o.get("fonte_numeros", "JetBrains Mono")
        self.MB, self.MM, self.MXB = FONTES[nome_fonte]
        self.esc = ESCALA_FONTE.get(nome_fonte, 1.0)
        self.dy = DESLOC_Y_FONTE.get(nome_fonte, 0)
        self.img = self._fundo()
        self.d = ImageDraw.Draw(self.img)
        self.stats = {}
        self.omitidos = []

    # ---------- fundo e desenho ----------
    def _fundo(self):
        caminho = self.cfg.get("imagem_fundo") or ""
        if caminho and os.path.isfile(caminho):
            img = Image.open(caminho).convert("RGB")
            esc = max(W / img.width, H / img.height)
            img = img.resize((max(W, round(img.width * esc)), max(H, round(img.height * esc))), Image.LANCZOS)
            x0, y0 = (img.width - W) // 2, (img.height - H) // 2
            return img.crop((x0, y0, x0 + W, y0 + H))
        img = Image.new("RGB", (W, H))
        d = ImageDraw.Draw(img)
        a, b = rgb(self.f["topo"]), rgb(self.f["base"])
        for y in range(H):
            t = y / (H - 1)
            d.line([(0, y), (W, y)], fill=tuple(int(p + (q - p) * t) for p, q in zip(a, b)))
        return img

    def cartao(self, x0, y0, x1, y1, cor, titulo=None):
        estilo = self.o.get("estilo_cartao", "cartao")
        r = int(self.o.get("cantos", 8))
        if estilo == "cartao":
            self.d.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=rgb(self.f["cartao"]), outline=rgb(self.f["borda"]))
        elif estilo == "contorno":
            self.d.rounded_rectangle([x0, y0, x1, y1], radius=r, outline=rgb(cor), width=1)
        if self.o.get("faixa_cor", True) and estilo != "contorno":
            m = min(8, max(2, r))
            self.d.rounded_rectangle([x0, y0 + m, x0 + 2, y1 - m], radius=1, fill=rgb(cor))
        if titulo:
            self.d.text((x0 + 9, y0 + 6), titulo, font=fonte(ROB_B, 13), fill=rgb(cor))

    def trilho(self, x, y, w, h):
        self.d.rounded_rectangle([x, y, x + w - 1, y + h - 1], radius=h // 2, fill=rgb(self.f["trilho"]))

    def rotulo(self, xy, txt, tam=11, anchor="la", cor=None):
        self.d.text(xy, txt, font=fonte(ROB_M, tam), fill=rgb(cor or self.f["rotulo"]), anchor=anchor)

    def icone_som(self, x, y, mic=False):
        lab = rgb(self.f["rotulo"])
        if mic:
            self.d.rounded_rectangle([x + 4, y, x + 10, y + 10], radius=3, fill=lab)
            self.d.arc([x + 1, y + 3, x + 13, y + 15], 0, 180, fill=lab, width=2)
            self.d.line([(x + 7, y + 15), (x + 7, y + 18)], fill=lab, width=2)
        else:
            self.d.rectangle([x, y + 5, x + 4, y + 13], fill=lab)
            self.d.polygon([(x + 4, y + 5), (x + 11, y), (x + 11, y + 18), (x + 4, y + 13)], fill=lab)
            self.d.arc([x + 8, y + 2, x + 18, y + 16], -50, 50, fill=lab, width=2)

    # ---------- entradas do theme.yaml ----------
    def texto(self, x, y, cor, tam, peso="b", anchor="la", unit=True, **extra):
        font = {"b": self.MB, "m": self.MM, "xb": self.MXB, "rob": ROB_M}[peso]
        tam_final = round(tam * self.esc) if peso == "xb" else tam
        if peso == "xb":
            y += self.dy
        t = {"SHOW": True, "SHOW_UNIT": unit, "X": x, "Y": y, "ANCHOR": anchor, "FONT": font,
             "FONT_SIZE": tam_final, "FONT_COLOR": yc(cor), "BACKGROUND_IMAGE": "background.png"}
        t.update(extra)
        return t

    @staticmethod
    def barra(x, y, w, h, cor, maximo=100):
        return {"SHOW": True, "X": x, "Y": y, "WIDTH": w, "HEIGHT": h, "MIN_VALUE": 0, "MAX_VALUE": maximo,
                "BAR_COLOR": yc(cor), "BAR_OUTLINE": False, "BACKGROUND_IMAGE": "background.png"}

    @staticmethod
    def grafico(x, y, w, h, cor, maximo=100, autoscale=True, hist=40):
        return {"SHOW": True, "X": x, "Y": y, "WIDTH": w, "HEIGHT": h, "MIN_VALUE": 0, "MAX_VALUE": maximo,
                "HISTORY_SIZE": hist, "AUTOSCALE": autoscale, "LINE_COLOR": yc(cor), "LINE_WIDTH": 2,
                "AXIS": False, "BACKGROUND_IMAGE": "background.png"}

    def radial(self, x, y, raio, cor):
        return {"SHOW": True, "X": x, "Y": y, "RADIUS": raio, "WIDTH": 8, "MIN_VALUE": 0, "MAX_VALUE": 100,
                "ANGLE_START": 135, "ANGLE_END": 45, "ANGLE_STEPS": 1, "ANGLE_SEP": 0, "CLOCKWISE": True,
                "BAR_COLOR": yc(cor), "DRAW_BAR_BACKGROUND": True, "BAR_BACKGROUND_COLOR": yc(self.f["trilho"]),
                "SHOW_TEXT": True, "SHOW_UNIT": True, "FONT": self.MB, "FONT_SIZE": 18,
                "FONT_COLOR": yc(self.f["texto"]), "BACKGROUND_IMAGE": "background.png"}

    def put(self, caminho, valor):
        n = self.stats
        partes = caminho.split(".")
        for p in partes[:-1]:
            n = n.setdefault(p, {})
        n[partes[-1]] = valor

    def custom(self, nome, **itens):
        self.put("CUSTOM.INTERVAL", 1)
        atual = self.stats.setdefault("CUSTOM", {}).setdefault(nome, {})
        atual.update(itens)

    def temperatura(self, nome_sensor, texto):
        """Temperatura de CPU/GPU como sensor próprio, com cor dinâmica opcional."""
        self.custom(nome_sensor, TEXT=texto)
        if self.o.get("temp_dinamica", True):
            self.custom(nome_sensor, COR_DINAMICA={"LIMITES": list(self.o.get("temp_limites", [70, 85])),
                                                   "CORES": [yc(c) for c in self.o.get("temp_cores")]})

    # ---------- alturas (dependem das opções) ----------
    def altura(self, b):
        o = self.o
        return {
            "relogio": 44, "hardware": 58, "cpu_gpu": 120,
            "ram": 56 if (o.get("ram_detalhes") or o.get("ram_modelo")) else 42,
            "fps": 92 if o.get("fps_grande") else 68,
            "energia": 44, "rede": 60, "ssd": 60, "volume": 32,
        }[b]

    # ---------- blocos (layout de cartões) ----------
    def relogio(self, y):
        cor = self.c["relogio"]
        self.d.line([(10, y + 44), (W - 10, y + 44)], fill=rgb(self.f["borda"]))
        self.d.line([(10, y + 44), (90, y + 44)], fill=rgb(cor), width=2)
        self.put("DATE.INTERVAL", 1)
        fmt, tam = self._fmt_hora()
        self.put("DATE.HOUR.TEXT", self.texto(12, y + (32 - tam) // 2, self.f["texto"], tam, FORMAT=fmt))
        fd = self._fmt_data()
        if fd:
            self.put("DATE.DAY.TEXT", self.texto(308, y + 11, self.f["rotulo"], 15, peso="rob", anchor="ra",
                                                 FORMAT=fd, ALIGN="right"))

    def _fmt_hora(self):
        h12, seg = self.o.get("relogio_12h"), self.o.get("segundos")
        fmt = ("hh" if h12 else "HH") + ":mm" + (":ss" if seg else "") + (" a" if h12 else "")
        n = 5 + (3 if seg else 0) + (3 if h12 else 0)
        return fmt, (32 if n <= 5 else (26 if n <= 8 else 21))

    def _fmt_data(self):
        return {"completo": "EEE, dd/MM/yyyy", "curto": "dd/MM", "dia_semana": "EEEE"}.get(
            self.o.get("formato_data", "completo"))

    def hardware(self, y):
        cor = self.c.get("hardware", self.c["ram"])
        self.cartao(6, y, 314, y + 58, cor)
        for i, (rot, sensor, c) in enumerate((("CPU", "NomeCpu", self.c["cpu"]), ("GPU", "NomeGpu", self.c["gpu"]),
                                              ("RAM", "NomeRam", self.c["ram"]))):
            yy = y + 6 + i * 16
            self.d.text((15, yy + 1), rot, font=fonte(ROB_B, 11), fill=rgb(c))
            self.custom(sensor, TEXT=self.texto(48, yy, self.f["texto"], 11, peso="m"))

    def cpu_gpu(self, y):
        mostrar = [k for k in ("cpu", "gpu") if self.o.get("mostrar_" + k, True)]
        if not mostrar:
            return
        caixas = [("cpu", 6, 157), ("gpu", 163, 314)] if len(mostrar) == 2 else [(mostrar[0], 6, 314)]
        barra = self.o.get("estilo_uso") == "barra"
        for k, x0, x1 in caixas:
            cor = self.c[k]
            base = k.upper()
            self.cartao(x0, y, x1, y + 120, cor, base)
            largo = len(caixas) == 1
            if barra:
                bw = (x1 - x0 - 16) if not largo else 150
                self.trilho(x0 + 8, y + 70, bw, 8)
                self.put(f"{base}.PERCENTAGE.GRAPH", self.barra(x0 + 8, y + 70, bw, 8, cor))
                self.put(f"{base}.PERCENTAGE.TEXT", self.texto(x0 + 8, y + 26, self.f["texto"], 32, peso="xb"))
                cx, y_sub = x0 + 8 + bw // 2, y + 90
            else:
                cx = (x0 + x1) // 2 if not largo else 84
                self.put(f"{base}.PERCENTAGE.RADIAL", self.radial(cx, y + 66, 38, cor))
                y_sub = y + 100
            if k == "cpu":
                self.put("CPU.PERCENTAGE.INTERVAL", 1)
            else:
                self.put("GPU.INTERVAL", 1)
            sensor_temp = "TempCpu" if k == "cpu" else "TempGpu"
            if largo:
                self.rotulo((306, y + 34), "TEMPERATURA", 10, "ra")
                self.temperatura(sensor_temp, self.texto(306, y + 44, cor, 34, peso="xb", anchor="ra"))
                xs, ys, anc = 306, y + 92, "ra"
            else:
                self.temperatura(sensor_temp, self.texto(x1 - 8, y + 1, cor, 15, anchor="ra"))
                xs, ys, anc = cx, y_sub, "ma"
            extra = self.o.get("cpu_extra" if k == "cpu" else "gpu_extra", "nenhum")
            t = self.texto(xs, ys, self.f["rotulo"], 11, peso="m", anchor=anc)
            if extra == "clock" and k == "cpu":
                self.put("CPU.FREQUENCY.INTERVAL", 2)
                self.put("CPU.FREQUENCY.TEXT", t)
            elif extra == "vram" and k == "gpu":
                self.custom("Vram", TEXT=t)
            elif extra == "potencia":
                self.custom("PotCpu" if k == "cpu" else "PotGpu", TEXT=t)

    def ram(self, y):
        cor = self.c["ram"]
        h = self.altura("ram")
        self.cartao(6, y, 314, y + h, cor, "RAM")
        detalhes = self.o.get("ram_detalhes", True) or self.o.get("ram_modelo")
        by = y + 24
        self.trilho(14, by, 292, 8)
        self.put("MEMORY.INTERVAL", 2)
        self.put("MEMORY.VIRTUAL.GRAPH", self.barra(14, by, 292, 8, cor))
        self.put("MEMORY.VIRTUAL.PERCENT_TEXT", self.texto(306, y + 1, cor, 15, anchor="ra"))
        if self.o.get("ram_modelo"):
            self.custom("NomeRam", TEXT=self.texto(15, y + 36, self.f["rotulo"], 11, peso="m"))
        elif detalhes:
            self.rotulo((15, y + 38), "Usada")
            self.rotulo((170, y + 38), "Livre")
            self.put("MEMORY.VIRTUAL.USED", self.texto(52, y + 32, self.f["texto"], 13, peso="m"))
            self.put("MEMORY.VIRTUAL.FREE", self.texto(202, y + 32, self.f["texto"], 13, peso="m"))

    def fps(self, y):
        cor = self.c["fps"]
        grande = self.o.get("fps_grande")
        h = self.altura("fps")
        self.cartao(6, y, 314, y + h, cor, "FPS")
        grafico = self.o.get("fps_grafico", True)
        self.custom("Fps", TEXT=self.texto(14, y + (18 if grande else 16), cor, 44 if grande else 28, peso="xb"))
        if grafico:
            gx = 150 if grande else 130
            self.custom("Fps", LINE_GRAPH=self.grafico(gx, y + 8, 306 - gx, h - 14, cor,
                                                       maximo=int(self.o.get("fps_max_grafico", 165))))
        ty = y + h - 18
        tam = 13 if grande else 11
        self.custom("FrameTime", TEXT=self.texto(15, ty, self.f["texto"], tam, peso="m"))
        if self.o.get("fps_media", True):
            if grafico:
                self.custom("FpsMedio", TEXT=self.texto(15 + (82 if grande else 65), ty, self.f["rotulo"], tam, peso="m"))
            else:
                self.rotulo((306, y + 8), "MÉDIA DA SESSÃO", 10, "ra")
                self.custom("FpsMedioGrande", TEXT=self.texto(306, y + 22, cor, 44 if grande else 28, peso="xb", anchor="ra"))

    def energia(self, y):
        cor = self.c.get("energia", self.c["fps"])
        self.cartao(6, y, 314, y + 44, cor, "ENERGIA")
        self.rotulo((210, y + 7), "total", 10, "ra")
        self.custom("PotTotal", TEXT=self.texto(306, y + 3, cor, 15, anchor="ra"))
        self.d.text((15, y + 25), "CPU", font=fonte(ROB_B, 11), fill=rgb(self.c["cpu"]))
        self.custom("PotCpu", TEXT=self.texto(44, y + 23, self.f["texto"], 13, peso="m"))
        self.d.text((165, y + 25), "GPU", font=fonte(ROB_B, 11), fill=rgb(self.c["gpu"]))
        self.custom("PotGpu", TEXT=self.texto(194, y + 23, self.f["texto"], 13, peso="m"))

    def rede(self, y):
        cor, cor_up = self.c["rede"], self.c["upload"]
        self.cartao(6, y, 314, y + 60, cor, "REDE")
        self.d.polygon([(15, y + 26), (25, y + 26), (20, y + 34)], fill=rgb(cor))
        self.d.polygon([(15, y + 50), (25, y + 50), (20, y + 42)], fill=rgb(cor_up))
        self.put("NET.INTERVAL", 1)
        self.put("NET.ETH.DOWNLOAD.TEXT", self.texto(32, y + 18, cor, 14))
        self.put("NET.ETH.UPLOAD.TEXT", self.texto(32, y + 36, cor_up, 14))
        if self.o.get("rede_grafico", True):
            self.put("NET.ETH.DOWNLOAD.LINE_GRAPH", self.grafico(150, y + 6, 156, 48, cor, maximo=1000))

    def ssd(self, y):
        cor = self.c["ssd"]
        h = self.altura("ssd")
        self.cartao(6, y, 314, y + h, cor, "SSD")
        self.rotulo((15, y + 24), "Atividade")
        self.trilho(80, y + 27, 170, 6)
        self.rotulo((15, y + 42), "Disco C:")
        self.trilho(80, y + 45, 170, 6)
        self.custom("SsdTemperatura", TEXT=self.texto(306, y + 1, cor, 15, anchor="ra"))
        if self.o.get("temp_dinamica", True):
            self.custom("SsdTemperatura", COR_DINAMICA={"LIMITES": [55, 70], "CORES": [yc(c) for c in self.o.get("temp_cores")]})
        self.custom("SsdAtividade", GRAPH=self.barra(80, y + 27, 170, 6, cor),
                    TEXT=self.texto(306, y + 19, self.f["texto"], 13, peso="m", anchor="ra"))
        self.put("DISK.INTERVAL", 30)
        self.put("DISK.USED.GRAPH", self.barra(80, y + 45, 170, 6, cor))
        self.put("DISK.USED.PERCENT_TEXT", self.texto(306, y + 37, self.f["texto"], 13, peso="m", anchor="ra"))
        if self.o.get("ssd_livre"):
            self.rotulo((80, y + 6), "Livre no C:")
            self.put("DISK.FREE.TEXT", self.texto(140, y + 2, cor, 13, peso="b"))

    def volume(self, y):
        cor = self.c["volume"]
        self.cartao(6, y, 314, y + 32, cor)
        if self.o.get("volume_mic", True):
            self.icone_som(15, y + 7)
            self.trilho(40, y + 12, 76, 8)
            self.custom("Volume", GRAPH=self.barra(40, y + 12, 76, 8, cor),
                        TEXT=self.texto(156, y + 5, self.f["texto"], 13, anchor="ra"))
            self.d.line([(162, y + 7), (162, y + 25)], fill=rgb(self.f["borda"]))
            cor_mic = self.c.get("microfone", cor)
            self.icone_som(170, y + 6, mic=True)
            self.trilho(190, y + 12, 76, 8)
            self.custom("Microfone", GRAPH=self.barra(190, y + 12, 76, 8, cor_mic),
                        TEXT=self.texto(306, y + 5, self.f["texto"], 13, anchor="ra"))
        else:
            self.icone_som(15, y + 7)
            self.trilho(42, y + 12, 210, 8)
            self.custom("Volume", GRAPH=self.barra(42, y + 12, 210, 8, cor),
                        TEXT=self.texto(306, y + 4, self.f["texto"], 14, anchor="ra"))

    # ---------- montagem (cartões) ----------
    def montar(self):
        if self.o.get("layout") == "codigo":
            return self.montar_codigo()
        ativos = [b["id"] for b in self.cfg["blocos"] if b.get("ativo")]
        if "cpu_gpu" in ativos and not (self.o.get("mostrar_cpu", True) or self.o.get("mostrar_gpu", True)):
            ativos.remove("cpu_gpu")
        topo = 0 if ativos and ativos[0] == "relogio" else 6
        gap = 6
        cabem, total = [], topo
        for b in ativos:  # o que não couber na tela fica de fora (a interface avisa)
            h = self.altura(b)
            extra = gap if cabem else 0
            if total + extra + h <= 476:
                cabem.append(b)
                total += extra + h
            else:
                self.omitidos.append(b)
        sobra = 476 - total
        if sobra > 0 and len(cabem) > 1:
            ext = min(sobra // (len(cabem) - 1), 16)
            gap += ext
            sobra -= ext * (len(cabem) - 1)
        y = topo + (max(0, sobra // 2) if topo else 0)
        for b in cabem:
            getattr(self, b)(y)
            y += self.altura(b) + gap
        return cabem

    # ---------- layout de código ----------
    def montar_codigo(self):
        LH = 15                             # altura da linha
        FS = 11
        fm = "jetbrains-mono/JetBrainsMono-Medium.ttf"
        f = fonte(fm, FS)
        cw = f.getlength("0")
        GUT = 26                            # coluna dos números de linha
        x0 = GUT + 6
        kw, st, nu, pr, cm, tx = (self.c["relogio"], self.c["rede"], self.c["fps"], self.c["cpu"],
                                  self.f["rotulo"], self.f["texto"])
        # fundo do editor: barra de abas e calha
        self.d.rectangle([0, 0, W, 18], fill=rgb(self.f["cartao"]))
        self.d.rectangle([0, 0, 92, 18], fill=rgb(self.f["topo"]))
        self.d.line([(0, 18), (W, 18)], fill=rgb(self.f["borda"]))
        self.d.text((8, 4), "painel.ts", font=fonte(fm, 10), fill=rgb(tx))
        self.d.text((80, 3), "×", font=fonte(fm, 10), fill=rgb(cm))
        self.d.line([(GUT, 18), (GUT, H)], fill=rgb(self.f["borda"]))
        linhas = []  # cada linha: lista de segmentos ("t", texto, cor) | ("v", caminho, n_chars, cor, extras)

        def L(*segs):
            linhas.append(list(segs))

        def t(s, cor=tx):
            return ("t", s, cor)

        def v(caminho, n, cor=nu, **extra):
            return ("v", caminho, n, cor, extra)

        ativos = [b["id"] for b in self.cfg["blocos"] if b.get("ativo")]
        for b in ativos:
            if b == "relogio":
                fmt, _ = self._fmt_hora()
                L(t("// ", cm), v("DATE.HOUR", len(fmt.replace("a", "AM")), cm, FORMAT=fmt),
                  *( [t("  ", cm), v("DATE.DAY", 16, cm, FORMAT=self._fmt_data())] if self._fmt_data() else []))
                L(t("import", kw), t(" { telemetria } "), t("from", kw), t(" \"pc\"", st), t(";"))
                L()
            elif b == "hardware":
                L(t("const", kw), t(" pc = {"))
                L(t("  cpu: ", pr), v("CUSTOM.NomeCpu", 30, st))
                L(t("  gpu: ", pr), v("CUSTOM.NomeGpu", 30, st))
                L(t("  ram: ", pr), v("CUSTOM.NomeRam", 30, st))
                L(t("};"))
            elif b == "cpu_gpu":
                for k in ("cpu", "gpu"):
                    if not self.o.get("mostrar_" + k, True):
                        continue
                    K = k.upper()
                    L(t(f"{k}", pr), t(".uso   = "), v(f"{K}.PERCENTAGE.TEXT", 4), t(";  "), ("bar", f"{K}.PERCENTAGE.GRAPH", 10, self.c[k]))
                    L(t(f"{k}", pr), t(".temp  = "), v("CUSTOM." + ("TempCpu" if k == "cpu" else "TempGpu"), 5), t(";"))
                    extra = self.o.get(f"{k}_extra", "nenhum")
                    if extra == "clock" and k == "cpu":
                        L(t("cpu", pr), t(".clock = "), v("CPU.FREQUENCY.TEXT", 8), t(";"))
                    elif extra == "vram" and k == "gpu":
                        L(t("gpu", pr), t(".vram  = "), v("CUSTOM.VramCurta", 8, nu), t(";"))
                    elif extra == "potencia":
                        L(t(k, pr), t(".watts = "), v("CUSTOM." + ("PotCpu" if k == "cpu" else "PotGpu"), 5), t(";"))
                L()
            elif b == "ram":
                L(t("ram", pr), t(".uso   = "), v("MEMORY.VIRTUAL.PERCENT_TEXT", 4), t(";  "), ("bar", "MEMORY.VIRTUAL.GRAPH", 10, self.c["ram"]))
                L(t("ram", pr), t(".usada = "), v("MEMORY.VIRTUAL.USED", 7), t(";"))
                L(t("ram", pr), t(".livre = "), v("MEMORY.VIRTUAL.FREE", 7), t(";"))
                L()
            elif b == "fps":
                L(t("while", kw), t(" (jogo.rodando) {"))
                L(t("  fps", pr), t(" = "), v("CUSTOM.Fps", 3), t(";  "), t("// média ", cm), v("CUSTOM.FpsMedioGrande", 3, cm))
                L(t("  frametime", pr), t(" = "), v("CUSTOM.FrameTime", 8), t(";"))
                L(t("}"))
                L()
            elif b == "energia":
                L(t("energia", pr), t(" = { cpu: "), v("CUSTOM.PotCpu", 5), t(", gpu: "), v("CUSTOM.PotGpu", 5), t(" };"))
                L()
            elif b == "rede":
                L(t("rede", pr), t(".down = "), v("NET.ETH.DOWNLOAD.TEXT", 10, self.c["rede"]), t(";"))
                L(t("rede", pr), t(".up   = "), v("NET.ETH.UPLOAD.TEXT", 10, self.c["upload"]), t(";"))
                L()
            elif b == "ssd":
                L(t("ssd", pr), t(".temp  = "), v("CUSTOM.SsdTemperatura", 5), t(";"))
                L(t("ssd", pr), t(".ativo = "), v("CUSTOM.SsdAtividade", 4), t(";  "), ("bar", "CUSTOM.SsdAtividade", 10, self.c["ssd"]))
                L(t("ssd", pr), t(".livre = "), v("DISK.FREE.TEXT", 7), t(";  "), t("// C:", cm))
                L()
            elif b == "volume":
                L(t("som", pr), t(".vol = "), v("CUSTOM.Volume", 4), t(";  "), t("mic", pr), t(".vol = "), v("CUSTOM.Microfone", 4), t(";"))
        while linhas and not linhas[-1]:
            linhas.pop()
        y0 = 22
        if len(linhas) * LH > H - y0:      # aperta um pouco as linhas antes de cortar
            LH = max(13, (H - y0) // max(1, len(linhas)))
        maxl = (H - y0) // LH
        if len(linhas) > maxl:
            self.omitidos.append(f"{len(linhas) - maxl} linha(s) de código")
            linhas = linhas[:maxl]
        for i, segs in enumerate(linhas):
            y = y0 + i * LH
            self.d.text((GUT - 4, y), str(i + 1), font=f, fill=rgb(cm), anchor="ra")
            col = 0
            for seg in segs:
                x = x0 + col * cw
                if seg[0] == "t":
                    self.d.text((x, y), seg[1], font=f, fill=rgb(seg[2]))
                    col += len(seg[1])
                elif seg[0] == "bar":
                    _, caminho, n, cor = seg
                    bw = int(n * cw)
                    self.trilho(int(x), y + 4, bw, 6)
                    entrada = self.barra(int(x), y + 4, bw, 6, cor)
                    self._por_caminho(caminho, "GRAPH", entrada)
                    col += n
                else:
                    _, caminho, n, cor, extra = seg
                    entrada = {"SHOW": True, "SHOW_UNIT": True, "X": int(x), "Y": y, "ANCHOR": "la", "FONT": fm,
                               "FONT_SIZE": FS, "FONT_COLOR": yc(cor), "BACKGROUND_IMAGE": "background.png"}
                    entrada.update({k: val for k, val in extra.items() if val})
                    self._por_caminho(caminho, "TEXT", entrada)
                    col += n
        # cursor piscando no fim (só enfeite)
        return ativos

    def _por_caminho(self, caminho, tipo, entrada):
        """Liga um valor do layout de código ao lugar certo do theme.yaml."""
        partes = caminho.split(".")
        if partes[0] == "CUSTOM":
            nome = partes[1]
            self.custom(nome, **{tipo: entrada})
            if nome in ("TempCpu", "TempGpu") and self.o.get("temp_dinamica", True):
                self.custom(nome, COR_DINAMICA={"LIMITES": list(self.o.get("temp_limites", [70, 85])),
                                                "CORES": [yc(c) for c in self.o.get("temp_cores")]})
            return
        if partes[0] == "DATE":
            self.put("DATE.INTERVAL", 1)
            self.put(f"{caminho}.TEXT", entrada)
            return
        intervalos = {"CPU": ("CPU.PERCENTAGE.INTERVAL", 1), "GPU": ("GPU.INTERVAL", 1), "MEMORY": ("MEMORY.INTERVAL", 2),
                      "NET": ("NET.INTERVAL", 1), "DISK": ("DISK.INTERVAL", 30)}
        if partes[0] in intervalos:
            self.put(*intervalos[partes[0]])
        if caminho == "CPU.FREQUENCY.TEXT":
            self.put("CPU.FREQUENCY.INTERVAL", 2)
        if tipo == "GRAPH" and caminho.endswith(".GRAPH"):
            self.put(caminho, entrada)
        else:
            self.put(caminho, entrada)


def gerar(cfg: dict = None, destino: Path = None, com_previa: bool = True):
    """Gera o tema e devolve (pasta, lista do que não coube)."""
    cfg = completar(cfg)
    c = Construtor(cfg)
    c.montar()
    tema = {
        "display": {"DISPLAY_SIZE": '3.5"', "DISPLAY_ORIENTATION": "portrait",
                    "DISPLAY_RGB_LED": yc(cfg["cores"]["relogio"])},
        "static_images": {"BACKGROUND": {"PATH": "background.png", "X": 0, "Y": 0, "WIDTH": W, "HEIGHT": H}},
        "STATS": c.stats,
    }
    destino = Path(destino or (THEMES_DIR / TEMA_PADRAO))
    destino.mkdir(parents=True, exist_ok=True)
    c.img.save(destino / "background.png")
    with open(destino / "theme.yaml", "w", encoding="utf-8") as fh:
        fh.write("# Tema gerado pelo PULSE — System Telemetry (painel/gerador.py). Edite pela janela de configuração.\n")
        yaml.safe_dump(tema, fh, sort_keys=False, allow_unicode=True)
    with open(destino / "painel_tema.json", "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)
    if com_previa:
        renderizar_previa(destino).save(destino / "preview.png")
    return destino, [BLOCOS_INFO.get(b, b) for b in c.omitidos]


# ----------------------------------------------------------------------------------------------
# Temas do usuário (C:\PainelTelemetria\temas\*.json)
# ----------------------------------------------------------------------------------------------
def listar_temas_usuario():
    TEMAS_USUARIO.mkdir(parents=True, exist_ok=True)
    return sorted(p.stem for p in TEMAS_USUARIO.glob("*.json"))


def carregar_tema_usuario(pasta: str) -> dict:
    arq = TEMAS_USUARIO / f"{pasta}.json"
    if arq.is_file():
        return completar(json.loads(arq.read_text(encoding="utf-8")))
    return completar(None)


def salvar_tema_usuario(pasta: str, cfg: dict, gerar_agora=True):
    TEMAS_USUARIO.mkdir(parents=True, exist_ok=True)
    cfg = completar(cfg)
    (TEMAS_USUARIO / f"{pasta}.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    if gerar_agora:
        gerar(cfg, THEMES_DIR / pasta)
    return cfg


def migrar_antigo():
    """v3 guardava um único tema em C:\\PainelTelemetria\\painel.json."""
    antigo = DESTINO / "painel.json"
    novo = TEMAS_USUARIO / f"{TEMA_PADRAO}.json"
    if antigo.is_file() and not novo.exists():
        TEMAS_USUARIO.mkdir(parents=True, exist_ok=True)
        cfg = completar(json.loads(antigo.read_text(encoding="utf-8")))
        cfg["nome"] = "Meu painel"
        novo.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def criar_modelos_iniciais():
    """Na primeira vez, cria o padrão e os modelos Trabalho, Jogos e Código como temas do usuário."""
    existentes = listar_temas_usuario()
    if not existentes:
        salvar_tema_usuario(TEMA_PADRAO, None, gerar_agora=False)
    pastas = {"Trabalho / Produtividade": "Meu_Trabalho", "Jogos": "Meu_Jogos", "Código (programação)": "Meu_Codigo"}
    marca = TEMAS_USUARIO / ".modelos_v5"
    if not marca.exists():
        for nome, pasta in pastas.items():
            if pasta not in existentes:
                salvar_tema_usuario(pasta, modelo(nome), gerar_agora=False)
        marca.write_text("ok", encoding="utf-8")


def gerar_todos():
    migrar_antigo()
    criar_modelos_iniciais()
    pastas = listar_temas_usuario()
    for p in pastas:
        gerar(carregar_tema_usuario(p), THEMES_DIR / p)
    return pastas


# ----------------------------------------------------------------------------------------------
# Prévia: desenha o tema com valores de exemplo usando as rotinas de desenho do próprio programa
# ----------------------------------------------------------------------------------------------
AMOSTRA_LINHA = [30, 34, 31, 40, 52, 47, 60, 58, 72, 66, 80, 77, 90, 84, 95, 88, 92, 99, 94, 101,
                 97, 104, 100, 110, 106, 112, 108, 115, 111, 118, 114, 120, 116, 121, 117, 122, 119, 124, 120, 123]

VALORES = {
    "CPU.PERCENTAGE": 37, "GPU.PERCENTAGE": 82,
    "CPU.FREQUENCY.TEXT": "4.52 GHz",
    "MEMORY.VIRTUAL.PERCENT_TEXT": " 46%", "MEMORY.VIRTUAL.GRAPH": 46,
    "MEMORY.VIRTUAL.USED": " 7340 M", "MEMORY.VIRTUAL.FREE": " 8620 M",
    "NET.ETH.DOWNLOAD.TEXT": "  12.4 M/s", "NET.ETH.UPLOAD.TEXT": " 640.0 K/s",
    "DISK.USED.GRAPH": 63, "DISK.USED.PERCENT_TEXT": " 63%", "DISK.FREE.TEXT": "  312 G",
    "CUSTOM.Fps": (120, "120"), "CUSTOM.FrameTime": (8.3, "  8.3 ms"),
    "CUSTOM.FpsMedio": (112, "méd 112"), "CUSTOM.FpsMedioGrande": (112, "112"),
    "CUSTOM.Vram": (41, "VRAM 3.3/8 GB"), "CUSTOM.VramCurta": (41, "3.3/8 GB"),
    "CUSTOM.TempCpu": (54, " 54°C"), "CUSTOM.TempGpu": (78, " 78°C"),
    "CUSTOM.PotCpu": (45, " 45 W"), "CUSTOM.PotGpu": (162, "162 W"), "CUSTOM.PotTotal": (207, "207 W"),
    "CUSTOM.NomeCpu": (0, "AMD Ryzen 5 8500G"), "CUSTOM.NomeGpu": (0, "AMD Radeon RX 6650 XT"),
    "CUSTOM.NomeRam": (0, "16 GB DDR5 5600 MHz (2x8)"),
    "CUSTOM.SsdTemperatura": (41, " 41°C"), "CUSTOM.SsdAtividade": (12, " 12%"),
    "CUSTOM.Volume": (65, " 65%"), "CUSTOM.Microfone": (80, " 80%"),
}


def _lcd_previa():
    if str(APP_DIR) not in sys.path:
        sys.path.insert(0, str(APP_DIR))
    from library.lcd.lcd_comm import LcdComm

    class LcdPrevia(LcdComm):
        def __init__(self):
            LcdComm.__init__(self, "AUTO", W, H, None)
            self.tela = Image.new("RGB", (W, H), (0, 0, 0))

        def auto_detect_com_port(self): return None
        def InitializeComm(self): pass
        def Reset(self): pass
        def Clear(self): pass
        def ScreenOff(self): pass
        def ScreenOn(self): pass
        def SetBrightness(self, level=25): pass
        def SetBackplateLedColor(self, led_color=(255, 255, 255)): pass
        def SetOrientation(self, orientation=None): pass

        def DisplayPILImage(self, image, x=0, y=0, image_width=0, image_height=0):
            if image_width and image_height:
                image = image.crop((0, 0, image_width, image_height))
            self.tela.paste(image.convert("RGB"), (x, y))

    return LcdPrevia()


def _get(d, caminho):
    for p in caminho.split("."):
        if not isinstance(d, dict) or p not in d:
            return None
        d = d[p]
    return d


def renderizar_previa(tema_dir: Path) -> Image.Image:
    import datetime
    tema_dir = Path(tema_dir)
    with open(tema_dir / "theme.yaml", encoding="utf-8") as fh:
        tema = yaml.safe_load(fh)
    lcd = _lcd_previa()
    fundo = str(tema_dir / "background.png")
    fonts = str(FONTS_DIR) + "/"
    lcd.tela.paste(Image.open(fundo).convert("RGB"))

    def txt(t, s):
        lcd.DisplayText(text=str(s), x=t["X"], y=t["Y"], font=fonts + t["FONT"], font_size=t["FONT_SIZE"],
                        font_color=t["FONT_COLOR"], background_image=fundo, anchor=t.get("ANCHOR", "lt"),
                        align=t.get("ALIGN", "left"))

    def bar(t, v):
        lcd.DisplayProgressBar(x=t["X"], y=t["Y"], width=t["WIDTH"], height=t["HEIGHT"], value=int(v),
                               min_value=t["MIN_VALUE"], max_value=t["MAX_VALUE"], bar_color=t["BAR_COLOR"],
                               bar_outline=False, background_image=fundo)

    def rad(t, v, s):
        lcd.DisplayRadialProgressBar(
            xc=t["X"], yc=t["Y"], radius=t["RADIUS"], bar_width=t["WIDTH"], min_value=0, max_value=100,
            angle_start=t["ANGLE_START"], angle_end=t["ANGLE_END"], angle_steps=1, angle_sep=0, clockwise=True,
            value=v, bar_color=t["BAR_COLOR"], text=s, font=fonts + t["FONT"], font_size=t["FONT_SIZE"],
            font_color=t["FONT_COLOR"], background_image=fundo, bar_background_color=t["BAR_BACKGROUND_COLOR"],
            draw_bar_background=True)

    def lin(t, vals):
        lcd.DisplayLineGraph(x=t["X"], y=t["Y"], width=t["WIDTH"], height=t["HEIGHT"], values=vals,
                             min_value=t["MIN_VALUE"], max_value=t["MAX_VALUE"], autoscale=t["AUTOSCALE"],
                             line_color=t["LINE_COLOR"], line_width=t["LINE_WIDTH"], graph_axis=False,
                             background_image=fundo)

    s = tema.get("STATS", {})
    g = lambda caminho: _get(s, caminho)
    agora = datetime.datetime(2026, 11, 11, 14, 32, 7)
    if g("DATE.HOUR.TEXT"):
        fmt = g("DATE.HOUR.TEXT").get("FORMAT", "HH:mm")
        py = fmt.replace("HH", "%H").replace("hh", "%I").replace("mm", "%M").replace("ss", "%S").replace(" a", " %p")
        txt(g("DATE.HOUR.TEXT"), agora.strftime(py))
    if g("DATE.DAY.TEXT"):
        fmt = g("DATE.DAY.TEXT").get("FORMAT", "")
        txt(g("DATE.DAY.TEXT"), {"EEE, dd/MM/yyyy": "qua., 11/11/2026", "dd/MM": "11/11",
                                 "EEEE": "quarta-feira"}.get(fmt, "11/11/2026"))
    for k in ("CPU", "GPU"):
        v = VALORES[f"{k}.PERCENTAGE"]
        if g(f"{k}.PERCENTAGE.RADIAL"):
            rad(g(f"{k}.PERCENTAGE.RADIAL"), v, f"{v:>3}%")
        if g(f"{k}.PERCENTAGE.GRAPH"):
            bar(g(f"{k}.PERCENTAGE.GRAPH"), v)
        if g(f"{k}.PERCENTAGE.TEXT"):
            txt(g(f"{k}.PERCENTAGE.TEXT"), f"{v:>3}%")
    for caminho in ("MEMORY.VIRTUAL.GRAPH", "DISK.USED.GRAPH"):
        if g(caminho):
            bar(g(caminho), VALORES[caminho])
    for caminho in ("MEMORY.VIRTUAL.PERCENT_TEXT", "MEMORY.VIRTUAL.USED", "MEMORY.VIRTUAL.FREE", "DISK.FREE.TEXT",
                    "NET.ETH.DOWNLOAD.TEXT", "NET.ETH.UPLOAD.TEXT", "DISK.USED.PERCENT_TEXT", "CPU.FREQUENCY.TEXT"):
        if g(caminho):
            txt(g(caminho), VALORES[caminho])
    if g("NET.ETH.DOWNLOAD.LINE_GRAPH"):
        lin(g("NET.ETH.DOWNLOAD.LINE_GRAPH"), [v * 9 for v in AMOSTRA_LINHA[::-1]])
    for nome, dados in (s.get("CUSTOM") or {}).items():
        if nome == "INTERVAL" or not isinstance(dados, dict):
            continue
        num, texto = VALORES.get("CUSTOM." + nome, (0, "--"))
        regra = dados.get("COR_DINAMICA")
        if regra:  # simula a cor dinâmica na prévia
            idx = min(sum(1 for lim in regra["LIMITES"] if num >= lim), len(regra["CORES"]) - 1)
            for parte, chave in (("TEXT", "FONT_COLOR"), ("GRAPH", "BAR_COLOR")):
                if parte in dados:
                    dados[parte][chave] = regra["CORES"][idx]
        if "TEXT" in dados:
            txt(dados["TEXT"], texto)
        if "GRAPH" in dados:
            bar(dados["GRAPH"], num)
        if "LINE_GRAPH" in dados:
            lin(dados["LINE_GRAPH"], AMOSTRA_LINHA)
    return lcd.tela


if __name__ == "__main__":
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        arq = Path(sys.argv[1])
        cfg = json.loads(arq.read_text(encoding="utf-8"))
        print("Tema gerado em", gerar(cfg, THEMES_DIR / arq.stem)[0])
    else:
        print("Temas gerados:", ", ".join(gerar_todos()))
