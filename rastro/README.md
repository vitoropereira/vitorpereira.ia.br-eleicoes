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
