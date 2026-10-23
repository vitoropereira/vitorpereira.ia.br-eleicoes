# RUNBOOK: checar um debate novo

Passo a passo na ordem das issues da Globo: G1 → G2 → G3 → G5 → publicação. Os formatos dos arquivos estão no
[`README.md`](README.md); aqui só a ordem, os comandos e quando parar. As regras dos classificadores estão em
[`regras/`](regras/). `<pasta>` = `debates/<ano>/<cargo>-<turno>-turno-<emissora>`.

**Parar = criar `.bloqueado`** (com o motivo) e terminar, sem publicar nada. **Perguntar = listar em
`## Perguntas ao Vitor`** no PR e seguir sem aquele item.

## G1. Íntegra e transcrição

| | |
|---|---|
| Entrada | emissora, data e duração do debate |
| Saída | `<pasta>/transcricao.md` e `<pasta>/debate.json` (com `video`) |
| Comando | `yt-dlp --write-auto-subs --sub-langs pt --skip-download <url>` |
| Gate | `python3 debates/validar.py <pasta>` (só passa com G2 pronto; antes disso confira o formato pelo README, seções 1 e 2) |

- Escolha o vídeo da **íntegra do debate, nunca o do telejornal** (na Band o 1º link era do telejornal). Confira os três:
  1. canal oficial da emissora;
  2. duração ≥ 90% da duração do debate;
  3. título (debate, não corte nem jornal).
- Preencha `video` no `debate.json` com esse mesmo vídeo: os tempos só batem se for o da transcrição.
- **Parar:** não achou íntegra confiável → `.bloqueado`.

## G2. Extração (`afirmacoes.json`)

| | |
|---|---|
| Entrada | `transcricao.md`, `debate.json` |
| Saída | `<pasta>/afirmacoes.json` (sem veredito) |
| Comando | `python3 debates/validar.py <pasta>` |
| Gate | validador sem erro; `python3 -m pytest -q tests/test_debates.py` |

- Formato e autoria: README, seções 3 e 4. Não repita aqui.
- A **mediação também é extraída** (`quem: mediacao`), mas **não entra no placar**.
- Autoria `incerta` não bloqueia: o item fica fora até o Vitor responder. Liste em `## Perguntas ao Vitor`.

## G3. Pesquisa por lotes de tema

Feita **na sessão do Vitor, não pelo executor**: o executor do dev-flow não tem web (decisão de 22/10).

| | |
|---|---|
| Entrada | `afirmacoes.json` dividido em lotes de tema |
| Saída | `debates/<ano>/<slug>/pesquisa/<lote>.json` |
| Comando | a sessão segue [`regras/pesquisa.md`](regras/pesquisa.md) e depois [`regras/auditoria.md`](regras/auditoria.md); cola o JSON pronto na issue do lote |
| Gate | o executor só grava o JSON em `pesquisa/<lote>.json` e valida (`python3 -m json.tool` no arquivo, `python3 -m pytest -q`) |

- Auditoria: item de gravidade `alta` volta para a pesquisa **antes** do consenso.
- **Parar:** busca na web indisponível → `.bloqueado`. **Nunca** marcar `nao-comprovado` por falta de busca.

## G5. Retórica com consenso

| | |
|---|---|
| Entrada | `afirmacoes.json`, `transcricao.md` |
| Saída | `<pasta>/retorica.json`, sem os itens `fora` |
| Comando | procedimento cego do README, seção 8 (`debates/retorica.py cego` e `juntar`) |
| Gate | `python3 debates/validar.py <pasta>` |

- 3 etiquetadores cegos com [`regras/retorica.md`](regras/retorica.md): recebem só `cego.json` (sem `quem`).
- Onde divergirem, decide o juiz com [`regras/juiz.md`](regras/juiz.md).
- Liste em `## Perguntas ao Vitor` os itens com confiança `baixa` decididos pelo juiz.

## Publicação

| | |
|---|---|
| Entrada | `pesquisa/*.json` auditado, `afirmacoes.json`, `retorica.json` |
| Saída | `<pasta>/checagens.json` |
| Comando | `python3 debates/validar.py --estrito <pasta>`, depois `python3 build_site.py` (gera em diretório temporário no PR: quem publica o `site/` é o lote) |
| Gate | `python3 debates/validar.py --estrito <pasta>` e `python3 -m pytest -q tests/test_debates.py` sem erro |

1. Consenso dos vereditos com 2 Sonnet e 1 Haiku, cegos, usando [`regras/checagem.md`](regras/checagem.md).
2. Divergências vão para o juiz ([`regras/juiz.md`](regras/juiz.md)); `confianca: baixa` vai para `## Perguntas ao Vitor`.
3. Grave `checagens.json` (README, seção 6).
4. Valide (comando acima).
5. Confira **3 tempos no vídeo** (início, meio e fim): o trecho tem que estar no segundo indicado.
6. **Parar:** validador falha sem correção clara → `.bloqueado`.

## Checklist: erros já apontados

Confira antes de abrir o PR.

- [ ] **Escopo parcial**: "criminalidade" é crime em geral (roubo, latrocínio, homicídio, estelionato), não só homicídio.
- [ ] **Promessa tratada como fato**: o que o candidato VAI fazer nunca é `verdadeiro` nem `falso-ou-exagerado`.
- [ ] **Fonte única fraca**: checador ou matéria genérica sobre o próprio debate não basta; ache a fonte primária.
- [ ] **Link do Google News** (`news.google.`): abra e use a matéria original.
- [ ] **Vídeo errado**: íntegra do debate, não o telejornal (canal, duração ≥ 90%, título).
- [ ] **Mediação fora do placar**: extraída, mas sem entrar na contagem dos candidatos.
