# Histórico de versões

## 2.1.1 — 2026-10-11

- **Tela dividida adaptativa:** o modo escolhido (1, 2 ou 4) passa a ser o
  máximo de terminais visíveis e a grade se ajusta à quantidade aberta —
  1 terminal ocupa a tela toda, 2 ficam lado a lado, 3 ficam dois em cima e
  um embaixo na largura toda, 4 em grade 2x2. Corrigido: com o modo 4, cada
  terminal ocupava só 1/4 da tela mesmo sozinho; e a aba nova substituía um
  terminal visível em vez de ocupar o painel livre.
- O terminal não força mais uma altura mínima (evitava que 4 painéis com
  fonte grande coubessem na tela).
- **Monitor de status por ping (ICMP)** em vez de abrir conexão na porta de
  login a cada 15 s. O método antigo fazia equipamentos Huawei bloquearem o
  IP do técnico ("The IP has been blocked and you cannot log on it") e enchia
  os logs das OLTs de conexões sem login. Usa a API de ping do Windows (não
  precisa de administrador). `MONITOR_METHOD=tcp` no `.env` volta ao antigo;
  IPv6 usa TCP automaticamente.
- **SSH legado por equipamento** para OLTs de firmware antigo que só aceitam
  chave `ssh-rsa` (SHA-1) — removida dos padrões do paramiko 4+. Ao falhar com
  "no acceptable host key", o app pergunta se libera SOMENTE aquele
  equipamento (também em Editar equipamento). Continua cifrado e com
  verificação de chave; as demais conexões não mudam. No modo legado, a troca
  de chaves prefere `group14-sha256` (a ZTE_SSH.1.0 anuncia `group16` mas
  derruba a conexão quando ele é escolhido).
- Distribuição **privada**: o build gera o `.msi` na Release do repositório
  privado; a equipe recebe o instalador por canal interno, com SHA-256.
- Novo: *Ajuda → Verificar atualizações agora*.

## 2.1.0 — 2026-10-11

### Novidades
- **Assistente de provisionamento de ONU** (botão 🧙 ONU no terminal): formulário
  gerado a partir do modelo da marca, validação dos campos, prévia obrigatória,
  envio linha a linha e botão "Listar ONUs pendentes".
- **Busca de ONU por serial ou descrição em várias OLTs** em paralelo (todas, por
  marca, por grupo ou selecionadas), com trecho encontrado e saída completa.
  Responde sozinha a "---- More ----" e às confirmações `{ <cr> }` da Huawei.
- **Modelos de ONU por marca** editáveis (padrões para Datacom, Huawei e ZTE
  baseados nas macros da equipe — validar em laboratório).
- **Localizar texto na aba** (Ctrl+Shift+F), com destaque de todas as
  ocorrências e navegação.
- **Tela dividida**: 1, 2 (lado a lado ou empilhados) ou 4 terminais.
- **Ping, ping contínuo e traceroute** com saída ao vivo.
- **Tema claro/escuro/igual ao Windows** e **fonte do terminal ajustável**
  (Ctrl + roda do mouse).
- **Realce de sintaxe personalizado**: palavras, nomes ou regex com cor e
  negrito; as cores antigas (up/down/IP/MAC) viraram regras editáveis; prévia
  ao vivo.
- **Perfil da equipe**: exporta/importa aparência, regras de realce, macros,
  modelos de ONU e equipamentos/grupos em JSON (sem segredos).
- **Instalador MSI** (WiX) por usuário, com atalhos e **atualização silenciosa**
  (o app instala com `/passive` e reabre sozinho).
- Ajuda > Atalhos de teclado.

### Correções
- Gravação do histórico agora é segura com várias threads (a busca paralela
  podia perder linhas de auditoria no Windows).
- Atualização automática: o modo TLS "estrito" do Python 3.13+ recusava a
  cadeia de certificados do GitHub; agora a validação é a mesma dos
  navegadores (cadeia + nome do host), e certificados inválidos continuam
  recusados.
- Build do MSI no GitHub Actions (`.github/workflows/release.yml`), sem
  precisar de administrador na máquina local.

## 2.0.0 — 2026-10-11

Reestruturação completa: o arquivo único `NETerminal.py` (2.378 linhas) virou
o pacote `netterminal/`, separado por responsabilidade. O código anterior
está em `legado/NETerminal_v1.4.1.py` e em `_backups/`.

### Segurança
- **Corrigido:** a desconexão por inatividade nunca disparava (o timer não
  era reagendado se a conexão ainda não tinha terminado ao abrir a aba).
- **Corrigido:** senhas digitadas em login manual (e em qualquer prompt de
  senha) eram gravadas em texto puro no histórico de comandos.
- **Novo:** mascaramento de senhas, communities, secrets e chaves no histórico.
- **Novo:** chave mestra protegida pelo DPAPI do Windows; migração automática
  da `security.key` em texto puro (o arquivo antigo é removido após verificar).
- **Novo:** verificação de chave de host SSH (known_hosts). Antes, qualquer
  chave era aceita (`AutoAddPolicy`), permitindo man-in-the-middle.
- **Novo:** atualização automática exige HTTPS, SHA-256 e host permitido;
  assinatura Authenticode opcional. Antes, um JSON sem hash executava o
  instalador sem verificação.
- **Novo:** histórico registra o usuário real do Windows (antes: sempre "local");
  envio opcional para syslog central.
- **Novo:** senha de admin (compatível com o hash da versão de teste 1.4,
  atualizado para 600 mil iterações), com bloqueio após 5 tentativas.
- **Novo:** confirmação ao colar várias linhas no terminal.
- **Novo:** proteção contra CSV/formula injection nas exportações.
- **Corrigido:** senha cifrada com chave diferente era enviada ao equipamento
  como se fosse a senha (agora vira vazio e gera erro no log).
- **Corrigido:** senhas antigas em texto puro no banco agora são cifradas.
- **Corrigido:** a senha global não é mais carregada decifrada na tela de
  credenciais nem nos dados da árvore de equipamentos.
- Telnet: usuário/senha só são enviados quando o prompt é detectado; aviso de
  conexão sem criptografia.

### Estabilidade
- A interface não é mais alterada a partir de threads de rede (causa de
  travamentos aleatórios); as sessões usam uma fila de eventos.
- Acesso ao SQLite serializado entre threads.
- Monitor de status testa os equipamentos em paralelo.
- Detecção de conexão encerrada pelo equipamento + botão "Reconectar".
- Realce de sintaxe só recolore o final do buffer; limite de linhas por aba.
- Erros em botões vão para o app.log com aviso amigável (antes sumiam
  silenciosamente no executável).

### Funcionalidades e correções
- SSH com login manual agora pede usuário/senha numa janela (antes falhava).
- Importação de CSV valida IP, porta e protocolo e informa as linhas inválidas.
- Exclusão de vários equipamentos selecionados de uma vez.
- Ctrl+V / Shift+Insert colam no terminal; Enter/Delete na árvore conectam/excluem.
- Validação de cor na tela de cores; botão "Restaurar padrão".
- A tela de abertura não simula mais ~5,5 s de carregamento.
- Busca abre as pastas automaticamente para mostrar os resultados.
- Nome de grupo igual ao id de um equipamento não quebra mais a árvore.
- `importador.py` substituído por `tools/importar_relatorio.py` (usa o banco
  real do app e não depende mais do pandas).
- Build: sem caminho absoluto da máquina do desenvolvedor; UPX desligado.
- 37 testes automatizados.
