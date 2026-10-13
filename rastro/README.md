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

Uso: `python3 rastro/cnpj.py [--mes AAAA-MM]` (baixa com cache `.lastmod` em `rastro/brutos/cnpj/<AAAA-MM>/`; nunca em 25/10).

### Resultado do spike (consulta em 2026-10-13)

- **URL:** compartilhamento Nextcloud do SERPRO, `https://arquivos.receitafederal.gov.br/index.php/s/YggdBLfdninEJX9`
  (token público, sem login). Download por `.../download?path=/AAAA-MM&files=<arquivo>.zip`.
  A listagem antiga (`/dados/cnpj/dados_abertos_cnpj/`) dá 404.
- **Não verificado por script:** nesta consulta o ambiente de execução devolveu corpo vazio (HTTP 200, 0 bytes) tanto no
  WebDAV (`/public.php/webdav/`) quanto na página do compartilhamento, então a listagem de pastas, o token e o mês mais
  recente **precisam ser conferidos na VPS** antes da primeira rodada. Se o token mudou, ajuste `BASE_CNPJ` e `MES_PADRAO`
  em `cnpj.py`.
- **Escolha: (a)**, base inteira em streaming (`Empresas0-9`, `Estabelecimentos0-9`, `Socios0-9`, `Simples`), filtrando
  pelo conjunto de CNPJs-alvo. Motivo: é GET simples sem captcha, a API pública (opção b, 1 req/s) levaria horas para
  dezenas de milhares de CNPJs e traria sócios sem a mesma máscara. Custo: cerca de 6 GB de ZIPs por mês de referência
  (a VPS tem cerca de 30 GB); apague `rastro/brutos/cnpj/<mês anterior>/` depois de gerar.
- **Plano B (b):** se (a) falhar, BrasilAPI `/api/cnpj/v1/{cnpj}` com cache em `rastro/brutos/cnpj_api/<cnpj>.json` e
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
  O ramo "cargo comissionado / nomeação política" é da Issue 11.
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
