# Lados dos partidos

Posição em **08/10/2026** (2026) e **2º turno de 2022**. Arquivos: `lados-2026.json`, `lados-2022.json`.

## Critério

- **L** = apoia Lula · **F** = apoia Flávio Bolsonaro (em 2022: Jair Bolsonaro) · **C** = sem lado declarado, neutro ou liberou.
- Só conta prova: nota oficial do partido, coligação registrada no TSE, imprensa reconhecida ou declaração pública
  do presidente nacional/estadual do partido.
- Sem prova = **C**. Nunca se deduz lado pela ideologia.
- Apoio pessoal de candidato ou político (ex.: Caiado, Cury, Clariana Barão) **não** muda o lado do partido.
- Coligação do 1º turno vale como prova para o 2º turno, enquanto o partido não disser outra coisa.
- Federação: os membros têm o lado da federação, salvo declaração própria com prova.
- Declaração nacional define o lado do Brasil; diretório estadual cria override só para a UF (`"uf": {"SC": "F"}`).
- Provas em conflito: vale a mais recente, e as duas ficam listadas.
- Cada prova tem `tipo`, `url`, `data`, `titulo` e um `trecho` (até 15 palavras, copiado da página).
- Exceção por UF exige ao menos uma prova com `url` e `data` marcada com a UF (`"uf": "PB"` ou lista).
  Sem prova verificada da UF, a exceção sai (o partido fica no lado nacional).

## 2022

Siglas de 2022. `mapa_siglas_2026` liga cada sigla de 2026 às de 2022
(ex.: PRD = PTB + PATRIOTA; SOLIDARIEDADE = SOLIDARIEDADE + PROS; PODE = PODE + PSC;
DEMOCRATA = PMB; MOBILIZA = PMN; MISSÃO não existia). Fontes da fusão/renomeação em `fontes_mapa`.

## Como atualizar

1. Edite o JSON: troque `lado`, adicione a prova (com link que abre e trecho que está na página),
   atualize `obs` e `posicao_em`.
2. `python3 -m unittest tests.test_lados -v`
3. Rode de novo `python3 analise/calcular.py` para refazer as análises.

## Pendências na data

- MDB: 17 diretórios acertaram apoio a Flávio, ato formal previsto para 13/10. Só os 6 citados pela imprensa
  (SP, MG, RJ, PR, RS, SC) estão como override. Revisar depois do ato.
- PCO decide em Conferência Nacional. Solidariedade/PRD, Avante e DC sem nota do partido até 08/10.
- Removidas em 08/10 por falta de prova verificável: PSD-SC (carta do presidente estadual não encontrada) e
  PSDB-RS (nota do diretório não encontrada).
