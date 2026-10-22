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
  O que vem antes da primeira seção de falas e a seção `## Índice` são notas internas: **não são publicados**.
  A página pública mostra no lugar uma linha gerada do `debate.json` (emissora, data, duração, vídeo).
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
- `video` (opcional): o vídeo do YouTube de onde saiu a transcrição (`https://www.youtube.com/watch?v=<id>` ou
  `https://youtu.be/<id>`). Com ele, o tempo de cada afirmação vira "▶ 9:52 no vídeo", aberto naquele segundo, além
  do link para a transcrição. Tem que ser o mesmo vídeo da transcrição, senão os tempos não batem.
- Opcionais: `parceiros`, `url_fonte`, `mediadores` (só com nome confirmado em fonte) e `id_tse` do candidato
  (o `sqcand` do TSE, só se estiver numa fonte do repo, como `relatorio/dados/`).
- `cor` do candidato (opcional): `flavio`, `lula` ou `outros` (padrão), que são as variáveis de cor de partido do
  `brand.css`. Em outra eleição são só nomes de cor: use a do campo do candidato. A mediação sai sempre em `outros`.
- `publicado_em` (opcional, AAAA-MM-DD): data de publicação da checagem no site (`datePublished`). Sem ele, vale a
  `data` do debate.
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
- `veredito`: um de cinco, para qualquer `tipo` (escala única desde 21/10/2026; a antiga, de 13 vereditos por tipo,
  complicava a leitura do placar):
  - `verdadeiro`: a afirmação central se confirma nas fontes (detalhe secundário impreciso ainda é verdadeiro);
  - `falso-ou-exagerado`: desmentida pelas fontes, ou o número central foi inflado a ponto de mudar o sentido;
  - `nao-comprovado`: não há evidência pública que confirme nem desminta, não é checável, ou é acusação sem registro;
  - `pendente-ou-condicionado`: promessa que ainda não existe e depende de Congresso, custo ou detalhamento;
  - `situacao-identificada`: a promessa já existe, ou a acusação tem investigação, denúncia ou condenação registrada.
  A afirmação é checada no sentido em que foi dita: "a criminalidade explodiu" olha o crime em geral, não só mortes.
  Promessa nunca é `verdadeiro`/`falso`. A mediação não entra no placar nem nas páginas publicadas.
- `explicacao`: de 2 a 4 frases, sem adjetivo, com o valor oficial e o período exato de cada número.
- `fontes`: pelo menos uma, com os cinco campos e `url` `https://`. Em `nao-comprovado`, a fonte é o
  que foi consultado e não confirmou. Órgão oficial primeiro; reportagem não é fonte única quando ele existe.
  Em série de dados (SGS, SIDRA, FMI), `data_publicacao` é o início do período mais recente usado.
- `atualizado_em` e `acessado_em`: AAAA-MM-DD, nunca depois de hoje; `acessado_em` também não pode ser antes da
  data do debate (o teste dos debates publicados confere).
  `data_publicacao` aceita também AAAA ou AAAA-MM, para publicação que só informa o ano (o Anuário do FBSP).
- `outro_lado` (opcional): nota da defesa, em `acusacao`, quando existir.

Sem fonte encontrada é `nao-comprovado`, nunca inferência; as duas campanhas e a mediação passam pelo mesmo critério.
Em `acusacao`, a escala registra só o estado processual público. Acusação de conduta política, que não é crime nem
tem processo, fica `nao-comprovado`, e a `explicacao` diz o que está documentado.
`python3 debates/validar.py <pasta>` também valida o `checagens.json` quando ele existe e imprime `quem×veredito`,
para conferir que o critério foi o mesmo para cada lado.

### 7. Publicar

`python3 build_site.py` publica todo `debates/<ano>/<slug>/` que tenha `checagens.json`, sem código novo por debate
(`debates/pagina.py`):

- `/debates/`: índice, do debate mais novo para o mais antigo, com o placar somado por `id` de candidato (sem a mediação);
- `/debates/<ano>/<slug>/`: placar do debate, filtro (quem, tema, veredito) e as checagens por tema;
- `/debates/<ano>/<slug>/<id>/`: uma página por checagem, com card OG próprio (`/og/debate-<ano>-<slug>-<id>.png`);
- `/debates/<ano>/<slug>/transcricao/`: a transcrição com uma âncora `t-H-MM-SS` por marcação.

Só entra afirmação `certa`. O JSON-LD traz um `ClaimReview` por checagem; `dateModified` é o maior `atualizado_em`.
Erro em qualquer arquivo para o build com o id e o campo: nada é publicado pela metade.

### 8. Retórica (`retorica.json`)

Opcional. Mostra como cada candidato argumentou: cada frase que ele disse recebe uma etiqueta. Com o arquivo, a página
do debate ganha a seção "Como cada um argumentou" (barras por candidato e a lista frase a frase, com filtro por quem e
por etiqueta), e o índice soma por candidato os debates que têm o arquivo. Sem ele, nada muda.

```json
[{"id": "r-0001", "timestamp": "0:10", "quem": "ana-silva-pa",
  "frase": "A taxa de roubos caiu pela metade em dez anos.", "etiqueta": "dado"}]
```

- **Frase**: uma sentença, até a pontuação final (`.`, `!`, `?`, `…`). Legenda sem pontuação é cortada antes de passar
  de 4 marcações. O texto é o literal da transcrição, com os erros dela. O `timestamp` é o da marcação onde a frase
  começa, e a frase tem que estar nas 4 marcações a partir dele (a mesma regra do `trecho` das afirmações).
- **`quem`**: o `id` de um candidato do `debate.json`. A mediação não entra. Trecho com autoria incerta (critério da
  seção 4) também fica de fora, sem pergunta ao Vitor.
- **`id`**: `r-NNNN`, na ordem da transcrição. O id que sai como `fora` deixa um buraco na numeração, e não tem problema.
- Não há outras chaves: nada de `autoria`, `nome` ou veredito.

Etiquetas (`etiqueta`):

| Etiqueta | Rótulo | Quando |
|---|---|---|
| `ataque-critica` | Ataques e críticas | ataca ou critica o adversário, o governo, o partido ou aliados, sem que o ponto central seja um dado (honestidade, família, competência, motivos, decisões) |
| `proposta` | Propostas | diz o que vai fazer ("vou...", "no meu governo..."), com ou sem detalhe |
| `apelo` | Apelo pessoal ou emocional | fala de si ou apela a medo, raiva, pena ou esperança, sem dado nem proposta |
| `dado` | Dados e evidências | o ponto central é número, data ou fato verificável, certo ou errado (se confere é a checagem que diz) |

Escala de 4 desde 21/10/2026 (a antiga tinha 6: ataque à pessoa e crítica sem prova viraram `ataque-critica`; emoção e
fala de si viraram `apelo`).
**Desempate**: vale o ponto central da frase; se ainda empatar, a primeira desta ordem: dado, proposta,
ataque-critica, apelo (`validar.ETIQUETAS`).
**Etiquetagem**: vários modelos de IA, cada um sem saber quem falou, etiquetam a mesma frase; onde divergem, um
desempate pela regra decide.
**Não entram**: cumprimentos, "obrigado", pedidos de tempo, perguntas e respostas sobre regra (etiqueta `fora`, que
`juntar` descarta).

Procedimento cego com `debates/retorica.py`. Quem etiqueta não pode saber quem falou:

1. Monte `falas.json` lendo a transcrição: `[{"inicio": "H:MM:SS", "fim": "H:MM:SS", "quem": id, "autoria": "certa"}]`,
   um trecho por vez de fala, com início e fim sendo marcações (o fim conta). Use as afirmações já atribuídas como
   âncora e marque `incerta` onde a fala cruza.
2. `python3 debates/retorica.py cego <pasta> falas.json > cego.json` gera `[{id, frase}]`, sem `quem`, nome ou partido.
3. O etiquetador (IA) recebe **só** `cego.json` e esta seção, nunca `falas.json` nem `debate.json`, e devolve
   `etiquetas.json` = `{id: etiqueta ou "fora"}` com todos os ids.
4. `python3 debates/retorica.py juntar <pasta> falas.json etiquetas.json` grava `<pasta>/retorica.json`. Ele recusa id
   desconhecido, id faltando e etiqueta fora da lista.
5. `python3 debates/validar.py <pasta>` valida o arquivo e imprime `quem×etiqueta`.

`falas.json`, `cego.json` e `etiquetas.json` são intermediários e não são versionados.
Os percentuais de cada candidato somam exatamente 100 (método do maior resto). O placar não é nota nem "quem ganhou".
