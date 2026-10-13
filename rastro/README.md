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
