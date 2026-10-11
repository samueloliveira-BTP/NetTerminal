"""Ping e traceroute para um equipamento, com saída ao vivo.

Os comandos do Windows são chamados com lista de argumentos (sem shell) e o
IP é validado antes — não há como injetar comandos pelo campo de endereço.
"""
import logging
import queue
import subprocess
import threading

import customtkinter as ctk

from netterminal.core.validators import ip_valido
from netterminal.ui.utils import msgbox, nova_janela

log = logging.getLogger(__name__)

_MODOS = {
    "ping": ("Ping", lambda ip: ["ping", "-n", "10", ip]),
    "ping_continuo": ("Ping contínuo", lambda ip: ["ping", "-t", ip]),
    "tracert": ("Traceroute", lambda ip: ["tracert", "-d", "-w", "1000", "-h", "30", ip]),
}
_SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _decodificar(linha):
    # Saída do ping/tracert no Windows vem na página de código OEM do console
    for codificacao in ("oem", "cp850", "utf-8"):
        try:
            return linha.decode(codificacao)
        except (LookupError, UnicodeDecodeError):
            continue
    return linha.decode("latin-1", errors="replace")


def abrir(app, ip, modo="ping"):
    ip = (ip or "").strip()
    if not ip_valido(ip):
        msgbox(app, "error", "Erro", f"'{ip}' não é um IP válido.")
        return
    top = nova_janela(app, f"Ferramentas de rede — {ip}", "760x480")
    estado = {"processo": None, "fila": queue.Queue()}

    topo = ctk.CTkFrame(top, fg_color="transparent")
    topo.pack(fill="x", padx=10, pady=(10, 0))
    seletor = ctk.CTkSegmentedButton(topo, values=[v[0] for v in _MODOS.values()])
    seletor.pack(side="left")
    lbl = ctk.CTkLabel(topo, text="")
    lbl.pack(side="left", padx=12)
    texto = ctk.CTkTextbox(top, font=("Consolas", 12))
    texto.pack(expand=True, fill="both", padx=10, pady=10)

    def parar():
        proc = estado["processo"]
        if proc and proc.poll() is None:
            proc.terminate()

    def iniciar(rotulo=None):
        parar()
        chave = next(k for k, v in _MODOS.items() if v[0] == (rotulo or seletor.get()))
        texto.configure(state="normal")
        texto.delete("1.0", "end")
        lbl.configure(text="Executando...")
        try:
            proc = subprocess.Popen(_MODOS[chave][1](ip), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    creationflags=_SEM_JANELA)
        except OSError as e:
            log.error(f"Falha ao executar {chave}: {e}")
            lbl.configure(text="Falha ao executar o comando.")
            return
        estado["processo"] = proc
        log.info(f"{_MODOS[chave][0]} iniciado para {ip}")

        def ler(p=proc, fila=estado["fila"]):
            for linha in iter(p.stdout.readline, b""):
                fila.put(_decodificar(linha).rstrip("\r\n"))
            p.wait()
            fila.put(None)
        threading.Thread(target=ler, daemon=True).start()

    def consumir():
        if not top.winfo_exists():
            return
        try:
            while True:
                linha = estado["fila"].get_nowait()
                if linha is None:
                    lbl.configure(text="Concluído.")
                    continue
                texto.insert("end", linha + "\n")
                texto.see("end")
        except queue.Empty:
            pass
        top.after(100, consumir)

    def copiar():
        top.clipboard_clear()
        top.clipboard_append(texto.get("1.0", "end-1c"))

    def ao_fechar():
        parar()
        top.destroy()

    rodape = ctk.CTkFrame(top, fg_color="transparent")
    rodape.pack(fill="x", padx=10, pady=(0, 10))
    ctk.CTkButton(rodape, text="▶ Executar", width=110, command=iniciar).pack(side="left")
    ctk.CTkButton(rodape, text="■ Parar", width=90, fg_color="#8B0000", hover_color="red",
                  command=lambda: (parar(), lbl.configure(text="Interrompido."))).pack(side="left", padx=8)
    ctk.CTkButton(rodape, text="📋 Copiar resultado", width=150, command=copiar).pack(side="left")

    seletor.configure(command=iniciar)
    seletor.set(_MODOS[modo][0])
    top.protocol("WM_DELETE_WINDOW", ao_fechar)
    consumir()
    iniciar()
