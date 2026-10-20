# Debates: transcrição e afirmações checáveis

Cada debate vira uma pasta com três arquivos. O formato é o mesmo para qualquer cargo, turno e emissora, e o
validador (`debates/validar.py`) e o teste (`tests/test_debates.py`) cobrem todas as pastas.

```
debates/<ano>/<cargo>-<turno>-turno-<emissora>/
├── debate.json       metadados e candidatos
├── transcricao.md    transcrição integral, sem correção
└── afirmacoes.json   afirmações checáveis extraídas (sem veredito)
```

Exemplo: `debates/2026/presidente-2-turno-band/`. A emissora entra no slug em minúsculas, sem acento e com hífen
no lugar de espaço (`TV Gazeta` → `tv-gazeta`).

## Passo a passo para um debate novo

### 1. Transcrição

Uma das três fontes (vai em `fonte_transcricao`):

- `youtube-auto`: legenda automática do YouTube.
  `yt-dlp --write-auto-subs --sub-langs pt --skip-download <url>`
- `whisper`: transcrição do áudio com Whisper.
- `colado`: texto colado de outra fonte.

Formato do `transcricao.md`:

- Cabeçalho livre (tabela com emissora, data, fonte). Nome não confirmado leva `[NÃO VERIFICADO]`.
- Uma seção `## Bloco N …` para cada bloco (`## Bloco 1 — Pergunta 1: segurança pública`) e
  `## Considerações finais`. Abertura, intervalos e encerramento ficam em seções com outro nome: o que está nelas
  não entra na extração.
- Uma marcação por linha: `**H:MM:SS** — texto` (ou `**M:SS** — texto` antes de uma hora).
- **Não corrigir a legenda.** O erro fica (ex.: "Vocário" = Vorcaro). A correção vai na `afirmacao`.

### 2. `debate.json`

```json
{
  "slug": "presidente-2-turno-band",
  "ano": 2026,
  "cargo": "presidente",
  "turno": 2,
  "emissora": "Band",
  "data": "2026-10-18",
  "fonte_transcricao": "youtube-auto",
  "candidatos": [
    {"id": "flavio-bolsonaro-pl", "nome_urna": "Flávio Bolsonaro", "partido": "PL", "id_tse": "280002551544"},
    {"id": "lula-pt", "nome_urna": "Lula", "partido": "PT", "id_tse": "280002542548"}
  ]
}
```

- Obrigatórios: `slug`, `ano`, `cargo`, `turno`, `emissora`, `data` (AAAA-MM-DD), `fonte_transcricao`, `candidatos`.
- `slug` tem que ser `<cargo>-<turno>-turno-<emissora>`, e a pasta tem que ser `<ano>/<slug>`.
- Opcionais: `parceiros`, `url_fonte`, `mediadores` (só com nome confirmado em fonte) e `id_tse` do candidato
  (o `sqcand` do TSE, só se estiver numa fonte do repo, como `relatorio/dados/`).
- **`id` do candidato é estável entre debates**: nome de urna + partido, em slug (`lula-pt`). O mesmo candidato
  usa o mesmo `id` no debate da Band, da Globo e de qualquer outro.

### 3. Extração (`afirmacoes.json`)

Uma lista de objetos:

```json
{"id": "seg-02", "bloco": "1", "tema": "seguranca", "quem": "mediacao", "autoria": "certa", "timestamp": "4:41",
 "tipo": "dado", "tese": "mortes-violentas-40775-ano-passado",
 "trecho": "40.775 775 mortes violentas no ano passado, segundo o anuário brasileiro de segurança pública",
 "afirmacao": "Houve 40.775 mortes violentas no ano passado, segundo o Anuário Brasileiro de Segurança Pública."}
```

| Campo | Valor |
|---|---|
| `id` | `<prefixo do tema>-NN` (`seg-01`). Não muda depois de publicado. |
| `bloco` | `1`, `2`, `3` ou `finais`. Tem que bater com a seção do `timestamp`. |
| `tema` | `seguranca` (seg), `economia` (eco), `social` (soc), `saude` (sau), `internacional` (int), `corrupcao-acusacoes` (cor), `outros` (out) |
| `quem` | `id` de um candidato do `debate.json`, ou `mediacao` |
| `autoria` | `certa` ou `incerta` (ver abaixo) |
| `timestamp` | uma marcação que existe na transcrição |
| `tipo` | `dado` (número), `fato`, `promessa`, `acusacao` |
| `tese` | slug curto da ideia, sem o nome de quem fala (`vorcaro-134-milhoes-filme`) |
| `trecho` | cópia **literal** da transcrição, com o erro da legenda, a partir do `timestamp` (pode seguir pelas 3 marcações seguintes) |
| `afirmacao` | a mesma frase limpa e checável |

**O que entra:** número, dado, fato verificável, votação, "eu fiz X", promessa e acusação. **Opinião não entra**
("ele é o pior presidente"). Número dito pela mediação entra com `quem: mediacao`.

**`tese`:** a mesma ideia tem a mesma `tese`, no mesmo debate e entre debates (quem repete o número dos
"134 milhões" na Globo reaproveita `vorcaro-134-milhoes-filme`). Antes de criar uma tese nova, procure:
`grep -rh '"tese"' debates/*/*/afirmacoes.json`.

**Sem veredito:** `veredito`, `selo`, `checagem`, `verdadeiro` e `falso` não entram como chave. A checagem é outra etapa.

**Simetria:** o mesmo critério de corte e de autoria vale para todos os candidatos. A saída do validador mostra a
contagem por `quem×tipo` e `quem×autoria` para conferir.

### 4. Autoria incerta

Leia o trecho em volta do `timestamp`: de quem é a palavra (pergunta, resposta, réplica, tréplica) e onde há
interjeição cruzada.

- `certa`: o turno de fala e o conteúdo não deixam dúvida.
- `incerta`: fala sobreposta, ou trecho que poderia ser de qualquer um.

Item `incerta` não é apagado nem reescrito: fica marcado e vira **uma** issue `pergunta-vitor` por debate, com id,
timestamp, trecho literal, afirmação e as opções (cada candidato / descartar). Enquanto não houver resposta,
ele fica fora da página e do placar.

### 5. Validar

```
python3 debates/validar.py debates/<ano>/<slug>
python3 -m pytest -q tests/test_debates.py
```

O validador sai com 1 e lista os erros, ou sai com 0 e imprime as contagens. O teste exige pelo menos uma
afirmação de cada candidato e da mediação, e os blocos `1`, `2`, `3` e `finais`.

### 6. Checar e publicar

A checagem fica em `checagens.json`, ao lado de `afirmacoes.json`: uma lista com exatamente um item por afirmação
`certa` checada. Item `incerta` não se checa.

```json
{
  "id": "eco-08",
  "veredito": "verdadeiro",
  "explicacao": "Pelo IBGE, o PIB cresceu 7,5% em 2010. Aos Fatos e Lupa chegaram ao mesmo número.",
  "fontes": [{"url": "https://sidra.ibge.gov.br/tabela/5932", "titulo": "Tabela 5932", "orgao": "IBGE",
              "data_publicacao": "2026-04-01", "acessado_em": "2026-10-20"}],
  "atualizado_em": "2026-10-20"
}
```

- `id`: o mesmo da afirmação.
- `veredito`: da escala do `tipo` da afirmação:
  - `dado`/`fato`: `verdadeiro`, `verdadeiro-com-ressalva`, `exagerado`, `falso`, `sem-evidencia`, `nao-checavel`;
  - `promessa`: `ja-existe`, `viavel`, `depende-do-congresso`, `sem-custo-estimado`, `inviavel`;
  - `acusacao`: `ha-investigacao`, `ha-denuncia`, `ha-condenacao`, `sem-registro-publico`.
- `explicacao`: de 2 a 4 frases, sem adjetivo, com o valor oficial e o período exato de cada número.
- `fontes`: pelo menos uma, com os cinco campos e `url` `https://`. Em `sem-evidencia` e `nao-checavel`, a fonte é o
  que foi consultado e não confirmou. Órgão oficial primeiro; reportagem não é fonte única quando ele existe.
  Em série de dados (SGS, SIDRA, FMI), `data_publicacao` é o início do período mais recente usado.
- `atualizado_em` e `acessado_em`: AAAA-MM-DD, nunca depois de hoje; `acessado_em` também não pode ser antes da
  data do debate (o teste dos debates publicados confere).
  `data_publicacao` aceita também AAAA ou AAAA-MM, para publicação que só informa o ano (o Anuário do FBSP).
- `outro_lado` (opcional): nota da defesa, em `acusacao`, quando existir.

Sem fonte encontrada é `sem-evidencia`, nunca inferência; as duas campanhas e a mediação passam pelo mesmo critério.
Em `acusacao`, a escala registra só o estado processual público. Acusação de conduta política, que não é crime nem
tem processo, fica `sem-registro-publico`, e a `explicacao` diz o que está documentado.
`python3 debates/validar.py <pasta>` também valida o `checagens.json` quando ele existe e imprime `quem×veredito`,
para conferir que o critério foi o mesmo para cada lado.

O selo e a página do debate são da #90.
