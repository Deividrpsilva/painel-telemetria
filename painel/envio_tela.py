# PULSE - envio das imagens para a tela (roda dentro do main.py)
#
# Três problemas da biblioteca turing-smart-screen-python que apareciam no FPS e na troca de tema:
#
# 1. Pedidos misturados. Na tela rev A (e B), cada desenho vai para a fila em duas partes: o comando
#    "desenhar retângulo" e, depois, os dados da imagem, cada parte com a sua trava. Como cada sensor
#    desenha da sua própria thread, outra thread podia enfiar o comando dela no meio: a tela recebia o
#    comando de um e os dados de outro e mostrava pedaços de números ou lixo. Agora o comando e os dados
#    entram juntos (a trava da fila vira reentrante e envolve o desenho inteiro).
#
# 2. Sobras de texto. A caixa de um texto é calculada pelo que tem tinta: "--" é mais baixo que "144",
#    então ao trocar o FPS de "144" para " --" a parte de cima dos números antigos ficava na tela
#    ("números pela metade"). Agora o texto é desenhado na caixa que cobre o texto novo E o anterior
#    daquele lugar.
#
# 3. Envio lento. A tela rev A recebe uns 250 KB/s: o fundo inteiro (320x480) leva 1,2 s. O PULSE agora
#    guarda uma cópia do que está na tela e manda só os retângulos que mudaram: um valor que não mudou
#    não é reenviado, um número que mudou um dígito manda só o dígito, e na troca de tema vai só a
#    parte do fundo que é diferente. Qualquer comando que mude a tela de outro jeito (limpar, girar,
#    reset) apaga a cópia, e o próximo desenho vai inteiro.
import threading
import time

import numpy as np

from library.log import logger

JUNTAR_LINHAS = 4      # linhas iguais entre dois trechos que mudaram: até isto, manda tudo junto
JUNTAR_COLUNAS = 24    # o mesmo para colunas
RELATORIO = 300        # s entre os resumos do envio no log

_caixas = {}           # lugar do texto -> caixa desenhada da última vez
_estat = {"desenhos": 0, "pulados": 0, "enviado": 0, "evitado": 0, "desde": time.monotonic()}
_instalado = False


# ------------------------------------------------------------------ utilidades
def _rgb565(image):
    """Mesma conversão da biblioteca (image_to_RGB565), sem a ordem dos bytes: matriz altura x largura."""
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGB")
    a = np.asarray(image)
    r = a[:, :, 0].astype(np.uint16) >> 3
    g = a[:, :, 1].astype(np.uint16) >> 2
    b = a[:, :, 2].astype(np.uint16) >> 3
    return (r << 11) | (g << 5) | b


def _faixas(indices, juntar):
    """[3,4,5,9,30,31] -> [(3,9),(30,31)] com juntar=4 (junta buracos de até 'juntar')."""
    faixas = []
    ini = fim = int(indices[0])
    for i in indices[1:]:
        i = int(i)
        if i - fim - 1 <= juntar:
            fim = i
        else:
            faixas.append((ini, fim))
            ini = fim = i
    faixas.append((ini, fim))
    return faixas


def retangulos(mudou):
    """Retângulos (x0, y0, x1, y1, inclusivos) que cobrem os pixels marcados em 'mudou'."""
    saida = []
    linhas = np.flatnonzero(mudou.any(axis=1))
    if not len(linhas):
        return saida
    for y0, y1 in _faixas(linhas, JUNTAR_LINHAS):
        cols = np.flatnonzero(mudou[y0:y1 + 1].any(axis=0))
        for x0, x1 in _faixas(cols, JUNTAR_COLUNAS):
            sub = mudou[y0:y1 + 1, x0:x1 + 1]
            ls = np.flatnonzero(sub.any(axis=1))          # aperta as linhas de cada pedaço
            saida.append((x0, y0 + int(ls[0]), x1, y0 + int(ls[-1])))
    return saida


def esquecer_textos():
    """Chamado na troca de tema: as caixas de texto do tema anterior não valem mais."""
    _caixas.clear()


def esquecer_tela(lcd):
    """A tela mudou por outro caminho (limpar, girar, reset, reconexão): o próximo desenho vai inteiro."""
    lcd._pulse_sombra = None


def estatisticas():
    return dict(_estat)


def _relatorio():
    agora = time.monotonic()
    if agora - _estat["desde"] < RELATORIO:
        return
    total = _estat["enviado"] + _estat["evitado"]
    if total:
        logger.info("Envio para a tela nos últimos %d min: %d desenhos (%d sem mudança), %.0f KB enviados, "
                    "%.0f KB evitados (%d%%)", round((agora - _estat["desde"]) / 60), _estat["desenhos"],
                    _estat["pulados"], _estat["enviado"] / 1024, _estat["evitado"] / 1024,
                    round(100 * _estat["evitado"] / total))
    _estat.update(desenhos=0, pulados=0, enviado=0, evitado=0, desde=agora)


# ------------------------------------------------------------------ 1 e 3: desenho atômico e só o que mudou
def _desenho_atomico(original):
    def DisplayPILImage(self, image, x=0, y=0, image_width=0, image_height=0):
        with self.update_queue_mutex:
            return original(self, image, x, y, image_width, image_height)
    DisplayPILImage.pulse_original = original
    return DisplayPILImage


def _desenho_diferencial(original):
    def DisplayPILImage(self, image, x=0, y=0, image_width=0, image_height=0):
        with self.update_queue_mutex:
            largura, altura = self.get_width(), self.get_height()
            w = image_width or image.size[0]
            h = image_height or image.size[1]
            w, h = min(w, largura - x), min(h, altura - y)       # o mesmo corte da biblioteca
            if x < 0 or y < 0 or w <= 0 or h <= 0:
                return original(self, image, x, y, image_width, image_height)   # deixa a biblioteca reclamar
            if (w, h) != image.size:
                image = image.crop((0, 0, w, h))
            novo = _rgb565(image)
            sombra = getattr(self, "_pulse_sombra", None)
            if sombra is None or sombra.shape != (altura, largura):
                sombra = None
            _estat["desenhos"] += 1
            if sombra is None:
                original(self, image, x, y)
                sombra = np.zeros((altura, largura), dtype=np.uint16)
                mudou_bytes = w * h * 2
                retas = None
            else:
                mudou = novo != sombra[y:y + h, x:x + w]
                retas = retangulos(mudou)
                if not retas:
                    _estat["pulados"] += 1
                    _estat["evitado"] += w * h * 2
                    _relatorio()
                    return
                mudou_bytes = 0
                for x0, y0, x1, y1 in retas:
                    original(self, image.crop((x0, y0, x1 + 1, y1 + 1)), x + x0, y + y0)
                    mudou_bytes += (x1 - x0 + 1) * (y1 - y0 + 1) * 2
            sombra[y:y + h, x:x + w] = novo
            self._pulse_sombra = sombra
            _estat["enviado"] += mudou_bytes
            _estat["evitado"] += w * h * 2 - mudou_bytes
            _relatorio()
    DisplayPILImage.pulse_original = original
    return DisplayPILImage


def _apaga_sombra(original, com_trava):
    """com_trava: comandos rápidos que vão para a fila (limpar, girar). Sem trava: abrir a porta e reset,
    que podem esperar a tela por muito tempo e não podem segurar os desenhos das outras threads."""
    def f(self, *a, **kw):
        if com_trava:
            with self.update_queue_mutex:
                esquecer_tela(self)
                return original(self, *a, **kw)
        esquecer_tela(self)
        try:
            return original(self, *a, **kw)
        finally:
            esquecer_tela(self)
    f.pulse_original = original
    return f


# ------------------------------------------------------------------ 2: texto sem sobras
def _texto_sem_sobra(lcd_comm):
    original = lcd_comm.LcdComm.DisplayText
    parse_color = lcd_comm.parse_color
    import math
    from PIL import Image, ImageDraw

    def DisplayText(self, text, x=0, y=0, width=0, height=0,
                    font="./res/fonts/roboto-mono/RobotoMono-Regular.ttf", font_size=20, font_color=(0, 0, 0),
                    background_color=(255, 255, 255), background_image=None, align='left', anchor='la'):
        if (width and height) or not text:
            # caixa fixa (já limpa a área inteira) ou texto vazio (a biblioteca reclama): como sempre
            return original(self, text, x, y, width, height, font, font_size, font_color, background_color,
                            background_image, align, anchor)
        if width > 0 and height == 0:
            return original(self, text, x, y, width, height, font, font_size, font_color, background_color,
                            background_image, align, anchor)
        font_color = parse_color(font_color)
        background_color = parse_color(background_color)
        assert x <= self.get_width(), 'Text "' + text + '" X coordinate ' + str(x) + ' must be <= display width'
        assert y <= self.get_height(), 'Text "' + text + '" Y coordinate ' + str(y) + ' must be <= display height'
        assert font_size > 0, "Font size must be > 0"

        if background_image is None:
            text_image = Image.new('RGB', (self.get_width(), self.get_height()), background_color)
        else:
            text_image = self.open_image(background_image)
        ttfont = self.open_font(font, font_size)
        d = ImageDraw.Draw(text_image)
        left, top, right, bottom = d.textbbox((x, y), text, font=ttfont, align=align, anchor=anchor)
        left, top = math.floor(left), math.floor(top)
        right, bottom = math.ceil(right), math.ceil(bottom)

        chave = (x, y, anchor, align, font, font_size, background_image)
        antes = _caixas.get(chave)
        _caixas[chave] = (left, top, right, bottom)
        if antes:   # cobre também o texto anterior deste lugar, para não sobrar pedaço dele
            left, top = min(left, antes[0]), min(top, antes[1])
            right, bottom = max(right, antes[2]), max(bottom, antes[3])

        d.text((x, y), text, font=ttfont, fill=font_color, align=align, anchor=anchor)
        left, top = max(left, 0), max(top, 0)
        right, bottom = min(right, self.get_width()), min(bottom, self.get_height())
        if right <= left or bottom <= top:
            return
        self.DisplayPILImage(text_image.crop(box=(left, top, right, bottom)), left, top)

    DisplayText.pulse_original = original
    return DisplayText


# ------------------------------------------------------------------ instalação
def instalar():
    """Troca as funções de desenho da biblioteca. Chamado pelo main.py antes de abrir a tela."""
    global _instalado
    if _instalado:
        return
    import library.lcd.lcd_comm as lcd_comm

    init_original = lcd_comm.LcdComm.__init__

    def __init__(self, *a, **kw):
        init_original(self, *a, **kw)
        self.update_queue_mutex = threading.RLock()   # reentrante: o desenho inteiro segura a trava
        self._pulse_sombra = None

    lcd_comm.LcdComm.__init__ = __init__
    lcd_comm.LcdComm.DisplayText = _texto_sem_sobra(lcd_comm)

    diferencial, atomico = [], []
    for modulo, classe, so_mudanca in (
            ("library.lcd.lcd_comm_rev_a", "LcdCommRevA", True),
            ("library.lcd.lcd_comm_rev_b", "LcdCommRevB", True),
            ("library.lcd.lcd_simulated", "LcdSimulated", True),
            ("library.lcd.lcd_comm_rev_c", "LcdCommRevC", False),
            ("library.lcd.lcd_comm_rev_d", "LcdCommRevD", False),
            ("library.lcd.lcd_comm_weact_a", "LcdCommWeActA", False),
            ("library.lcd.lcd_comm_weact_b", "LcdCommWeActB", False)):
        try:
            mod = __import__(modulo, fromlist=[classe])
            cls = getattr(mod, classe)
        except Exception as e:
            logger.debug("Envio: %s indisponível (%s)" % (classe, e))
            continue
        metodo = cls.__dict__.get("DisplayPILImage")
        if metodo is None or hasattr(metodo, "pulse_original"):
            continue
        if so_mudanca:
            cls.DisplayPILImage = _desenho_diferencial(metodo)
            for nome, com_trava in (("Clear", True), ("SetOrientation", True), ("Reset", False),
                                    ("InitializeComm", False), ("openSerial", False)):
                m = cls.__dict__.get(nome) or getattr(cls, nome, None)
                if m is not None and not hasattr(m, "pulse_original"):
                    setattr(cls, nome, _apaga_sombra(m, com_trava))
            diferencial.append(classe)
        else:
            cls.DisplayPILImage = _desenho_atomico(metodo)
            atomico.append(classe)
    _instalado = True
    logger.debug("Envio para a tela: só o que mudou em %s; desenho atômico em %s" %
                 (", ".join(diferencial), ", ".join(atomico)))
