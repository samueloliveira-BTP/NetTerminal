"""NetTerminal — Gerenciador de Ativos de Rede (OLTs, switches e roteadores).

Mapa do pacote (onde mexer em cada coisa):

    netterminal/
    ├── config.py          Caminhos, leitura do .env e parâmetros ajustáveis
    ├── log_config.py      Configuração do app.log, rotação e retenção de logs
    ├── core/              Regras puras, sem interface e sem rede
    │   ├── models.py        Equipamento, Macro, listas de marcas/protocolos
    │   ├── validators.py    Validação de IP, porta e protocolo
    │   ├── redaction.py     Mascaramento de senhas antes de gravar logs
    │   └── csv_seguro.py    Leitura/escrita de CSV protegida contra "formula injection"
    ├── security/          Tudo que envolve segredo
    │   ├── dpapi.py         Proteção da chave mestra com o DPAPI do Windows
    │   ├── crypto.py        Chave mestra + criptografia Fernet das senhas
    │   ├── hostkeys.py      Verificação de chave de host SSH (known_hosts)
    │   └── admin.py         Senha de admin e ações protegidas
    ├── data/database.py   Acesso ao SQLite (thread-safe)
    ├── net/               Conexões de rede
    │   ├── telnet.py        Cliente Telnet mínimo
    │   ├── sessao.py        Sessões SSH/Telnet em background (fila de eventos)
    │   └── monitor.py       Monitor de status (porta TCP + latência)
    ├── services/          Casos de uso que não são interface
    │   ├── auditoria.py     Histórico de comandos e duração de sessões
    │   ├── transferencia.py Importação/exportação de CSV
    │   └── updater.py       Atualização automática segura
    └── ui/                Interface gráfica (CustomTkinter)
        ├── app.py           Janela principal (árvore, abas, menu)
        ├── terminal_tab.py  Aba de terminal
        ├── splash.py, tema.py, utils.py
        └── dialogs/         Uma janela por arquivo
"""

APP_NAME = "NetTerminal"
APP_VERSION = "2.1.1"
