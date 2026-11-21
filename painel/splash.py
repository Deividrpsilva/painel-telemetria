# PULSE - tela de inicialização (splash)
#
# Janela sem bordas, fundo preto, com o logo PULSE "respirando" (ciclo de 2,5 s, escala de 98% a 102%,
# brilho de 60% a 100%), um texto de status e uma barra de progresso. Ela aparece logo que o PULSE é
# aberto e fica até a janela de configuração estar pronta. Quem está carregando manda o andamento
# real para 127.0.0.1:5683, uma linha por mensagem:
#   p <0-100> <texto>   progresso e status
#   vivo                ainda carregando (mandado a cada 2 s por quem abriu a splash)
#   fim                 interface pronta: completa a barra e some com um fade
#   erro <texto>        mostra o erro e fecha depois de alguns segundos
# Ela fecha sozinha se ninguém der notícia por 12 s (quem a abriu travou ou fechou) e depois de 90 s.
# Só existe uma splash por vez (a porta 5683 funciona como trava). Sem Tkinter, simplesmente não aparece.
#
# Uso direto (testes):  pythonw painel/splash.py
import math
import platform
import queue
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

PORTA = 5683
PASTA = Path(__file__).resolve().parent
MARCA = PASTA / "marca"
WINDOWS = platform.system() == "Windows"

CICLO = 2.5                # s
ESCALA = 0.02              # 98% a 102%
SILENCIO_MAX = 12.0        # s sem notícias -> fecha
VIDA_MAX = 90.0            # s no máximo

PRETO, AZUL, CIANO, CINZA, ERRO = "#000000", "#162234", "#00E5FF", "#8B9BAD", "#FF6B7D"


# ------------------------------------------------------------------ lado de quem abre a splash
def splash_aberta():
    try:
        with socket.create_connection(("127.0.0.1", PORTA), timeout=0.3):
            return True
    except OSError:
        return False


def avisar(msg):
    """Manda uma mensagem para a splash, se ela estiver aberta. Nunca falha."""
    try:
        with socket.create_connection(("127.0.0.1", PORTA), timeout=0.5) as s:
            s.sendall((msg + "\n").encode("utf-8"))
    except OSError:
        pass


def abrir_splash(texto=None):
    """Abre a splash (se ainda não estiver aberta) sem esperar por ela."""
    try:
        if not splash_aberta():
            exe = Path(sys.executable)
            pyw = exe.with_name("pythonw.exe")
            exe = pyw if WINDOWS and pyw.exists() else exe
            kw = {"creationflags": 0x00000008 | 0x00000200} if WINDOWS else {"start_new_session": True}
            subprocess.Popen([str(exe), str(PASTA / "splash.py")] + ([texto] if texto else []),
                             cwd=str(PASTA.parent), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, **kw)
        elif texto:
            avisar(f"p 0 {texto}")
    except Exception:
        pass


class Batimento:
    """Avisa a splash a cada 2 s que o carregamento continua (se o processo morrer, ela fecha sozinha)."""

    def __init__(self):
        self._fim = threading.Event()
        threading.Thread(target=self._rodar, daemon=True).start()

    def _rodar(self):
        while not self._fim.wait(2.0):
            avisar("vivo")

    def parar(self):
        self._fim.set()


# ------------------------------------------------------------------ a janela
def _servidor(srv, fila):
    while True:
        try:
            con, _ = srv.accept()
        except OSError:
            return
        threading.Thread(target=_ler, args=(con, fila), daemon=True).start()


def _ler(con, fila):
    with con:
        con.settimeout(5)
        buf = b""
        try:
            while True:
                parte = con.recv(1024)
                if not parte:
                    break
                buf += parte
                while b"\n" in buf:
                    linha, buf = buf.split(b"\n", 1)
                    fila.put(linha.decode("utf-8", "ignore").strip())
        except OSError:
            pass
        if buf.strip():
            fila.put(buf.decode("utf-8", "ignore").strip())


def _dpi_aware():
    if not WINDOWS:
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


class Splash:
    def __init__(self, fila, texto_inicial):
        import tkinter as tk
        from PIL import Image, ImageChops, ImageEnhance, ImageTk
        self.Image, self.ImageChops, self.ImageEnhance, self.ImageTk = Image, ImageChops, ImageEnhance, ImageTk
        self.fila = fila
        self.root = root = tk.Tk()
        root.withdraw()
        self.e = e = max(1.0, root.winfo_fpixels("1i") / 96.0)      # escala do Windows (100%, 125%, 150%...)
        self.W, self.H = round(560 * e), round(340 * e)
        root.overrideredirect(True)
        root.configure(bg=PRETO)
        root.title("PULSE")
        x = (root.winfo_screenwidth() - self.W) // 2
        y = (root.winfo_screenheight() - self.H) // 2
        root.geometry(f"{self.W}x{self.H}+{x}+{y}")
        root.attributes("-topmost", True)
        self.alfa_ok = True
        try:
            root.attributes("-alpha", 0.0)
        except tk.TclError:
            self.alfa_ok = False
        cv = self.cv = tk.Canvas(root, width=self.W, height=self.H, bg=PRETO, highlightthickness=0, bd=0)
        cv.pack()

        # camadas do logo, já sobre o fundo preto (a soma de luz fica simples: fundo absoluto)
        self.LW = round(470 * e)
        self.LH = round(self.LW * 560 / 1200)
        self.camadas = {}
        for nome in ("texto", "linha", "brilho"):
            im = Image.open(MARCA / f"splash_{nome}.png").convert("RGBA").resize((self.LW, self.LH), Image.LANCZOS)
            fundo = Image.new("RGBA", im.size, (0, 0, 0, 255))
            fundo.alpha_composite(im)
            self.camadas[nome] = fundo.convert("RGB")
        self.quadros = {}
        self.logo_y = round(self.H * 0.42)
        self.item_logo = cv.create_image(self.W // 2, self.logo_y, anchor="center")

        self.y_status = round(self.H * 0.80)
        self.item_status = cv.create_text(self.W // 2, self.y_status, text=texto_inicial, fill=CINZA,
                                          font=("Segoe UI", 10) if WINDOWS else ("DejaVu Sans", 10))
        bw, bh = round(220 * e), max(2, round(3 * e))
        self.bx0, self.by0 = self.W // 2 - bw // 2, round(self.H * 0.87)
        self.bw, self.bh = bw, bh
        cv.create_rectangle(self.bx0, self.by0, self.bx0 + bw, self.by0 + bh, fill=AZUL, width=0)
        self.item_barra = cv.create_rectangle(self.bx0, self.by0, self.bx0, self.by0 + bh, fill=CIANO, width=0)

        self.progresso = 0.0          # mostrado
        self.alvo = 5.0               # recebido
        self.estado = "abrindo"       # abrindo -> rodando -> fechando
        self.alfa = 0.0
        self.t0 = time.monotonic()
        self.ultimo_contato = self.t0
        self.fechar_em = None
        self._cantos_arredondados()
        root.deiconify()

    def _cantos_arredondados(self):
        if not WINDOWS:
            return
        try:  # Windows 11: cantos arredondados também em janela sem bordas
            import ctypes
            self.root.update_idletasks()
            hwnd = int(self.root.wm_frame(), 16)
            valor = ctypes.c_int(2)                                              # DWMWCP_ROUND
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(valor), ctypes.sizeof(valor))
        except Exception:
            pass

    # ---------- animação
    def quadro(self, nivel, niveis):
        """Logo para um ponto do ciclo (nivel 0..niveis-1, de -1 a +1 no seno). Fica em cache."""
        if nivel not in self.quadros:
            v = nivel / (niveis - 1) * 2 - 1
            Image, ImageChops, ImageEnhance = self.Image, self.ImageChops, self.ImageEnhance
            brilho = ImageEnhance.Brightness(self.camadas["brilho"]).enhance(0.8 + 0.2 * v)    # 60% a 100%
            linha = ImageEnhance.Brightness(self.camadas["linha"]).enhance(0.86 + 0.14 * v)
            im = ImageChops.add(ImageChops.add(brilho, linha), self.camadas["texto"])
            s = 1 + ESCALA * v
            im = im.resize((round(self.LW * s), round(self.LH * s)), Image.BICUBIC)
            self.quadros[nivel] = self.ImageTk.PhotoImage(im)
        return self.quadros[nivel]

    def tick(self):
        agora = time.monotonic()
        self._mensagens(agora)
        fase = ((agora - self.t0) % CICLO) / CICLO
        niveis = 25
        nivel = round((math.sin(2 * math.pi * fase) + 1) / 2 * (niveis - 1))
        self.cv.itemconfigure(self.item_logo, image=self.quadro(nivel, niveis))

        self.progresso += (self.alvo - self.progresso) * (0.25 if self.alvo >= 100 else 0.12)
        if abs(self.alvo - self.progresso) < 0.3:
            self.progresso = self.alvo
        self.cv.coords(self.item_barra, self.bx0, self.by0, self.bx0 + self.bw * self.progresso / 100, self.by0 + self.bh)

        if self.estado == "abrindo":
            self.alfa = min(1.0, self.alfa + 0.12)
            if self.alfa >= 1.0:
                self.estado = "rodando"
        elif self.estado == "rodando":
            if self.fechar_em is None:
                if agora - self.ultimo_contato > SILENCIO_MAX or agora - self.t0 > VIDA_MAX:
                    self.status("Não foi possível concluir a inicialização.", ERRO)
                    self.fechar_em = agora + 3.0
            elif agora >= self.fechar_em and (self.progresso >= self.alvo or self.alvo < 100):
                self.estado = "fechando"
        elif self.estado == "fechando":
            self.alfa -= 0.1
            if self.alfa <= 0:
                self.root.destroy()
                return
        if self.alfa_ok:
            self.root.attributes("-alpha", max(0.0, self.alfa))
        self.root.after(33, self.tick)

    def status(self, texto, cor=CINZA):
        self.cv.itemconfigure(self.item_status, text=texto, fill=cor)

    def _mensagens(self, agora):
        while True:
            try:
                m = self.fila.get_nowait()
            except queue.Empty:
                return
            self.ultimo_contato = agora
            if m.startswith("p "):
                partes = m.split(" ", 2)
                try:
                    self.alvo = max(self.alvo, min(100.0, float(partes[1])))
                except (IndexError, ValueError):
                    pass
                if len(partes) > 2 and partes[2]:
                    self.status(partes[2])
            elif m == "fim":
                self.alvo = 100.0
                self.status("Pronto")
                self.fechar_em = agora              # some assim que a barra completar
            elif m.startswith("erro"):
                self.status(m[4:].strip() or "Falha na inicialização.", ERRO)
                self.fechar_em = agora + 4.0


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        srv.bind(("127.0.0.1", PORTA))      # trava: só uma splash por vez
        srv.listen(8)
    except OSError:
        return
    fila = queue.Queue()
    threading.Thread(target=_servidor, args=(srv, fila), daemon=True).start()
    _dpi_aware()
    texto = sys.argv[1] if len(sys.argv) > 1 else "Inicializando..."
    try:
        s = Splash(fila, texto)
    except Exception as e:  # sem Tkinter/Pillow ou sem tela: segue sem splash
        print("Splash indisponível:", e)
        srv.close()
        return
    s.root.after(0, s.tick)
    s.root.mainloop()
    srv.close()


if __name__ == "__main__":
    main()
