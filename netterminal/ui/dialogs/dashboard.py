"""Dashboard de uso: tempo logado, comandos e equipamentos mais usados."""
from collections import Counter

import customtkinter as ctk

from netterminal.services import auditoria
from netterminal.ui.utils import nova_janela

_PREFIXOS_ORIGEM = ("[MACRO] ", "[COLADO] ", "[LOTE] ")


def _sem_prefixo(comando):
    for prefixo in _PREFIXOS_ORIGEM:
        comando = comando.replace(prefixo, "")
    return comando.strip()


def abrir(app):
    top = nova_janela(app, "Dashboard de Uso", "720x600")

    historico = auditoria.ler_historico()
    contagem_comandos = Counter(c for c in (_sem_prefixo(r[4]) for r in historico) if c)
    contagem_alvos = Counter(r[2] for r in historico)
    segundos, n_sessoes = auditoria.ler_total_sessoes()
    horas, resto = divmod(segundos, 3600)

    resumo = ctk.CTkFrame(top, corner_radius=10)
    resumo.pack(fill="x", padx=15, pady=15)
    ctk.CTkLabel(resumo, text="Resumo Geral", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(15, 10))
    ctk.CTkLabel(resumo, text=f"⏱️ Tempo total logado: {horas}h {resto // 60}min  ({n_sessoes} sessões)").pack(anchor="w", padx=20, pady=3)
    ctk.CTkLabel(resumo, text=f"⌨️ Total de comandos registrados: {len(historico)}").pack(anchor="w", padx=20, pady=(3, 15))

    colunas = ctk.CTkFrame(top, fg_color="transparent")
    colunas.pack(expand=True, fill="both", padx=15, pady=(0, 15))

    def coluna(titulo, contagem, limite, padding):
        frame = ctk.CTkFrame(colunas, corner_radius=10)
        frame.pack(side="left", expand=True, fill="both", padx=padding)
        ctk.CTkLabel(frame, text=titulo, font=ctk.CTkFont(weight="bold")).pack(pady=(15, 10))
        if not contagem:
            ctk.CTkLabel(frame, text="Sem dados ainda.", text_color="gray").pack(pady=10)
            return
        for item, qtd in contagem.most_common(10):
            texto = item if len(item) <= limite else item[:limite - 3] + "..."
            ctk.CTkLabel(frame, text=f"{qtd}x  {texto}", anchor="w", justify="left").pack(anchor="w", padx=15, pady=2)

    coluna("🔝 Comandos mais usados", contagem_comandos, 38, (0, 8))
    coluna("📡 Equipamentos mais acessados", contagem_alvos, 32, (8, 0))
