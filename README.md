# Jira Obsidian Sync

Serviço em Python que monitora um quadro Kanban do Obsidian e sincroniza com o Jira as mudanças de status das issues. A integração com a API Jira fica isolada em `jira_client.py`; o monitoramento do Markdown e a execução como serviço Windows ficam em módulos separados.

> **Direção da sincronização:** movimentações feitas no Obsidian atualizam o Jira. Com `JIRA_PULL_INTERVAL_SECONDS > 0`, o serviço também consulta o Jira periodicamente e move/adiciona cartões no board (Jira → Obsidian). Ver [Sincronização Jira → Obsidian](#sincronização-jira--obsidian).

## Funcionalidades

- Monitora alterações no arquivo `Kanban.md` do vault.
- Interpreta títulos de coluna (`##`) como status de destino.
- Identifica a issue Jira pela chave no cartão, por exemplo `PROJ-123`.
- Consulta as transições disponíveis para a issue e executa uma transição válida para o status da coluna.
- Ignora issues que já estão no status desejado.
- Registra falhas no log sem interromper a sincronização dos demais cartões.
- Pode rodar em primeiro plano para teste ou como serviço do Windows.

## Estrutura esperada

```text
jira_obsidian_sync/
├── jira_client.py       # Cliente e operações da API Jira
├── kanban_format.py     # Formato do board: parse, edição e render do Markdown
├── board_state.py       # Estado/lock compartilhado entre as duas direções
├── board_sync.py        # Obsidian → Jira: monitoramento do arquivo
├── kanban_pull.py       # Jira → Obsidian: consulta periódica e reconciliação
├── task_comments.py     # Comentários da transição: notas da task ou texto digitado
├── markdown_adf.py      # Conversão Markdown → ADF (formato de comentário da API v3)
├── comment_dialog.py    # Janela Tk para digitar comentário (processo separado)
├── install_startup.bat      # Atalho na pasta Inicializar: inicia no logon, sem Administrador
├── uninstall_startup.bat    # Remove o atalho e encerra a instância em execução
├── instance_lock.py         # Lock de instância única (service.lock)
├── install_logon_task.bat   # Registra o sincronizador no logon (Administrador)
├── uninstall_logon_task.bat # Encerra e remove a tarefa de logon
├── config.py            # Leitura e validação do .env (JiraSettings, SyncSettings)
├── service.py           # Composição e execução em foreground (também no logon)
├── windows_service.py   # Hospedagem como serviço Windows (pywin32, sem janela)
├── check_connection.py  # Teste de autenticação/transições, sem alterar nada
├── tests/               # Testes unitários (unittest)
├── .pylintrc            # Regras do pylint do projeto
├── requirements.txt
├── .env.example
├── .env                 # Configuração local; não versionar
├── install_service.bat      # Instala e inicia o serviço Windows (Administrador)
├── uninstall_service.bat    # Para e remove o serviço Windows (Administrador)
└── service.log           # Gerado durante a execução
```

O board deve estar em um arquivo Markdown, por exemplo:

```markdown
---
kanban-plugin: board
---

## To Do

- [[Squad/PFN/PROJ-123/Task|PROJ-123 — Exemplo de tarefa]]

## In Progress

## Done
```

Os nomes das colunas devem corresponder aos nomes dos status de destino disponíveis no workflow Jira. Cada cartão precisa conter uma chave Jira válida, como `PROJ-123`.

## Requisitos

- Python 3.11 ou superior no Windows (os regex usam quantificadores possessivos).
- Conta Jira com permissão para visualizar issues e executar as transições necessárias.
- Token de API Jira armazenado localmente em `.env`.
- Acesso de leitura ao vault e permissão de escrita no diretório do projeto para o log.
- Para instalar/gerenciar o serviço Windows, executar o terminal como Administrador.

## Configuração

1. Copie `.env.example` para `.env`.
2. Preencha a URL, o e-mail e o token de API do Jira.
3. Informe o caminho absoluto do arquivo `Kanban.md`.
4. Não versione `.env` nem inclua o token em logs.

Exemplo:

```dotenv
JIRA_BASE_URL=https://empresa.atlassian.net
JIRA_EMAIL=usuario@empresa.com
JIRA_API_TOKEN=seu-token
OBSIDIAN_BOARD_FILE=C:\Users\usuario\Documents\Obsidian\vault\Squad\PROJETO\Kanban.md
JIRA_VERIFY_TLS=true
LOG_LEVEL=INFO
```

## Instalação e execução para teste

Abra um terminal na pasta do projeto:

```powershell
py -3 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Configure o `.env` e execute em primeiro plano:

```powershell
python service.py
```

Faça uma alteração de status em uma issue de teste, movendo seu cartão para a coluna correspondente. Verifique o resultado no Jira e em `service.log`.

## Instalação e desinstalação

Depois de validar a execução em primeiro plano, escolha **um** modo. Cada instalador recusa se outro modo já estiver instalado. Além disso, o próprio serviço obtém um lock exclusivo em `service.lock` ao iniciar: uma segunda instância, de qualquer origem, registra o erro no log e sai com código 1, sem consultar o Jira.

| Modo | Janela de comentário | Instalar | Desinstalar | Administrador |
|---|---|---|---|---|
| Pasta Inicializar (recomendado) | Sim | `install_startup.bat`: cria `JiraObsidianSync.lnk` em `shell:startup`, que abre o `pythonw` com o `service.py` no logon | `uninstall_startup.bat`: remove o atalho e encerra a instância em execução | Não |
| Tarefa de logon | Sim | `install_logon_task.bat` e depois `schtasks /Run /TN JiraObsidianSync` | `uninstall_logon_task.bat` | **Sim**: `schtasks /SC ONLOGON` responde "Acesso negado" num terminal comum (verificado) |
| Serviço Windows | Não (sessão 0) | `install_service.bat` (cria o `.venv`, instala as dependências, registra com início automático e inicia) | `uninstall_service.bat` | Obrigatório; os scripts verificam antes de agir |

A desinstalação:

- encerra o processo em execução e remove o atalho, a tarefa ou o serviço;
- usa apenas ferramentas do Windows (`schtasks`, `sc`, PowerShell), então funciona mesmo com o `.venv` ausente ou quebrado;
- no modo pasta Inicializar, encerra **qualquer** processo cuja linha de comando tenha o `.venv` desta pasta e o `service.py`. Isso inclui o redirecionador do venv e o interpretador base, que ele abre como filho;
- **mantém** `.venv`, `.env` e `service.log`. Apague-os manualmente se não precisar mais;
- é segura para rodar de novo: sem nada instalado, informa e sai com código 0.

Gerenciamento do serviço Windows, na pasta do projeto:

```powershell
.venv\Scripts\python.exe windows_service.py start
.venv\Scripts\python.exe windows_service.py stop
.venv\Scripts\python.exe windows_service.py restart
```

A conta que executa o serviço precisa de acesso ao vault e à pasta onde `service.log` é gravado. Para diagnosticar problemas, execute primeiro `python service.py` em primeiro plano e consulte o log.

## Como a sincronização funciona

1. O monitor observa o diretório do arquivo configurado.
2. Quando `Kanban.md` muda, aguarda o intervalo de debounce e lê o conteúdo.
3. O parser associa cada cartão à coluna em que aparece.
4. Para cada chave detectada, consulta o status atual e as transições permitidas no Jira.
5. Se o destino for alcançável por uma única transição, solicita a mudança ao Jira.
6. Se não for alcançável, houver ambiguidade ou a transição exigir campos obrigatórios não configurados, registra o erro. Não escolhe uma transição arbitrariamente.

## Sincronização Jira → Obsidian

Ativada por `JIRA_PULL_INTERVAL_SECONDS` (0 desativa). Requer `JIRA_PROJECT_KEY`; `JIRA_USERS` (separados por `;`) e `JIRA_JQL_EXTRA` são opcionais.

1. A cada intervalo, consulta `(project = X AND statusCategory != Done AND assignee in (...) AND (extra)) OR key in (<cartões do board>)`. Os cartões já presentes são incluídos para acompanhá-los mesmo depois de concluídos ou reatribuídos.
2. Cartão em coluna diferente do status atual é movido para o fim dos cartões da coluna certa, levando junto as linhas de continuação.
3. Issue do filtro ainda ausente no board é adicionada como `- [ ] CHAVE — resumo · tipo · @responsável`.
4. Status sem coluna correspondente (ex.: `CANCELADO`) não altera o cartão; é registrado um aviso uma vez por issue/status.
5. Front matter, texto livre, cartões sem chave, configurações do plugin e o estilo de quebra de linha (CRLF/LF) são preservados. A gravação é atômica (`.tmp` + `os.replace`).

**Conflitos.** As duas direções compartilham um lock e o último conteúdo do board sabidamente consistente com o Jira (`BoardState`):

- O Jira prevalece. Ao iniciar, o serviço aplica primeiro o estado do Jira e só depois começa a monitorar o arquivo, para não reenviar um board desatualizado. Se essa consulta inicial falhar, o serviço não inicia.
- Se o arquivo tem alteração local ainda não enviada (por exemplo, dentro do debounce), a rodada de consulta é adiada.
- Se o arquivo muda entre a leitura e a gravação, a gravação é cancelada e refeita na próxima rodada.
- O envio Obsidian → Jira só transiciona cartões que mudaram de coluna desde o último estado consistente. Na primeira execução sem consulta ao Jira, envia todos, como antes.
- Se o Jira recusar uma transição, a próxima consulta devolve o cartão à coluna do status real.

Janela residual: uma gravação do Obsidian entre a verificação final e o `os.replace` (microssegundos) seria sobrescrita. Não há trava de arquivo entre processos; rode uma única instância do serviço.

## Comentários na transição

Quando um cartão movido no Obsidian **efetivamente** transiciona a issue (não ocorre se ela já estava no status, nem se o Jira recusou):

1. Procura a pasta da task em `<pasta do board>/<projeto identificado>/<CHAVE>/`. Com o board em `vault/Squad/SQD01/Kanban.md`, por exemplo `vault/Squad/SQD01/PFN/SQD01-342/`. A mesma chave em dois projetos é tratada como erro, e nenhum comentário é publicado.
2. **Com notas** (`*.md` não vazios, só no primeiro nível da pasta): cada nota vira um comentário, na ordem de criação do arquivo. Cada comentário gerado guarda numa *entity property* invisível (`obsidian-sync`) o nome do arquivo e o SHA-256 do conteúdo:
   - nota sem comentário (ou cujo comentário foi apagado): cria;
   - nota editada (hash diferente): **atualiza** o mesmo comentário;
   - nota sem mudança: nada.
   Comentários feitos à mão não são tocados.
3. **Sem notas:** abre uma janela para digitar um comentário em Markdown. "Mover sem comentário", fechar a janela, texto vazio ou 10 minutos sem resposta: a transição permanece, sem comentário.

Falha ao comentar não desfaz a transição; o erro vai para o log.

### Por que rodar no logon, e não como serviço Windows

Serviços Windows rodam na sessão 0, sem acesso à área de trabalho do usuário (Session 0 Isolation), então nenhuma janela aberta por eles aparece para você. Para ter a janela, rode o sincronizador na sua sessão: use a **tarefa de logon** (ver [Instalação e desinstalação](#instalação-e-desinstalação)), que roda `pythonw`, sem console.

O modo serviço (`windows_service.py install`) continua funcionando, sem a janela: sem notas, a transição acontece sem comentário e isso fica registrado no log.

## Limitações e considerações

- Conversor Markdown → ADF cobre o subconjunto usual das notas (títulos, listas aninhadas, código, citações, ênfases, links, wikilinks). Tabelas vão como bloco de código; imagens/embeds como texto. Ênfase ambígua com delimitadores colados (`***x***`, `**a *b***`) não segue o CommonMark. Bloco de código dentro de item de lista vira texto do item.
- O Jira limita o tamanho do comentário (cerca de 32 mil caracteres). Notas maiores falham com erro no log.
- Enquanto a janela de comentário está aberta, a consulta Jira → Obsidian espera, porque o lock do board fica ocupado.

- Sem `JIRA_PULL_INTERVAL_SECONDS`, a sincronização é apenas **Obsidian → Jira**.
- O Jira → Obsidian não remove cartões nem renomeia resumos já existentes.
- O workflow pode não permitir ir diretamente do status atual para o destino escolhido. Nesse caso, o Jira recusará a movimentação ou o serviço informará os destinos disponíveis.
- Campos obrigatórios em telas de transição precisam ser implementados explicitamente para o workflow da instância; o serviço não preenche valores por conta própria.
- Boards com títulos que não correspondem aos status Jira precisam de uma configuração de mapeamento antes do uso.
- O monitor pode receber eventos duplicados do sistema de arquivos. O serviço evita operações redundantes ao conferir o status atual da issue.
- Teste primeiro em um projeto Jira sandbox e com issues não produtivas.

## Segurança

- Mantenha `.env` fora do controle de versão e limite suas permissões no Windows.
- Use uma conta de serviço Jira com o menor conjunto de permissões necessário.
- Mantenha `JIRA_VERIFY_TLS=true`; não desative a validação TLS em produção.
- Não registre tokens ou cabeçalhos de autenticação nos logs.

## Testes

Testes unitários, sem acesso ao Jira:

```powershell
.venv\Scripts\python -m unittest discover -s tests -t .
```

### Qualidade

Ferramentas fora do `.venv` do projeto (não fazem parte do `requirements.txt`): `pip install pylint coverage pysonar`.

```powershell
pylint --rcfile=.pylintrc *.py tests\*.py
$env:PYTHONPATH = ".;.venv\Lib\site-packages"
coverage run --branch --source=. --omit="tests/*,.venv/*,windows_service.py" -m unittest discover -s tests -t .
coverage xml -o coverage.xml
pysonar --sonar-host-url http://localhost:9000 --sonar-project-key jira-obsidian-sync --sonar-sources . --sonar-tests tests `
  "-Dsonar.exclusions=tests/**,.venv/**" "-Dsonar.coverage.exclusions=windows_service.py" `
  "-Dsonar.python.coverage.reportPaths=coverage.xml" "-Dsonar.scm.disabled=true"
```

O `pysonar` lê o token de `SONAR_TOKEN`. `windows_service.py` fica fora da cobertura porque só executa dentro do gerenciador de serviços do Windows; a janela Tk (`comment_dialog.main`) também não é coberta, porque precisa de tela.

Antes de produção, valide também manualmente:

- Cartão movido para uma coluna com transição Jira permitida.
- Cartão já no status de destino.
- Transição indisponível no workflow.
- Chave Jira ausente ou malformada no cartão.
- Cartão duplicado em mais de uma coluna.
- Campos obrigatórios na transição.
- Reinício do serviço e alteração do board enquanto o serviço está parado.

## Dependências

As dependências Python estão listadas em `requirements.txt`. `pywin32` é necessário para instalação/execução como serviço no Windows; para teste em foreground, execute `python service.py`.

## Licença

Defina a licença de acordo com as políticas da sua organização antes de distribuir o projeto.

## Manutenção

A integração Jira está concentrada em `jira_client.py`. O formato do board fica em `kanban_format.py` e é usado pelas duas direções. `board_sync.py` cuida de Obsidian → Jira, `kanban_pull.py` de Jira → Obsidian (que depende só do protocolo `IssueSource`, não do cliente concreto), `config.py` lê o `.env`, `service.py` compõe tudo e controla o ciclo de vida, e `windows_service.py` só adapta o ciclo de vida ao pywin32. Preserve essa separação ao adicionar suporte a campos de transição ou mapeamentos de status.