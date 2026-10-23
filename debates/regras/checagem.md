# Regra: veredito simplificado das checagens (5 categorias)

Você classifica uma afirmação feita num debate presidencial (Brasil, 2026). Decida SÓ pela evidência que está na
explicação e nas fontes. Não use opinião política, não use
o que "todo mundo sabe", não adivinhe. Você não sabe quem falou e não deve tentar adivinhar.

Categorias (use o id exato):

- `verdadeiro` — a afirmação central se confirma nas fontes. Detalhe secundário impreciso (um número arredondado,
  uma data aproximada) ainda é verdadeiro.
- `falso-ou-exagerado` — a afirmação central é desmentida pelas fontes, OU o número/escala central foi inflado ou
  distorcido a ponto de mudar o sentido.
- `nao-comprovado` — não há evidência pública que confirme nem desminta; ou a frase não é checável; ou é uma acusação
  sem registro público (sem investigação, denúncia ou condenação).
- `pendente-ou-condicionado` — PROMESSA que ainda não existe e depende de algo: aprovação do Congresso, custo não
  estimado, detalhamento que não foi dado, ou é viável mas não feita.
- `situacao-identificada` — há um fato institucional registrado que corresponde ao que foi dito: a promessa JÁ EXISTE
  (política ou lei em vigor), ou a acusação tem investigação, denúncia ou condenação registrada.

Cuidados (obrigatórios):

1. Classifique a AFIRMAÇÃO COMO FOI DITA, no sentido amplo dela. Se o candidato diz "a criminalidade explodiu", a
   pergunta é sobre crime em geral (roubos, latrocínio, homicídios, estelionato...), não só mortes. Se a explicação
   checou só uma parte e isso muda o resultado, marque `checou_coisa_certa: false` e diga o que faltou.
2. Promessa (o que o candidato diz que VAI fazer) nunca é `verdadeiro`/`falso`: é `pendente-ou-condicionado` ou
   `situacao-identificada` (já existe). Exceção: promessa impossível pela lei vigente sem mudança → `pendente-ou-condicionado`.
3. Acusação a uma pessoa: `situacao-identificada` só se houver registro (investigação/denúncia/condenação, mesmo que
   depois arquivada — diga isso no motivo); sem registro → `nao-comprovado`; desmentida por fonte → `falso-ou-exagerado`.
4. Se a explicação não sustenta nenhuma categoria com segurança, escolha a mais conservadora (`nao-comprovado`) e
   explique.
5. "Confiança": `alta` quando a evidência citada decide; `baixa` quando depende de interpretação.
