# Rastro do dinheiro: plano de implementação

> **Para agentes:** este plano é o **roteiro das issues**. Cada seção "Issue N" vira uma issue no GitHub.
> O plano de tarefas, com o código, sai do runner do dev-flow: o planner escreve o rascunho na issue e o Vitor aprova com
> `ok vpe#N`. Na execução de cada issue, vale o que estiver nesta seção **mais** as Restrições globais.

**Objetivo:** a aba "Rastro do dinheiro" mostra, para cada eleito de 2026, de onde veio e para onde foi o dinheiro da campanha, com 17 indicadores de atenção.

**Arquitetura:** pipeline offline em Python, só com a biblioteca padrão, em `rastro/`.
- Cada script lê o JSON do passo anterior e escreve o seu em `rastro/dados/`.
- Os brutos (ZIPs do TSE e da Receita) ficam em `rastro/brutos/`, fora do git.
- O `build_site.py` gera as páginas estáticas em `site/rastro/`.

**Stack:** Python 3 (stdlib), `unittest`, site estático, `brand.css`.

**Spec:** `docs/superpowers/specs/2026-10-12-rastro-do-dinheiro-design.md` (com as revisões 1 e 2).

## Restrições globais

- Só biblioteca padrão do Python. Testes com `python3 -m unittest discover -s tests -v`, **sem rede**, com fixtures pequenas em `tests/fixtures/rastro/`.
- **LGPD:**
  - o CPF de pessoa física nunca vai para `rastro/dados/`, `site/rastro/` nem para o git;
  - o CNPJ de MEI aparece mascarado;
  - o nome de pessoa física **paga** (fornecedor PF) não aparece no site;
  - quando for preciso agregar por CPF, usar `hash(sal + cpf)`, com o sal em `rastro/.sal` (fora do git).
- **Redação:**
  - o site não escreve "fraude", "laranja" nem "fictícia";
  - todo indicador é exibido como "<nome>: <fato>" com link para a fonte;
  - toda página traz o aviso "indicador não é prova de irregularidade" e a data da base.
- **Isolamento:** não alterar `relatorio/relatorio.json`, `historico.json`, `hud/`, `supabase/`, `painel.html` nem `site/ao-vivo/`.
- **Nada de tabelas no Supabase.**
- **Rede:**
  - os downloads usam o `User-Agent` do repo (o mesmo de `municipios/baixar.py`) e cache em `rastro/brutos/`;
  - nenhum download roda em 25/10;
  - os ZIPs são lidos em streaming (`zipfile` + `io.TextIOWrapper`, latin-1, `;`), **sem extrair**. A VPS tem cerca de 30 GB livres.
- **Rastreabilidade:** todo JSON em `rastro/dados/` tem `{"fonte": [...urls], "data_base": "AAAA-MM-DD", "gerado_em": ISO}`.
- **Limiares** (percentis, N, X%) só em `rastro/config.json`, nunca fixos no código.
- **Deploy:** só com o ok do Vitor; nenhum deploy entre 23 e 26/10.

## Fatos verificados (2026-10-12)

| Fato | Fonte |
|---|---|
| Os eleitos já estão no repo: `relatorio/dados/{uf}-c{cargo:04d}.json`, campo `carg[0].agr[].par[].cand[]`, com `sqcand`, `nmu`, `vap` (votos), `e` (`"s"` = eleito) e `st` ("Eleito", "Suplente", "2º turno"…). Cargos: 3 = gov, 5 = sen, 6 = depfed, 7 = depest, 8 = distrital (DF) | arquivos versionados |
| O `consulta_cand_2026` (base de 22/07) tem `DS_SIT_TOT_TURNO` **vazio**: não serve para eleito | ZIP do TSE |
| `sqcand` dos resultados = `SQ_CANDIDATO` das contas (formato `160002546888`) | conferido no PR |
| `prestacao_de_contas_eleitorais_candidatos_2026.zip` (189 MB) traz `despesas_contratadas_*`, `despesas_pagas_*`, `receitas_*` e `receitas_*_doador_originario_*`, por UF e `_BRASIL` | ZIP do TSE |
| A base parcial tem 19.223 candidatos, cerca de 1 milhão de despesas, 55.920 CNPJs e 491.986 CPFs de fornecedores, somando R$ 4,53 bi contratados | contagem local |
| `despesa_documento_2026.zip` (5 MB): `SQ_DESPESA`, `NR_CPF_CNPJ_FORNECEDOR`, `VR_DESPESA`, `DS_URL_DOCUMENTO` | ZIP do TSE |
| `extrato_bancario_candidato_2026.zip` (8,5 MB): `NR_CNPJ_PRESTADOR_CONTA`, `DS_LANCAMENTO`, `DT_LANCAMENTO`, `TP_OPERACAO`, `VR_LANCAMENTO`, `NR_CPF_CNPJ_CONTRAPARTE` | ZIP do TSE |
| Base do CNPJ da Receita: a listagem antiga (`arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/`) dá **404**, e o site agora é um compartilhamento do SERPRO | [NÃO VERIFICADO: URL nova] → a Issue 3 começa resolvendo isso |

Colunas das despesas contratadas (as que importam): `SQ_CANDIDATO`, `DS_CARGO`, `SG_UF`, `DS_TIPO_FORNECEDOR`,
`CD_CNAE_FORNECEDOR`, `NR_CPF_CNPJ_FORNECEDOR`, `NM_FORNECEDOR`, `NM_FORNECEDOR_RFB`, `SQ_CANDIDATO_FORNECEDOR`,
`DS_ORIGEM_DESPESA`, `SQ_DESPESA`, `DT_DESPESA`, `DS_DESPESA`, `VR_DESPESA_CONTRATADA`. As pagas ligam por `SQ_DESPESA`
(`DT_PAGTO_DESPESA`, `VR_PAGTO_DESPESA`, `DS_FONTE_DESPESA`). As receitas trazem `DS_FONTE_RECEITA`, `DS_ORIGEM_RECEITA`,
`NR_CPF_CNPJ_DOADOR`, `NM_DOADOR`, `SQ_CANDIDATO_DOADOR`, `DT_RECEITA` e `VR_RECEITA`.

## Contratos entre as issues

```
rastro/dados/eleitos.json        (Issue 1)
  {fonte, data_base, gerado_em,
   eleitos: [{sq, nome_urna, cargo: "governador|senador|depfed|depest|distrital", uf, partido, votos, situacao}]}

rastro/dados/contas/<sq>.json    (Issue 2, só eleitos)
  {fonte, data_base, gerado_em, sq,
   receitas: {total, por_origem: {<DS_ORIGEM_RECEITA>: valor}, por_fonte: {<DS_FONTE_RECEITA>: valor},
              doadores_pj: [{cnpj, nome, valor}], doadores_pf: {qtd, total}},
   despesas: {total_contratado, total_pago,
              fornecedores_pj: [{cnpj, nome, cnae, valor, n_despesas, tipos: [DS_ORIGEM_DESPESA]}],
              fornecedores_pf: {qtd, total, por_tipo: {...}}}}

rastro/dados/base/agregados.json (Issue 2, todos os candidatos, sem página)
  {por_cnpj: {<cnpj>: {total_recebido, n_campanhas, campanhas: [sq]}},
   por_tipo_cargo_uf: {<tipo>|<cargo>|<uf>: [valores por campanha]},
   custo_por_voto: {<cargo>|<uf>: [valores]}}
  # o eleitorado da UF vem de relatorio/dados (campo de eleitores do arquivo de presidente)

rastro/brutos/doadores_hash.json (Issue 2, fora do git; para socio_doador e pessoal_pf)

rastro/dados/fornecedores.json   (Issue 3)
  {<cnpj>: {razao, abertura, situacao, cnae, mei: bool, simples: bool, endereco_chave, socios: [{nome, cpf_mascarado}]}}

rastro/dados/indicadores.json    (Issues 4 a 7)
  {<sq>: [{nome, fato, valor, fonte_url, contraparte?}]}
  # nome ∈ os 17 nomes do spec; cada um é uma função em rastro/indicadores.py

rastro/fila.json                 (Issue 9b)
  [sq] na ordem de prioridade; rastro/publicados.json = [sq] já com página
```

## Review Focus

1. **Homônimo no casamento por nome** (`socio_doador`, `socio_ligado`): um nome comum como "JOSÉ DA SILVA" dispara falso positivo. Exigir nome + trecho visível do CPF mascarado bater, e dizer "pode ser homônimo" na página. Teste com dois homônimos que **não** devem casar.
2. **Valores em formato brasileiro** (`1.234,56`, vazio, `#NULO`): o parse precisa tratar e nunca virar 0 em silêncio. Linha inválida é contada e registrada no log. Teste com as três formas.
3. **Despesa contratada ≠ paga, e parcelas:** somar a paga pelo `SQ_DESPESA` sem duplicar parcelas (`SQ_PARCELAMENTO_DESPESA`). Teste com uma despesa em 3 parcelas.
4. **Eleito sem prestação de contas** (não entregou a parcial): a página diz "sem prestação parcial publicada" em vez de R$ 0. Teste com esse caso.
5. **CPF vazando por campo inesperado:** CPF dentro de `NM_FORNECEDOR` ou `DS_DESPESA`, ou CNPJ de MEI no nome. O teste de LGPD varre **todo** o texto gerado com uma regex de 11 dígitos + dígito verificador válido.

---

## Issue 1: Eleitos 2026 (`rastro/eleitos.py`) ← teste ponta a ponta do runner

**Objetivo:** gerar `rastro/dados/eleitos.json` a partir dos resultados que **já estão no repo**. Não baixa nada.

**Arquivos:** criar `rastro/__init__.py`, `rastro/eleitos.py`, `rastro/config.json` (vazio, `{}`), `tests/test_rastro_eleitos.py`, `tests/fixtures/rastro/` e a linha `rastro/brutos/` + `rastro/.sal` no `.gitignore`.

**Contrato:** a saída é `eleitos.json` (ver Contratos). Lê `relatorio/dados/{uf}-c0003/5/6/7.json` e `df-c0008.json`.
- Entra quem tem `e == "s"`.
- Governador com `st` de 2º turno **não** entra; ele vem na Issue 10.

**Aceite:**
- o teste com fixture de 2 UFs gera os eleitos certos, sem não eleitos nem candidatos de 2º turno;
- rodando de verdade, a contagem bate com as vagas: depfed 513, senador 54, depest/distrital 1.059 [conferir no `nv` de cada arquivo];
- `sq` é string, e `votos` é int a partir de `vap`.

## Issue 2: Contas de todos os candidatos (`rastro/baixar.py`, `rastro/contas.py`)

**Objetivo:**
- baixar `prestacao_de_contas_eleitorais_candidatos_2026.zip`, `despesa_documento_2026.zip` e `extrato_bancario_candidato_2026.zip` para `rastro/brutos/`, com cache por `Last-Modified`;
- gerar `contas/<sq>.json` para os eleitos e `base/agregados.json` para todos.

**Contrato:** ver Contratos. Os fornecedores PF são só contagem e total. Os doadores PF viram `doadores_hash.json`, fora do git.

**Aceite:**
- os testes cobrem os itens 2, 3 e 4 do Review Focus;
- o teste de LGPD passa sobre a saída;
- `data_base` vem de `DT_GERACAO` do CSV;
- o tamanho do que é versionado fica registrado no PR. Se `rastro/dados/` passar de 30 MB, o PR propõe dividir por UF.

## Issue 3: Base CNPJ só dos fornecedores (`rastro/cnpj.py`)

**Objetivo:** gerar `fornecedores.json` para os CNPJs que aparecem nas despesas dos eleitos.

**Passo 0 (spike, no próprio PR):** achar a URL atual dos dados abertos do CNPJ (o compartilhamento do SERPRO) e decidir:
- **(a)** base inteira, lida em streaming dos ZIPs `Empresas*`, `Estabelecimentos*`, `Socios*` e `Simples*`, filtrando pelo conjunto de CNPJs;
- **(b)** se a base inteira não for acessível por script, consultar CNPJ por CNPJ numa API pública, com cache e no máximo 1 requisição/s.

Registrar a escolha e o motivo em `rastro/README.md`.

**Resultado do spike:** opção (a). URL: compartilhamento `https://arquivos.receitafederal.gov.br/index.php/s/YggdBLfdninEJX9` (download por `?path=/AAAA-MM&files=<arquivo>.zip`); a listagem não pôde ser verificada do ambiente de desenvolvimento e deve ser conferida na VPS (detalhes em `rastro/README.md`).

**Contrato de `fornecedores.json`** (envelope com metadados; as Issues 4 e 5 leem `["fornecedores"]`):
`{fonte, data_base, gerado_em, fornecedores: {<cnpj>: {razao, abertura, situacao, cnae, mei, simples, endereco_chave, socios: [{nome, cpf_mascarado}]}}}`.
`endereco_chave` = `TIPO LOGRADOURO|NUMERO|CEP` normalizado; `mei`/`simples` = optante hoje; CNPJ ausente da base entra com `situacao: null`.

**Aceite:**
- fixture com 3 CNPJs: um MEI, um baixado e um com 2 sócios;
- o `cpf_mascarado` mantém só o que a Receita já publica mascarado;
- `endereco_chave` é o endereço normalizado (logradouro + número + CEP).

## Issue 4: Indicadores da Receita, parte 1 (`rastro/indicadores.py`)

`mei_acima_teto`, `empresa_recem_aberta` (< 1 ano antes de 2026-08-16), `atividade_incompativel` (tabela `rastro/cnae_x_tipo.json`, revisável) e `socio_doador` (doador de **qualquer** campanha de 2026, casando nome + trecho do CPF).

**Aceite:**
- cada indicador tem um teste que **dispara** e um que **não dispara**;
- o `socio_doador` tem o teste de homônimo (Review Focus 1);
- o teto do MEI fica em `config.json`, com a fonte da lei anotada.

## Issue 5: Indicadores da Receita, parte 2

`socio_ligado` (sócio que é candidato/suplente em 2026 ou tem o mesmo sobrenome do candidato pagador), `multicampanha`, `situacao_irregular`, `concentracao` e `endereco_compartilhado` (2 ou mais fornecedores da mesma campanha com o mesmo `endereco_chave` da Issue 3).

**Aceite:**
- dispara e não dispara para cada um;
- o sobrenome ignora partículas (DA, DE, DOS…) e sobrenomes muito comuns (lista em `config.json`, ex.: SILVA, SANTOS, OLIVEIRA);
- o `fato` diz "mesmo sobrenome", nunca "parente".

## Issue 6: Indicadores de comparação

`preco_fora_da_curva` (percentil 95 por tipo × cargo × UF, proporcional ao eleitorado), `gasto_por_voto` e `transferencia_candidato` (repasse a outro candidato que gastou com os mesmos fornecedores; destacar o recebedor de votação ínfima).

**Aceite:**
- o percentil é calculado com `statistics.quantiles` e testado com uma lista conhecida;
- grupo com menos de 10 campanhas **não** gera indicador. O teste afirma isso.

## Issue 7: Indicadores de pessoal e extrato

`pessoal_pf` (contagem, CPFs repetidos entre campanhas pelo hash, valores redondos e altos), `saque_especie` (extrato: `DS_LANCAMENTO`/`TP_OPERACAO` de saque ou espécie) e `pagamento_tardio` (depois de 2026-10-04, ou mais de X% nos últimos 7 dias).

**Aceite:**
- o `pessoal_pf` nunca expõe nome nem CPF. O teste varre o `fato` e afirma isso;
- o extrato é casado pelo `NR_CNPJ_PRESTADOR_CONTA` da campanha.

## Issue 8: Página por eleito + metodologia

**Objetivo:** o `build_site.py` gera `site/rastro/<cargo>/<uf>/<slug>/` para os `sq` em `rastro/publicados.json`, e também `site/rastro/metodologia/`.

**Aceite:**
- o teste de redação passa (sem "fraude", "laranja" ou "fictícia");
- o teste de LGPD varre `site/rastro/`;
- o teste de isolamento mostra que os arquivos protegidos não mudaram;
- a página mostra a data da base, o aviso e o bloco "Contestar este dado";
- screenshot no PR, em desktop e celular (Chrome headless, como o repo já faz).

## Issue 9: Página por fornecedor + home da aba + contestação

**Objetivo:**
- `site/rastro/` (home);
- `site/rastro/fornecedor/<id>/`, com `<id>` = CNPJ, ou um hash para MEI;
- `rastro/correcoes.json` aplicado nas páginas;
- link da aba no menu do site.

**Lote 1:** os 20 primeiros da fila em `publicados.json`. O **PR desta issue é o primeiro deploy** e só vai ao ar com o ok do Vitor.

## Issue 9b: Cron de lotes diários

**Objetivo:**
- `rastro/fila.py` gera `fila.json`, ordenada por cargo, depois votos e depois número de indicadores;
- `rastro/lote.py` move os próximos N (de `config.json`) para `publicados.json`, regenera as páginas e abre o PR "Rastro: lote AAAA-MM-DD";
- cron na VPS, com uma trava que **não roda entre 23 e 26/10**.

**Aceite:**
- a trava de data é testada;
- o lote nunca repete um `sq` já publicado.

## Issue 10: Contas finais (depois de 3/11; 2º turno depois de 14/11)

Rodar o pipeline com a base final e ativar `sobra_sem_destino` e `nota_fiscal_suspeita`. Presidente e governadores do 2º turno entram em `eleitos.json`.

**Aceite:** dispara e não dispara para os 2 indicadores novos; o `data_base` muda nas páginas.

## Issue 11: `socio_ligado` com nomeações

Servidores federais (Portal da Transparência) e secretários parlamentares (Câmara e Senado), casando nome + trecho do CPF.

## Issue 12: Eleições anteriores (2022/2024)

Fornecedor que recebeu de campanhas em várias eleições. Usa os mesmos pacotes do TSE de outros anos.

