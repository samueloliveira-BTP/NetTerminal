"""Posicionamento dos terminais na tela dividida, com divisões arrastáveis.

Os terminais são posicionados por proporção (place com relx/relwidth). Entre
eles ficam duas "divisórias" que o técnico arrasta com o mouse:
    vertical   -> largura das colunas (fração `fx`)
    horizontal -> altura das linhas   (fração `fy`)
Dois cliques numa divisória voltam para 50/50. As frações ficam salvas.
"""
import tkinter as tk

from netterminal.ui.tema import paleta_atual

ESPACO_PX = 6        # largura da divisória entre terminais
FRACAO_MIN = 0.15    # nenhum painel fica menor que 15% da área


class LayoutPaineis:
    def __init__(self, container, db, cor_destaque):
        self._c = container
        self._db = db
        self._cor_destaque = cor_destaque
        self.fx = self._ler_fracao("painel_frac_x")
        self.fy = self._ler_fracao("painel_frac_y")
        self._itens = []      # [(widget, (linha, coluna, altura, largura))]
        self._grade = (1, 1)  # (linhas, colunas)

        self._div_v = tk.Frame(container, cursor="sb_h_double_arrow", width=ESPACO_PX, bd=0, highlightthickness=0)
        self._div_h = tk.Frame(container, cursor="sb_v_double_arrow", height=ESPACO_PX, bd=0, highlightthickness=0)
        for divisoria, eixo in ((self._div_v, "x"), (self._div_h, "y")):
            divisoria.bind("<B1-Motion>", lambda e, ex=eixo: self._arrastar(e, ex))
            divisoria.bind("<ButtonRelease-1>", lambda e: self._salvar())
            divisoria.bind("<Double-Button-1>", lambda e, ex=eixo: self._resetar(ex))
            divisoria.bind("<Enter>", lambda e, d=divisoria: d.configure(bg=self._cor_destaque()))
            divisoria.bind("<Leave>", lambda e, d=divisoria: d.configure(bg=paleta_atual()["divisoria"]))
        container.bind("<Configure>", lambda e: self._aplicar(), add="+")
        self.aplicar_cores()

    # ------------------------------------------------------------ público
    def definir(self, widgets, posicoes, grade):
        """widgets[i] ocupa posicoes[i] = (linha, coluna, altura, largura) numa grade (linhas, colunas)."""
        novos = set(widgets)
        for widget, _ in self._itens:
            if widget not in novos and widget.winfo_exists():
                widget.place_forget()
        self._itens = list(zip(widgets, posicoes))
        self._grade = grade
        self._aplicar()

    def resetar(self):
        self.fx = self.fy = 0.5
        self._aplicar()
        self._salvar()

    def aplicar_cores(self):
        cor = paleta_atual()["divisoria"]
        self._div_v.configure(bg=cor)
        self._div_h.configure(bg=cor)

    # ------------------------------------------------------------ interno
    def _ler_fracao(self, chave):
        try:
            return min(1 - FRACAO_MIN, max(FRACAO_MIN, float(self._db.get_config(chave, "0.5"))))
        except ValueError:
            return 0.5

    def _aplicar(self):
        largura, altura = self._c.winfo_width(), self._c.winfo_height()
        if largura <= 1 or altura <= 1 or not self._itens:
            self._div_v.place_forget()
            self._div_h.place_forget()
            if largura > 1:
                for widget, _ in self._itens:
                    widget.place(relx=0, rely=0, relwidth=1, relheight=1)
            return
        linhas, colunas = self._grade
        meio_x, meio_y = ESPACO_PX / largura / 2, ESPACO_PX / altura / 2
        limites_x = [0.0, self.fx, 1.0] if colunas == 2 else [0.0, 1.0]
        limites_y = [0.0, self.fy, 1.0] if linhas == 2 else [0.0, 1.0]

        for widget, (linha, coluna, alt, larg) in self._itens:
            x0, x1 = limites_x[coluna], limites_x[coluna + larg]
            y0, y1 = limites_y[linha], limites_y[linha + alt]
            x0 += meio_x if x0 > 0 else 0
            x1 -= meio_x if x1 < 1 else 0
            y0 += meio_y if y0 > 0 else 0
            y1 -= meio_y if y1 < 1 else 0
            widget.place(relx=x0, rely=y0, relwidth=x1 - x0, relheight=y1 - y0)

        if colunas == 2:
            # Com 3 terminais, a divisória vertical só existe na linha de cima
            so_em_cima = linhas == 2 and any(larg == 2 for _, (_, _, _, larg) in self._itens)
            self._div_v.place(relx=self.fx, x=-ESPACO_PX // 2, rely=0, relheight=self.fy if so_em_cima else 1,
                              width=ESPACO_PX)
            self._div_v.lift()
        else:
            self._div_v.place_forget()
        if linhas == 2:
            self._div_h.place(rely=self.fy, y=-ESPACO_PX // 2, relx=0, relwidth=1, height=ESPACO_PX)
            self._div_h.lift()
        else:
            self._div_h.place_forget()

    def _arrastar(self, evento, eixo):
        if eixo == "x":
            fracao = (evento.x_root - self._c.winfo_rootx()) / max(1, self._c.winfo_width())
            self.fx = min(1 - FRACAO_MIN, max(FRACAO_MIN, fracao))
        else:
            fracao = (evento.y_root - self._c.winfo_rooty()) / max(1, self._c.winfo_height())
            self.fy = min(1 - FRACAO_MIN, max(FRACAO_MIN, fracao))
        self._aplicar()

    def _resetar(self, eixo):
        if eixo == "x":
            self.fx = 0.5
        else:
            self.fy = 0.5
        self._aplicar()
        self._salvar()

    def _salvar(self):
        self._db.set_config_lote([("painel_frac_x", f"{self.fx:.4f}"), ("painel_frac_y", f"{self.fy:.4f}")])
