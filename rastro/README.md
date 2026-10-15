# rastro/

Scripts do "rastro do dinheiro". Brutos ficam em `rastro/brutos/` (fora do git); saídas em `rastro/dados/`.

## Base CNPJ da Receita (`cnpj.py`)

Lê só os CNPJs que aparecem em `fornecedores_pj` de `rastro/dados/contas/<sq>.json` e grava
`rastro/dados/fornecedores.json`:

```json
{"fonte": ["<URLs dos ZIPs>"], "data_base": "AAAA-MM-01", "gerado_em": "...",
 "fornecedores": {"<cnpj>": {"razao", "abertura", "situacao", "cnae", "mei", "simples",
                             "endereco_chave", "socios": [{"nome", "cpf_mascarado"}]}}}
```

Uso: `python3 -m rastro.cnpj --baixar [--mes AAAA-MM]`. Sem `--mes`, usa o mês mais recente que aparece na listagem da
Receita. Sem `--baixar`, só processa ZIPs já presentes em `rastro/brutos/cnpj/<AAAA-MM>/` (`--mes` obrigatório, sem rede).
**Nunca rodar perto de 25/10** (trava no dia da apuração, antes de qualquer rede).

### Caminho verificado: WebDAV público da Receita

- **Origem:** compartilhamento Nextcloud do SERPRO, via WebDAV: `https://arquivos.receitafederal.gov.br/public.php/webdav/<AAAA-MM>/`,
  autenticação básica com usuário `YggdBLfdninEJX9` (o token do compartilhamento, público por desenho) e senha vazia. A URL
  `index.php/s/.../download` devolve HTML, não o ZIP. Em 13/10 havia as pastas de 2026-06 a 2026-09.
- **Como baixa:** `PROPFIND` (Depth 1) lista meses e tamanhos (`getcontentlength`); os 31 ZIPs (`Estabelecimentos0-9`,
  `Empresas0-9`, `Socios0-9`, `Simples`) vêm **um a um**, nessa ordem: baixa em `<arq>.zip.part`, confere o tamanho e o `PK`,
  processa em streaming, apaga, e só então o próximo. Falta de arquivo na listagem aborta antes de baixar.
- **Espaço:** 7,8 GB baixados em sequência, mas o pico no disco é o do maior arquivo (cerca de 2,2 GB). O script exige
  2× o maior livre (cerca de 4,5 GB) antes de começar e aborta sem nenhum GET se não houver.
- **Tempo:** depende da banda; algo como 15 a 60 minutos para 7,8 GB a 20–80 Mbit/s, mais o processamento.
- **Retomada:** corte de conexão é retentado até 3 vezes com `Range`; se o processo morrer, rodar de novo continua do `.part`.
  Erro HTTP (inclusive 401 de token trocado: ajuste `TOKEN` em `cnpj.py`) não é retentado.
- **Plano B (b):** se a Receita sair do ar, BrasilAPI `/api/cnpj/v1/{cnpj}` com cache em `rastro/brutos/cnpj_api/<cnpj>.json` e
  `time.sleep(1)` entre chamadas; seria um leitor novo no lugar de `ler_zip`, com a mesma saída.

### LGPD

`cpf_mascarado` só guarda o que a Receita já publica mascarado (`***123456**`). CPF inteiro, em qualquer campo, nunca é
gravado (nome e razão passam por `contas.limpar_texto`); sócio PJ fica sem CPF. `tests/test_rastro_cnpj.py` varre o JSON
inteiro atrás de CPF válido.

## Indicadores da Receita, parte 1 (`indicadores.py`)

Funções puras, uma por indicador, no contrato `{nome, fato, valor, fonte_url, contraparte?}`:
`mei_acima_teto`, `empresa_recem_aberta`, `atividade_incompativel` e `socio_doador`. `gerar()` lê
`dados/contas/`, `dados/fornecedores.json`, `dados/base/agregados.json` e `brutos/doadores_hash.json` e grava
`dados/indicadores.json` (`{"fonte", "data_base", "gerado_em", "indicadores": {"<sq>": [...]}}`). Sem o arquivo de hash,
só o `socio_doador` é pulado (aviso no log). Uso: `python3 rastro/indicadores.py`.

- **Limiares em `config.json`**: teto do MEI (R$ 81.000, LC 123/2006 art. 18-A §1º, redação da LC 155/2016; conferir se
  há lei nova), início da campanha (2026-08-16) e janela de "recém-aberta" (365 dias; dispara com abertura depois de
  início − 365 dias, inclusive CNPJ aberto depois do início).
- **LGPD**: CNPJ de MEI sai mascarado (`**.***.***/0001-**`); sócio de MEI não entra no `socio_doador`. O `socio_doador` só
  casa quando nome normalizado **e** os 6 dígitos do meio do CPF batem; o `fato` traz o nome, campanhas e total, termina
  com "pode ser homônimo" e nunca o trecho do CPF nem o hash.
- **Revisar `cnae_x_tipo.json`**: `{tipo de despesa (DS_ORIGEM_DESPESA): [prefixos de CNAE compatíveis]}`. O indicador só
  dispara se todos os tipos do fornecedor estão na tabela e nenhum é compatível com o CNAE; qualquer tipo fora da tabela ou
  CNAE ausente cala. Para cortar falso positivo, acrescente prefixos; para cobrir mais tipos, acrescente chaves. Revisão humana
  obrigatória antes de ir ao site.

## Indicadores da Receita, parte 2 (`indicadores.py`, `candidatos.py`)

Mais cinco indicadores no mesmo contrato: `socio_ligado`, `multicampanha`, `situacao_irregular`, `concentracao` e
`endereco_compartilhado`. Todos os limiares e listas ficam em `config.json`.

**Ordem de execução:** `python3 rastro/baixar.py` → `python3 rastro/candidatos.py` → `python3 rastro/indicadores.py`
(depois de `contas.py` e `cnpj.py`). O `candidatos.py` lê `consulta_cand_2026.zip` (titulares e suplentes) e grava
`rastro/brutos/candidatos.json` (`{sq: {nome, uf, cargo, cpf_meio|None}}`), **fora do git**, porque tem o trecho do CPF.
Sem esse arquivo o `socio_ligado` inteiro é pulado (aviso no log); `gerar()` aceita `candidatos_path=`.

- `socio_ligado`: dois ramos. (1) o sócio consta como candidato/suplente em 2026 (nome normalizado **e** 6 dígitos do meio
  do CPF iguais, candidato diferente do pagador; candidato sem CPF no arquivo não casa só por nome). (2) o sócio tem o
  **mesmo sobrenome** do candidato pagador; o `fato` diz "mesmo sobrenome", nunca "parente". Sócio de MEI fica de fora.
  O ramo "cargo comissionado / nomeação política" está na seção Nomeações, abaixo.
- `multicampanha`: fornecedor em `n_campanhas >= multicampanha_min` (agregados). `valor` = `n_campanhas`.
- `situacao_irregular`: situação cadastral em `situacoes_irregulares` (BAIXADA, INAPTA, SUSPENSA, NULA).
- `concentracao`: fornecedor acima de `concentracao_pct` % de `despesas.total_contratado` (contratado, não pago: a parcial
  tem muita despesa ainda não paga). Total 0 ou nulo cala. `valor` = o percentual.
- `endereco_compartilhado`: `endereco_min_fornecedores` ou mais fornecedores da **mesma campanha** com o mesmo
  `endereco_chave`; um item para cada, citando os outros. O endereço não sai (o de MEI pode ser a casa da pessoa).

Chaves novas do `config.json`: `multicampanha_min` (5), `concentracao_pct` (50), `endereco_min_fornecedores` (2),
`situacoes_irregulares`, `sobrenome_particulas` e `sobrenomes_comuns` (incluem agnomes: JUNIOR, FILHO, NETO, SOBRINHO).
Os valores 5, 50 e 2 são palpites: ajuste conforme o que a primeira rodada mostrar. Sobrenome = todo token depois do
prenome, sem partículas e sem os comuns; basta um em comum. Fato de sobrenome é textual e **não** prova relação.

## Nomeações (`nomeacoes.py`) e o ramo `socio_ligado` do indicador

`python3 rastro/nomeacoes.py` baixa o cadastro de servidores federais (SIAPE) do Portal da Transparência para o mês de
`nomeacoes_mes` em `config.json` (cache `.lastmod` em `rastro/brutos/nomeacoes/`; nunca em 25/10), lê o ZIP em streaming
e grava `rastro/brutos/nomeados.json` (fora do git): `{"fonte", "data_base", "gerado_em", "nomeados": [{"nome", "cpf_meio",
"funcao", "orgao", "base"}]}`. Só entra quem tem função ou cargo comissionado: `SIGLA_FUNCAO` começando por um dos prefixos de
`nomeacoes_funcoes` (`DAS`, `FCPE`, `CCE`, `FCE`, `NES`; revisáveis, cada um com nota). Servidor efetivo sem função não entra.
As URLs ficam em `nomeacoes_fontes` (`siape` com `{mes}` = AAAAMM; `camara` e `senado` em `null`).

- **Regra de casamento** (`indicadores.socio_nomeado`, emite `nome: "socio_ligado"`): nome normalizado **e** os 6 dígitos
  visíveis do CPF mascarado (`***.123.456-**` no Portal, `***123456**` na Receita). Homônimos com trechos diferentes não
  casam; sócio de MEI fica fora; o `fato` termina com "pode ser homônimo" e o trecho nunca vai para a saída. Sem
  `rastro/brutos/nomeados.json`, `indicadores.gerar()` pula o ramo com aviso no log.
- **LGPD**: CPF inteiro na base é descartado com aviso; CPF vazio é descartado e contado no log.
- **Câmara e Senado**: `ler_externa()` aceita um mapeamento de colunas, mas ignora a base inteira (com aviso) se ela não tiver
  coluna de CPF mascarado. Pelo que se sabe, esses dados abertos trazem nome, cargo e lotação, sem CPF; por isso as URLs
  estão `null`. Casar só pelo nome contraria a regra acima: seria outra issue.

### Resultado do spike (não verificado por script: o executor não tem rede)

- URL de download esperada: `https://portaldatransparencia.gov.br/download-de-dados/servidores/AAAAMM` (ZIP com
  `AAAAMM_Cadastro.csv`, `AAAAMM_Remuneracao.csv` etc.). Só o cadastro é lido.
- **Conferir na VPS** antes da primeira rodada: (1) o mês mais recente publicado (`nomeacoes_mes`); (2) o cabeçalho de
  `*_Cadastro.csv` (`;`, latin-1, aspas): o leitor usa `NOME`, `CPF`, `SIGLA_FUNCAO` e `ORG_LOTACAO`; (3) o formato do CPF
  (`***.123.456-**`); (4) o valor de `SIGLA_FUNCAO` sem função (`-1` ou vazio) e a lista real de siglas, para ajustar os
  prefixos; (5) se o endpoint exige o cabeçalho `User-Agent` do repo (já enviado por `baixar.py`) ou devolve página HTML.

## Páginas (`paginas.py`): home, eleito, fornecedor, correções e lote 1

`python3 build_site.py` gera `site/rastro/`: a home `/rastro/`, `/rastro/metodologia/`, uma página por `sq` de `publicados.json`
(`/rastro/<cargo>/<uf>/<slug>/`) e uma por fornecedor PJ que aparece nas contas desses eleitos (`/rastro/fornecedor/<id>/`).
Nunca toda a base: fornecedor de eleito não publicado não gera página.

- **Id do fornecedor** (`id_fornecedor`): empresa = os 14 dígitos do CNPJ; MEI (ou sem cadastro na Receita, tratado como MEI) =
  `hmac-sha256(sal, cnpj)[:16]`. O sal é `rastro/.sal` (fora do git), só **lido** no build, nunca criado; sem ele e com MEI
  publicado, o build falha. **Guarde um backup do `.sal`**: se ele se perder, os links de MEI mudam.
- **O que a página do fornecedor mostra**: situação, abertura, CNAE, Simples/MEI, campanhas publicadas que o pagaram (valor
  contratado) e os indicadores em que ele é a contraparte (com "pode ser homônimo" nos de `HOMONIMO`). Sócios só pelo nome e só de PJ;
  em MEI, nem sócio nem razão social (só o CNPJ mascarado). Nunca `cpf_mascarado` nem `endereco_chave`.
- **Home**: total contratado por cargo, top `home_top_n` fornecedores, eleitos publicados (quem não tem contas aparece como
  "sem prestação parcial publicada", sem "R$ 0") e indicadores mais frequentes.
- **Correções** (`rastro/correcoes.json`): `{fonte, data_base, gerado_em, correcoes: [{path, data, o_que_mudou, fonte_url?}]}`,
  com `path` igual à rota publicada (ex.: `/rastro/depfed/ma/fulano/`). A página ganha a seção "Correções" com a data e o texto.
  `path` inexistente, texto com CPF válido ou termo proibido (`varrer`) derrubam o build: nada é publicado em silêncio.
- **Varredura**: toda página (home, fornecedores e correções incluídos) passa por `varrer` antes de qualquer gravação.
- **Lote 1** (`lote1.py`, uso único): lê `dados/eleitos.json` e `dados/indicadores.json`, ordena por cargo, votos (desc.) e nº de
  indicadores (desc.), e grava os `lote_tamanho` (20) primeiros em `publicados.json`. Sem `dados/fornecedores.json` ou
  `dados/indicadores.json` ele não grava nada. A fila e os lotes diários (Issue 9b) podem substituí-lo.

## Eleições anteriores (`anteriores.py`)

Cruza os fornecedores PJ de 2026 (`dados/base/agregados.json`) com as despesas **contratadas** das campanhas de 2022 (geral) e
2024 (municipal), do mesmo pacote de prestação de contas do TSE de cada ano (`baixar.url_contas(ano)`). Os anos ficam em
`config.json` (`anteriores_anos`). Grava `dados/anteriores.json`: `fonte`, `data_base`, `gerado_em`, `anos` e, por CNPJ e ano,
`n_campanhas` (SQ_CANDIDATO distintos) e `total_contratado`.

```
python3 -m rastro.anteriores --baixar   # baixa um ano por vez, processa e apaga o ZIP
python3 -m rastro.anteriores            # com os ZIPs já em rastro/brutos/
```

- **Tamanho**: os ZIPs são grandes (o municipal de 2024 deve ter alguns GB; não verificado). `--baixar` faz um `HEAD`, exige 2x o
  tamanho livre em disco e apaga o ZIP depois do ano processado. Padrão de `baixar.py` sem `--anteriores` continua só 2026.
- **Trava de data**: em 25/10 o `--baixar` aborta antes de qualquer requisição (mesmo IP de saída do agregador).
- **Valores**: vazio, `#NULO` e lixo nunca viram 0; a linha é contada como inválida e vai para o log. Despesa repetida
  (mesmo `SQ_DESPESA` na mesma campanha) conta uma vez. ZIP ausente vira aviso e o ano fica fora de `anos`.
- **LGPD**: só entram CNPJs de 14 dígitos que são fornecedores de 2026; fornecedor PF é descartado e nenhum nome é gravado.
  MEI continua só com o CNPJ mascarado na página.
- **Na página** do fornecedor: seção "Em eleições anteriores" (campanhas e contratado por ano, com link do pacote). Se o
  fornecedor aparece em todos os anos configurados, a página registra "contratado por campanhas em 2022, 2024 e 2026". O arquivo é
  opcional: sem ele, a seção não aparece.
- **Ressalva**: o mesmo CNPJ não garante a mesma atividade nem o mesmo dono; a empresa pode ter mudado de mãos.
- O arquivo real é gerado à mão na VPS depois do merge, nunca em 25/10.

## Fila e lotes diários

- `rastro/fila.py` grava `rastro/fila.json`: lista JSON de `sq` na ordem cargo, votos (desc), nº de indicadores (desc), a mesma do
  lote 1. Inclui os já publicados; quem filtra é `publicados.json`. Sai com 1 se faltarem `eleitos.json` ou `indicadores.json`.
- `rastro/lote.py` (`--dry-run` só imprime): move os próximos `lote_diario_tamanho` (15) `sq` ainda não publicados para
  `publicados.json`, cria a branch `rastro/lote-AAAA-MM-DD` a partir de `origin/main`, roda `build_site.py`, commita só
  `publicados.json`, `fila.json` e `site/` (o build também muda `sitemap.xml` e `llms.txt`; assim a árvore termina limpa), roda
  `python3 -m pytest -q` sobre o conteúdo exato do lote, dá push e abre o PR "Rastro: lote AAAA-MM-DD".
- **Merge automático, condicionado aos testes**: com o pytest verde, o próprio `lote.py` faz `gh pr merge --squash --delete-branch`
  (o merge no `main` é a publicação: a Vercel publica a cada push). Com o pytest vermelho (LGPD, redação, isolamento em
  `tests/test_rastro_publicado.py` e o resto), o PR fica aberto com o label **`bloqueado`**, sem merge, e o lote sai com 1.
  Enquanto houver PR de lote aberto com `bloqueado`, os lotes seguintes não rodam: o lote reprovado pede conserto humano e não é
  empilhado nem duplicado. Recusa também árvore suja e branch do dia já existente.
- **Trava**: de `trava_inicio` a `trava_fim` (23 a 26/10/2026, inclusive, em `config.json`) o `lote.py` sai com código 2 antes de
  qualquer comando. A trava está no Python, então vale também para quem rodar à mão e para o workflow.
- **Workflow** `.github/workflows/rastro-lote.yml` (substitui o antigo `cron_lote.sh`): todo dia às 12:00 UTC (09:00 BRT) e por
  `workflow_dispatch` (input `dry_run`, que roda `lote.py --dry-run`). Nenhum passo do YAML faz merge: o merge só existe no
  `lote.py`, depois do pytest. Pré-requisitos, feitos uma vez pelo Vitor:
  - secret `RASTRO_SAL` com o conteúdo de `rastro/.sal` (da máquina que gerou os ids publicados): `gh secret set RASTRO_SAL < rastro/.sal`.
    Sem ele o workflow falha antes de tudo (sem o sal os ids de MEI mudariam);
  - vars `GA_ID` e `CLARITY_ID` (Settings → Secrets and variables → Actions → Variables), senão o build sai sem medição;
  - label `bloqueado` no repo (`gh label create bloqueado`);
  - Settings → Actions → General → "Allow GitHub Actions to create and approve pull requests" ligado.
- Os indicadores que não puderam ser calculados (fonte fora do ar, arquivo de `brutos/` ausente) ficam em `avisos` no
  `dados/indicadores.json` e aparecem numa nota da metodologia.
