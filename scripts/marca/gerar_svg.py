"""Gera os SVGs da marca PULSE (marca/ e camadas da splash), com o texto convertido em curvas.

Uso:  SAIRA_TTF=caminho/Saira[wdth,wght].ttf python scripts/marca/gerar_svg.py pasta_saida
Depois converta para PNG com scripts/marca/render.js (Playwright/Chromium), por exemplo:
  node scripts/marca/render.js pasta_saida/pulse_logo.svg marca/pulse_logo.png 1200 560 2
Precisa de: pip install fonttools
"""
import math
import os
import sys
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

FONTE = os.environ.get("SAIRA_TTF", "Saira[wdth,wght].ttf")   # Saira (OFL), do Google Fonts
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "out")
OUT.mkdir(parents=True, exist_ok=True)

CIANO = "#00E5FF"
CIANO2 = "#00D1E8"
BRANCO = "#F5F7FA"
GRAFITE = "#101722"
AZUL = "#162234"

_cache = {}


def fonte(wdth, wght):
    k = (wdth, wght)
    if k not in _cache:
        f = TTFont(FONTE)
        _cache[k] = instancer.instantiateVariableFont(f, {"wdth": wdth, "wght": wght})
    return _cache[k]


def texto(txt, wdth, wght, cap, tracking=0.0, x0=0.0, base=0.0):
    """Path SVG do texto com a base em (x0, base) e altura das maiúsculas = cap px. Devolve (d, largura)."""
    f = fonte(wdth, wght)
    gs = f.getGlyphSet()
    cmap = f.getBestCmap()
    esc = cap / f["OS/2"].sCapHeight
    hmtx = f["hmtx"]
    pen = SVGPathPen(gs, ntos=lambda v: ("%.2f" % v).rstrip("0").rstrip("."))
    x = 0.0
    nomes = [cmap[ord(c)] for c in txt]
    for i, nome in enumerate(nomes):
        if txt[i] != " ":
            tp = TransformPen(pen, (esc, 0, 0, -esc, x0 + x, base))
            gs[nome].draw(tp)
        x += hmtx[nome][0] * esc
        if i < len(nomes) - 1:
            x += tracking * cap / 0.688 if tracking else 0
    # largura visual: tira o espaço lateral do último glifo
    ult = nomes[-1]
    glyf = f["glyf"][ult] if "glyf" in f else None
    if glyf is not None and hasattr(glyf, "xMax"):
        x -= (hmtx[ult][0] - glyf.xMax) * esc
    lsb = hmtx[nomes[0]][1] * esc
    return pen.getCommands(), x, lsb


def medir(txt, wdth, wght, cap, tracking=0.0):
    _, w, lsb = texto(txt, wdth, wght, cap, tracking)
    return w - lsb, lsb


def arco(cx, cy, r, a1, a2):
    """Arco de a1 a a2 graus (sentido anti-horário visual, 0 = direita)."""
    p1 = (cx + r * math.cos(math.radians(a1)), cy - r * math.sin(math.radians(a1)))
    p2 = (cx + r * math.cos(math.radians(a2)), cy - r * math.sin(math.radians(a2)))
    grande = 1 if (a2 - a1) % 360 > 180 else 0
    return f"M{p1[0]:.1f} {p1[1]:.1f} A{r} {r} 0 {grande} 0 {p2[0]:.1f} {p2[1]:.1f}", p1, p2


# ------------------------------------------------------------------ logo horizontal
W, H = 1200, 560
DX = 34                        # desloca tudo para centralizar
CX, CY, R = 600 + DX, 280, 228
LINHA_Y = 300
CAP = 116
TX = 404 + DX                       # início do PULSE
w_pulse, lsb = medir("PULSE", 125, 600, CAP, 0.035)
d_pulse, _, _ = texto("PULSE", 125, 600, CAP, 0.035, x0=TX - lsb, base=LINHA_Y - 18)
FIM = TX + w_pulse + 14        # ponto final da linha
CAP_SUB = 21
w_sub, lsb_sub = medir("SYSTEM TELEMETRY", 100, 400, CAP_SUB, 0.42)
sub_x = TX + (w_pulse - w_sub) / 2
d_sub, _, _ = texto("SYSTEM TELEMETRY", 100, 400, CAP_SUB, 0.42, x0=sub_x - lsb_sub, base=LINHA_Y + 22 + CAP_SUB)

ecg_pts = [(x + DX if x != FIM else x, y) for x, y in [(96, LINHA_Y), (214, LINHA_Y), (232, LINHA_Y - 16), (250, LINHA_Y), (268, LINHA_Y),
           (282, LINHA_Y + 14), (308, LINHA_Y - 176), (336, LINHA_Y + 96), (356, LINHA_Y - 22),
           (370, LINHA_Y), (FIM, LINHA_Y)]]
d_ecg = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in ecg_pts)
d_arco_cima, ac1, ac2 = arco(CX, CY, R, 32, 166)
d_arco_baixo, ab1, ab2 = arco(CX, CY, R, 204, 322)

DEFS_GRAD = f"""
    <linearGradient id="gEcg" x1="{96 + DX}" y1="0" x2="{FIM:.0f}" y2="0" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="{CIANO}" stop-opacity="0"/>
      <stop offset="0.12" stop-color="{CIANO}" stop-opacity="1"/>
      <stop offset="1" stop-color="{CIANO}" stop-opacity="1"/>
    </linearGradient>
    <linearGradient id="gCima" x1="{ac2[0]:.0f}" y1="0" x2="{ac1[0]:.0f}" y2="0" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="{CIANO2}" stop-opacity="0.15"/>
      <stop offset="0.55" stop-color="{CIANO2}" stop-opacity="0.85"/>
      <stop offset="1" stop-color="{CIANO2}" stop-opacity="1"/>
    </linearGradient>
    <linearGradient id="gBaixo" x1="{ab1[0]:.0f}" y1="0" x2="{ab2[0]:.0f}" y2="0" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="{CIANO2}" stop-opacity="0.35"/>
      <stop offset="0.45" stop-color="{CIANO2}" stop-opacity="1"/>
      <stop offset="1" stop-color="{CIANO2}" stop-opacity="0.2"/>
    </linearGradient>"""


def linha_svg(com_ponto=True):
    s = (f'<path d="{d_arco_cima}" fill="none" stroke="url(#gCima)" stroke-width="5" stroke-linecap="round"/>\n'
         f'    <path d="{d_arco_baixo}" fill="none" stroke="url(#gBaixo)" stroke-width="5" stroke-linecap="round"/>\n'
         f'    <path d="{d_ecg}" fill="none" stroke="url(#gEcg)" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>\n')
    if com_ponto:
        s += f'    <circle cx="{FIM:.1f}" cy="{LINHA_Y}" r="9" fill="{CIANO}"/>\n'
    return s


TEXTO = (f'<path d="{d_pulse}" fill="{BRANCO}"/>\n'
         f'    <path d="{d_sub}" fill="{BRANCO}" fill-opacity="0.88"/>\n')


def svg(corpo, w=W, h=H, defs="", fundo=None, titulo="PULSE — System Telemetry"):
    bg = f'<rect width="{w}" height="{h}" fill="{fundo}"/>\n  ' if fundo else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">\n'
            f'  <title>{titulo}</title>\n  <defs>{defs}\n  </defs>\n  {bg}{corpo}</svg>\n')


BRILHO = """
    <filter id="brilho" x="-20%" y="-60%" width="140%" height="220%">
      <feGaussianBlur in="SourceGraphic" stdDeviation="7" result="b"/>
      <feComponentTransfer in="b" result="b2"><feFuncA type="linear" slope="0.75"/></feComponentTransfer>
      <feMerge><feMergeNode in="b2"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>"""

logo = f'<g filter="url(#brilho)">\n    {linha_svg()}  </g>\n  <g>\n    {TEXTO}  </g>\n'
(OUT / "pulse_logo.svg").write_text(svg(logo, defs=DEFS_GRAD + BRILHO))
(OUT / "pulse_logo_fundo_preto.svg").write_text(svg(logo, defs=DEFS_GRAD + BRILHO, fundo="#000000"))
# camadas da splash (cada uma sozinha, fundo transparente)
(OUT / "camada_texto.svg").write_text(svg(f"<g>\n    {TEXTO}  </g>\n"))
(OUT / "camada_linha.svg").write_text(svg(f"<g>\n    {linha_svg()}  </g>\n", defs=DEFS_GRAD))
BLUR = """
    <filter id="so_brilho" x="-20%" y="-60%" width="140%" height="220%">
      <feGaussianBlur in="SourceGraphic" stdDeviation="9"/>
    </filter>"""
(OUT / "camada_brilho.svg").write_text(
    svg(f'<g filter="url(#so_brilho)" stroke-width="2">\n    {linha_svg()}  </g>\n', defs=DEFS_GRAD + BLUR))


# ------------------------------------------------------------------ símbolo (ícone)
ECG_COMPLETO = [(30, 138), (70, 138), (82, 124), (94, 138), (104, 138), (112, 150), (130, 50),
                (152, 204), (168, 118), (180, 138), (226, 138)]
ECG_SIMPLES = [(34, 140), (88, 140), (114, 48), (146, 206), (170, 116), (184, 140), (222, 140)]
ECG_MINI = [(42, 138), (84, 138), (110, 54), (146, 204), (170, 138), (214, 138)]
# (pontos, traço, borda, raio, desfoque, opacidade da borda) em unidades de 256
VARIANTES = {
    "completo": (ECG_COMPLETO, 15, 5, 56, 7, 0.55),   # 40 px ou mais
    "simples": (ECG_SIMPLES, 24, 10, 56, 4, 0.9),     # 32 px
    "mini": (ECG_MINI, 30, 16, 52, 0, 1.0),           # 16 a 24 px e bandeja
}


def simbolo(variante="completo", fundo=True, tam=256):
    pts, traco, borda, raio, desf, op = VARIANTES[variante]
    m = tam / 256
    d = "M" + " L".join(f"{x * m:.2f} {y * m:.2f}" for x, y in pts)
    defs = f"""
    <linearGradient id="gFundo" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{AZUL}"/><stop offset="1" stop-color="#0B111A"/>
    </linearGradient>"""
    filtro = ""
    if desf:
        defs += f"""
    <filter id="bri" x="-30%" y="-30%" width="160%" height="160%">
      <feGaussianBlur in="SourceGraphic" stdDeviation="{desf * m:.2f}" result="b"/>
      <feComponentTransfer in="b" result="b2"><feFuncA type="linear" slope="0.8"/></feComponentTransfer>
      <feMerge><feMergeNode in="b2"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>"""
        filtro = ' filter="url(#bri)"'
    corpo = ""
    if fundo:
        inset = borda * m / 2 + 2 * m
        corpo += (f'<rect x="{inset:.2f}" y="{inset:.2f}" width="{tam - 2 * inset:.2f}" height="{tam - 2 * inset:.2f}" '
                  f'rx="{raio * m:.2f}" fill="url(#gFundo)" stroke="{CIANO2}" stroke-opacity="{op}" '
                  f'stroke-width="{borda * m:.2f}"/>\n  ')
    corpo += (f'<path d="{d}" fill="none" stroke="{CIANO}" stroke-width="{traco * m:.2f}" '
              f'stroke-linecap="round" stroke-linejoin="round"{filtro}/>\n')
    return svg(corpo, tam, tam, defs, titulo="PULSE")


for _v in VARIANTES:
    (OUT / f"pulse_simbolo_{_v}.svg").write_text(simbolo(_v))
(OUT / "pulse_simbolo.svg").write_text(simbolo("completo"))
(OUT / "pulse_simbolo_sem_fundo.svg").write_text(simbolo("completo", fundo=False))

# ------------------------------------------------------------------ marca compacta para a interface
# símbolo ECG pequeno + PULSE + SYSTEM TELEMETRY, altura 40
HU = 40
cap_u = 20
wu, lsbu = medir("PULSE", 125, 600, cap_u, 0.035)
xu = 52
d_u, _, _ = texto("PULSE", 125, 600, cap_u, 0.035, x0=xu - lsbu, base=21)
_w10, _ = medir("SYSTEM TELEMETRY", 100, 500, 10, 0.3)
cap_us = 10 * wu / _w10                 # subtítulo com a mesma largura do PULSE
wus, lsbus = medir("SYSTEM TELEMETRY", 100, 500, cap_us, 0.3)
d_us, _, _ = texto("SYSTEM TELEMETRY", 100, 500, cap_us, 0.3, x0=xu - lsbus, base=21 + 6 + cap_us)
ecg_u = [(2, 20), (12, 20), (16, 16), (20, 20), (23, 20), (26, 23), (31, 3), (37, 34), (41, 17), (44, 20), (xu - 6, 20)]
d_ecg_u = "M" + " L".join(f"{x} {y}" for x, y in ecg_u)
wtot = xu + wu + 2
ui = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {wtot:.0f} {HU}" width="{wtot:.0f}" height="{HU}" '
      f'role="img" aria-label="PULSE — System Telemetry">'
      f'<path d="{d_ecg_u}" fill="none" stroke="{CIANO}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>'
      f'<path d="{d_u}" fill="{BRANCO}"/><path d="{d_us}" fill="#8B9BAD"/></svg>')
(OUT / "pulse_marca_ui.svg").write_text(ui)

# ------------------------------------------------------------------ instalador
def corpo_simbolo(variante, x, y, lado):
    """Símbolo (sem <svg>) posicionado em (x, y) com o lado dado, para compor outras imagens."""
    pts, traco, borda, raio, desf, op = VARIANTES[variante]
    m = lado / 256
    d = "M" + " L".join(f"{x + px * m:.2f} {y + py * m:.2f}" for px, py in pts)
    inset = borda * m / 2 + 2 * m
    return (f'<rect x="{x + inset:.2f}" y="{y + inset:.2f}" width="{lado - 2 * inset:.2f}" height="{lado - 2 * inset:.2f}" '
            f'rx="{raio * m:.2f}" fill="url(#gFundo)" stroke="{CIANO2}" stroke-opacity="{op}" stroke-width="{borda * m:.2f}"/>'
            f'<path d="{d}" fill="none" stroke="{CIANO}" stroke-width="{traco * m:.2f}" stroke-linecap="round" '
            f'stroke-linejoin="round" filter="url(#bri)"/>')


DEFS_SIMB = f"""
    <linearGradient id="gFundo" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{AZUL}"/><stop offset="1" stop-color="#0B111A"/>
    </linearGradient>
    <filter id="bri" x="-30%" y="-30%" width="160%" height="160%">
      <feGaussianBlur in="SourceGraphic" stdDeviation="2.2" result="b"/>
      <feComponentTransfer in="b" result="b2"><feFuncA type="linear" slope="0.8"/></feComponentTransfer>
      <feMerge><feMergeNode in="b2"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <linearGradient id="gAnel" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{CIANO2}" stop-opacity="0.05"/>
      <stop offset="0.5" stop-color="{CIANO2}" stop-opacity="0.45"/>
      <stop offset="1" stop-color="{CIANO2}" stop-opacity="0.05"/>
    </linearGradient>"""

LW, LH = 164, 314
cap_l = 24
wl, lsbl = medir("PULSE", 125, 600, cap_l, 0.035)
d_l, _, _ = texto("PULSE", 125, 600, cap_l, 0.035, x0=(LW - wl) / 2 - lsbl, base=231)
cap_ls = 5.6
wls, lsbls = medir("SYSTEM TELEMETRY", 100, 500, cap_ls, 0.42)
d_ls, _, _ = texto("SYSTEM TELEMETRY", 100, 500, cap_ls, 0.42, x0=(LW - wls) / 2 - lsbls, base=249)
lat = (f'<rect width="{LW}" height="{LH}" fill="#000000"/>\n  '
       f'<circle cx="{LW / 2}" cy="135" r="62" fill="none" stroke="url(#gAnel)" stroke-width="1.6"/>\n  '
       + corpo_simbolo("completo", LW / 2 - 40, 95, 80) + "\n  "
       f'<path d="{d_l}" fill="{BRANCO}"/>\n  <path d="{d_ls}" fill="#8B9BAD"/>\n')
(OUT / "instalador_lateral.svg").write_text(svg(lat, LW, LH, DEFS_SIMB))

HW_, HH_ = 150, 57
cap_h = 15
wh, lsbh = medir("PULSE", 125, 600, cap_h, 0.035)
d_h, _, _ = texto("PULSE", 125, 600, cap_h, 0.035, x0=98 - wh - lsbh, base=28.5 + cap_h / 2)
cab = (f'<rect width="{HW_}" height="{HH_}" fill="#FFFFFF"/>\n  '
       + corpo_simbolo("simples", 106, 9.5, 38) + "\n  "
       f'<path d="{d_h}" fill="{GRAFITE}"/>\n')
(OUT / "instalador_cabecalho.svg").write_text(svg(cab, HW_, HH_, DEFS_SIMB))
print("PULSE", w_pulse, "sub", w_sub, "fim", FIM, "ui", wtot)
