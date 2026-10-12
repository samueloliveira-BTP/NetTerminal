# NetTerminal — Gerenciador de Ativos de Rede

Terminal SSH/Telnet com cadastro de OLTs, switches e roteadores, macros por
marca, monitor de status, histórico auditável de comandos e atualização
automática segura.

## Funcionalidades

| Recurso | Onde fica |
|---|---|
| Terminal SSH/Telnet em abas, **tela dividida** (1, 2 ou 4 painéis) | Canto superior direito da área de abas |
| **Divisórias arrastáveis**, **expandir terminal** (⤢), **ocultar barras** (▴), **ocultar lista** (◧), **modo foco** (⛶ / F11) | Menu **Exibir** e botões ao lado das abas |
| **Localizar texto na aba** | `Ctrl+Shift+F` ou botão 🔍 no terminal |
| **Fonte do terminal** | `Ctrl + roda do mouse` ou Configurações > Aparência |
| **Tema claro/escuro** | Configurações > Aparência |
| **Realce de sintaxe personalizado** (palavra, texto ou regex + cor) | Configurações > Realce de Sintaxe |
| **Assistente de provisionamento de ONU** | Botão 🧙 ONU no terminal |
| **Busca de ONU por serial/descrição em várias OLTs** | Ferramentas > Buscar ONU em todas as OLTs |
| Modelos de comando de ONU por marca | Configurações > Modelos de ONU |
| **Ping / ping contínuo / traceroute** | Botão direito no equipamento ou botões no terminal |
| **Perfil da equipe** (exportar/importar configurações) | Configurações > Exportar/Importar Perfil |
| Macros com variáveis `[VAR]` e listas `[VAR\|a,b]` | Configurações > Macros |
| Monitor de status, painel, histórico e dashboard | Ferramentas |
| **Instalador MSI** com atalho no Menu Iniciar e atualização silenciosa | `installer/` |

## Estrutura do projeto

```
OLT_Manager/
├── NETerminal.py          Ponto de entrada (python NETerminal.py)
├── NETerminal.spec        Build do executável (PyInstaller)
├── netterminal/           Código-fonte do aplicativo
│   ├── config.py            Caminhos, .env e parâmetros ajustáveis
│   ├── log_config.py        app.log, rotação e retenção
│   ├── main.py              Sequência de inicialização
│   ├── core/                Regras puras: modelos, validação, mascaramento, CSV,
│   │                        realce (destaque.py), modelos de ONU (onu.py), saida.py
│   ├── security/            DPAPI, criptografia, host keys SSH, senha de admin
│   ├── data/database.py     SQLite (thread-safe)
│   ├── net/                 Telnet, sessões SSH/Telnet, executor (busca), monitor
│   ├── services/            Auditoria, CSV, perfil da equipe, atualização
│   └── ui/                  Interface: app.py, terminal_tab.py, menu.py, dialogs/
├── installer/             Instalador MSI (NetTerminal.wxs + build_msi.ps1)
├── assets/                Ícone e imagem da tela de abertura
├── tests/                 Testes automatizados (incluem servidores SSH/Telnet falsos)
├── tools/                 Utilitários de linha de comando (importar_relatorio.py)
├── legado/                Versões antigas (1.0 a 1.4.1), só para consulta
├── _backups/              Backups zipados do código (não versionar)
└── .env.example           Modelo de configuração
```

**Onde mexer:**

| Quero mudar... | Arquivo |
|---|---|
| Uma janela (cadastro, macros, histórico...) | `netterminal/ui/dialogs/<janela>.py` |
| O comportamento do terminal (teclas, cores, colar) | `netterminal/ui/terminal_tab.py` |
| O menu do topo | `netterminal/ui/menu.py` |
| Como conecta via SSH/Telnet | `netterminal/net/sessao.py` |
| Tabelas/consultas do banco | `netterminal/data/database.py` |
| O que é mascarado no histórico | `netterminal/core/redaction.py` |
| Comandos padrão de ONU por marca / validação dos campos | `netterminal/core/onu.py` |
| Regras de realce padrão | `netterminal/core/destaque.py` |
| Tela dividida, tema, fonte | `netterminal/ui/app.py`, `netterminal/ui/tema.py` |
| Busca na aba, botões do terminal | `netterminal/ui/terminal_tab.py` |
| Busca global de ONU (conexão automática) | `netterminal/net/executor.py`, `ui/dialogs/busca_onu.py` |
| Timeout, intervalo do monitor, retenção de logs | `.env` (veja `.env.example`) |

## Rodar em desenvolvimento

```bash
uv sync
```

```bash
.venv\Scripts\python.exe NETerminal.py
```

## Testes

```bash
.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
```

Os testes não acessam nenhum equipamento real: sobem servidores SSH/Telnet
falsos em 127.0.0.1 e usam pastas temporárias.

## Gerar o executável

```bash
.venv\Scripts\pyinstaller.exe NETerminal.spec --noconfirm
```

Saída: `dist\NETerminal.exe`. O `.env` (opcional) fica ao lado do `.exe`.

## Gerar o instalador MSI

Pré-requisito (uma vez): WiX Toolset v4+ — `winget install --id WiXToolset.WiXCLI`

```bash
powershell -ExecutionPolicy Bypass -File installer\build_msi.ps1
```

Saída: `dist\NetTerminal-<versão>.msi` e `dist\versao.json` (modelo do JSON
do servidor de atualização, já com o SHA-256).

- Instala **por usuário** em `%LOCALAPPDATA%\Programs\NetTerminal` (sem pedir
  administrador), com atalho no Menu Iniciar e na Área de Trabalho.
- Versão nova substitui a antiga automaticamente (MajorUpgrade).
- Instalação silenciosa em massa: `msiexec /i NetTerminal-x.y.z.msi /qn`
  (sem atalho na área de trabalho: acrescente `ATALHO_DESKTOP=0`).
- **Atualização automática:** publique o `.msi` e o `versao.json` (com
  `url_download` preenchida) num servidor HTTPS e aponte `UPDATE_CHECK_URL`
  no `.env`. O app baixa, confere o SHA-256, fecha, instala com barra de
  progresso (`/passive`) e abre de novo sozinho.
- Os dados do usuário (`%USERPROFILE%\.olt_manager`) não são tocados pela
  instalação nem pela desinstalação.

## Lançar e distribuir uma versão (repositório privado)

O workflow `.github/workflows/release.yml` roda numa máquina Windows do
GitHub (sem precisar de admin na sua máquina): testes → `.exe` → `.msi`
(WiX 5, licença MS-RL) → Release **privada** com `NetTerminal-X.Y.Z.msi` e
`versao.json` (que traz o SHA-256 do instalador).

### Lançar

1. Atualize `APP_VERSION` em `netterminal/__init__.py`, o `pyproject.toml` e
   o `CHANGELOG.md`; faça commit e *Push origin* no GitHub Desktop.
2. No GitHub: *Releases → Draft a new release → Choose a tag →* digite
   `vX.Y.Z` (igual ao `APP_VERSION`) → *Create new tag* → *Publish release*.
3. Acompanhe em *Actions* (~3 min). Ao terminar, o `.msi` aparece anexado
   na Release.

### Distribuir para a equipe

O link da Release privada **só abre para quem tem acesso ao repositório**.
Para o restante da equipe:

1. Baixe o `NetTerminal-X.Y.Z.msi` da Release.
2. Compartilhe o **arquivo** por um canal interno da empresa (pasta de rede,
   OneDrive/SharePoint, Teams) junto com o SHA-256 que está no `versao.json`.
3. Cada técnico (opcional, recomendado) confere o arquivo antes de instalar:

   ```bash
   Get-FileHash .\NetTerminal-X.Y.Z.msi -Algorithm SHA256
   ```

4. Executar o `.msi`: não pede administrador, **substitui a versão anterior**
   e mantém dados, senhas e configurações (`%USERPROFILE%\.olt_manager`).

Em *Ajuda → Verificar atualizações agora* o técnico vê a versão instalada e a
orientação de que as atualizações são distribuídas pela equipe.

> Se no futuro houver um servidor HTTPS interno, basta publicar nele o `.msi`
> e o `versao.json` e definir `UPDATE_CHECK_URL` no `.env`: o app passa a se
> atualizar sozinho (veja "Gerar o instalador MSI").

### Cuidados
- Mantenha **autenticação em dois fatores** na conta do GitHub e só dê acesso
  ao repositório a quem precisa.
- Distribua o instalador sempre pelo mesmo canal interno e com o SHA-256 —
  assim ninguém instala um arquivo trocado.

## Dados do usuário

Ficam em `%USERPROFILE%\.olt_manager\`:

| Arquivo | Conteúdo |
|---|---|
| `olts.db` | Cadastro, macros, configurações, status (SQLite) |
| `security.key.dpapi` | Chave mestra, protegida pelo DPAPI do Windows |
| `known_hosts` | Chaves SSH conhecidas dos equipamentos |
| `historico_comandos.log` | Auditoria de comandos (segredos mascarados) |
| `sessoes.log` | Duração das sessões |
| `app.log` | Log técnico (erros, conexões) |

## Segurança

| Controle | Como funciona |
|---|---|
| Senhas salvas | Fernet (AES-128 + HMAC). A chave mestra é protegida pelo **DPAPI**: só abre com o mesmo usuário do Windows. |
| SSH | Verificação de chave de host (TOFU). Chave alterada **bloqueia** a conexão até o técnico confirmar. |
| SSH legado | Algoritmos antigos (`ssh-rsa`/SHA-1) só para equipamentos marcados, com confirmação do técnico e registro no log; nunca alteram as demais conexões (`net/ssh_legado.py`). |
| Monitor de status | Ping ICMP — não abre sessões na porta de login, então não aciona o bloqueio anti-força-bruta dos equipamentos. |
| Telnet | Aviso de texto claro; usuário e senha só são enviados quando o equipamento pede. |
| Auditoria | Usuário real (`usuario@maquina`), senhas/communities mascaradas, digitação em prompt de senha nunca é gravada; envio opcional para syslog central. |
| Inatividade | Sessão encerrada após `SESSION_IDLE_TIMEOUT_MIN` (padrão 10 min). |
| Colagem | Confirmação antes de enviar texto com várias linhas. |
| Senha de admin | PBKDF2-SHA256 (600 mil iterações), bloqueio após 5 erros, ações protegidas configuráveis. |
| CSV | Proteção contra *formula injection*; importação valida IP, porta e protocolo; credenciais nunca exportadas. |
| Atualização | HTTPS obrigatório (inclusive redirecionamentos), host restrito, SHA-256 obrigatório, assinatura Authenticode opcional. |
| SQL | Somente consultas parametrizadas. |
| Provisionamento de ONU | Campos validados (serial, VLAN 1–4094, IDs numéricos, sem quebra de linha); prévia obrigatória + "Revisei" + confirmação; tudo auditado como `[ONU]`. |
| Busca global | Executa só os modelos de consulta; máximo 8 conexões simultâneas; mesma verificação de chave SSH; auditado como `[BUSCA]`. |
| Realce por regex | Expressões que travariam o terminal (backtracking exponencial) são recusadas. |
| Perfil da equipe | Nunca contém credenciais, senha de admin, permissões ou chaves SSH; importação ignora esses campos e valida tudo. |
| Ping/traceroute | Comandos chamados sem shell, com IP validado. |

**Limitações conhecidas** (aceitas por serem uma aplicação desktop local):
- Quem tem acesso à conta do Windows do técnico consegue usar o app e,
  portanto, as credenciais salvas. A senha de admin é uma barreira de uso,
  não um controle contra o dono da conta.
- Os logs locais podem ser editados pelo próprio usuário; para auditoria à
  prova de alteração, configure `AUDIT_SYSLOG_HOST`.
- Os logs podem conter dados de clientes (seriais de ONU, descrições). A
  retenção (`LOG_RETENTION_DAYS`) deve ser definida com o responsável de LGPD.
