# Rastro do dinheiro: para onde foi a grana das campanhas dos eleitos · Design

Data: 2026-10-12. O desenho foi aprovado pelo Vitor na conversa, com os ajustes dele já incorporados.

## Objetivo

O site ganha uma aba nova, **"Rastro do dinheiro"**. Ela mostra, para cada eleito em 2026:
- de onde veio o dinheiro da campanha;
- para quem ele foi pago;
- quais fornecedores disparam **indicadores** de atenção. São cruzamentos com a base de CNPJ da Receita e com outras bases públicas.

Começa pelos cargos mais importantes e destaca os mais votados. O trabalho é feito aos poucos, em várias issues pequenas pelo dev-flow.

## Decisões

- **Mostrar tudo o que é público** (decisão do Vitor: o site é de transparência).
- **Redação neutra.**
  - Cada achado mostra o **fato**, a **regra que disparou** e o **link para o dado de origem**.
  - O site nunca escreve "fraude", "laranja" nem "empresa fictícia". Quem conclui é o leitor.
  - Toda página de indicador tem o aviso "indicador não é prova de irregularidade".
- **LGPD.**
  - O CPF de pessoa física (doador, dono de MEI, sócio) **nunca** vai para o site nem para o git. Nome e valor podem.
  - O CNPJ de MEI contém o CPF do dono, então aparece mascarado no site. Só a razão social fica visível.
- **Fonte: dados abertos em lote, não scrape.**
  - O DivulgaCandContas é uma SPA. Os mesmos dados saem em ZIP de `dadosabertos.tse.jus.br`.
  - Pacotes confirmados em 2026-10-12: `resultados-2026`, `candidatos-2026`, `prestacao-de-contas-eleitorais-2026`.
- **Dados parciais por enquanto.** A prestação de contas é parcial: base de 2026-08-18, documentos fiscais de 2026-09-22.
  - Toda página mostra a data da base usada.
  - Quando saírem as contas finais, entra a etapa de atualização (etapa 8).
- **Stack do repo:** Python 3 só com a biblioteca padrão, site estático gerado e `brand.css` como única fonte de cores e fontes. Sem tabelas no Supabase.
- **Não encosta no ao vivo do 2º turno (25/10).**
  - Nenhum arquivo do painel ao vivo, do HUD ou do agregador muda.
  - **Nenhum deploy entre 23 e 26/10.**

## Arquitetura

```
rastro/
  baixar.py        # baixa os ZIPs (TSE, Receita) para rastro/brutos/ (fora do git), com cache e User-Agent do repo
  eleitos.py       # resultados + candidatos → eleitos.json (cargo, UF, partido, votos, sq_candidato)
  contas.py        # receitas/despesas dos eleitos → contas/<sq>.json
  cnpj.py          # filtra a base CNPJ só para os fornecedores que aparecem → fornecedores.json
  indicadores.py   # regras → indicadores.json (uma função por regra, com nome estável)
  dados/           # JSON derivado, versionado (público, pequeno, sem CPF)
site/rastro/       # páginas geradas pelo build_site.py
```

- **Os brutos** (milhares de MB) ficam em `rastro/brutos/`, que entra no `.gitignore`. O processamento pesado (a base CNPJ, cerca de 6 GB zipados [NÃO VERIFICADO]) roda na VPS.
- **O JSON derivado** carrega `fonte` e `data_base` em cada arquivo.
- Cada passo é um script que lê o JSON do passo anterior e se testa com fixtures pequenas em `tests/`.

## Escopo de cargos

| Fase | Cargos |
|---|---|
| Agora (eleitos no 1º turno) | deputado federal, senador, governador eleito no 1º turno, deputado estadual/distrital |
| Depois de 25/10 | presidente e governadores do 2º turno |

Nas páginas, os mais votados de cada cargo aparecem em destaque.

## Indicadores

Cada indicador é uma função pura com nome estável e teste. Na página ele aparece como "<nome>: <fato>", seguido da fonte.

| Nome | Regra |
|---|---|
| `mei_acima_teto` | fornecedor MEI (Simples/MEI da Receita) recebeu de campanhas, somadas, mais que o teto anual do MEI |
| `empresa_recem_aberta` | CNPJ aberto **menos de 1 ano** antes de 2026-08-16 (início da campanha) |
| `atividade_incompativel` | o CNAE do fornecedor não tem relação com a descrição ou o tipo do gasto declarado. Usa uma tabela de mapeamento revisável no repo |
| `socio_doador` | um sócio do fornecedor **doou para qualquer campanha de 2026**, não precisa ser a mesma. O casamento é por nome + trecho visível do CPF mascarado da Receita |
| `socio_ligado` | um sócio do fornecedor é **candidato ou suplente em 2026**, **tem o mesmo sobrenome do candidato pagador** (marcado como "mesmo sobrenome", nunca como "parente") ou **ocupa cargo comissionado ou nomeação política** (servidores federais do Portal da Transparência e secretários parlamentares da Câmara e do Senado) |
| `multicampanha` | o mesmo CNPJ recebeu de N ou mais campanhas (N está em configuração) |
| `situacao_irregular` | a situação cadastral na Receita é baixada, inapta, suspensa ou nula |
| `concentracao` | um fornecedor recebeu mais que X% do gasto total da campanha (X está em configuração) |

**Limite declarado no site:**
- parentesco e amizade não estão em nenhuma base pública;
- "mesmo sobrenome" é um fato textual, não uma relação;
- o casamento por nome pode errar com homônimos, e a página diz isso.

## Páginas

- `/rastro/`: total por cargo, top fornecedores, mais votados com o gasto de cada um e indicadores mais frequentes.
- `/rastro/<cargo>/<uf>/<slug-eleito>/`: receitas por origem, despesas por fornecedor e os indicadores disparados.
- `/rastro/fornecedor/<id>/`: campanhas que pagaram, dados da Receita e indicadores. O `<id>` é o CNPJ para empresa e um hash para MEI.
- Toda página tem a data da base, a metodologia (link para `/rastro/metodologia/`) e o aviso de que indicador não é prova.

## Etapas (uma issue cada, com label `agente`)

1. **Eleitos 2026:** `baixar.py` + `eleitos.py` → `rastro/dados/eleitos.json`.
2. **Contas dos eleitos:** `contas.py` → `rastro/dados/contas/<sq>.json` (receitas por origem, despesas por fornecedor).
3. **Base CNPJ filtrada:** `cnpj.py` → `fornecedores.json`, só com os CNPJs que aparecem nas despesas.
4. **Indicadores 1 a 4:** `mei_acima_teto`, `empresa_recem_aberta`, `atividade_incompativel`, `socio_doador`.
5. **Indicadores 5 a 8:** `socio_ligado` (só candidato e sobrenome), `multicampanha`, `situacao_irregular`, `concentracao`.
6. **Página por eleito** + metodologia.
7. **Página por fornecedor** + home da aba.
8. **Contas finais:** rodar tudo de novo com a base final do TSE, mais presidente e governadores do 2º turno.
9. **`socio_ligado` com nomeações:** bases de servidores federais e secretários parlamentares.

## Gates do Vitor

- **Deploy público:** cada página só vai ao ar com o ok dele.
- **Nenhum deploy entre 23 e 26/10.**
- **Merge** de cada PR.

## Testes de aceite

- Cada script tem teste com fixture pequena (CSV recortado do TSE e da Receita), sem rede.
- **Teste de LGPD:**
  - **falha** se qualquer arquivo em `rastro/dados/` ou `site/rastro/` tiver um CPF completo (11 dígitos no formato de CPF válido);
  - **falha** se qualquer um deles tiver o CNPJ de um MEI sem máscara.
- **Teste de redação:** **falha** se `site/rastro/` tiver "fraude", "laranja" ou "fictícia".
- **Teste de isolamento:** `relatorio/relatorio.json`, `historico.json` e os arquivos do ao vivo não mudam.

## Fora do escopo

- Score ou ranking de "suspeição".
- Acusação ou conclusão editorial.
- Dados de anos anteriores.
