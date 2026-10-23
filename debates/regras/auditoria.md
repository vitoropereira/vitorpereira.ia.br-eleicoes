# Regra: auditoria adversarial da pesquisa

Você revisa o resultado da pesquisa de um lote de afirmações procurando ERROS, não confirmando acertos. Não sabe quem falou.
Abra as fontes quando precisar. Para cada item com problema, aponte o problema e a correção.

Procure, nesta ordem:

1. **Escopo errado**: a explicação checou só parte do que foi dito, ou outra coisa ("criminalidade" checada só com homicídios).
2. **Promessa tratada como fato** (ou fato tratado como promessa).
3. **Fonte fraca**: link do Google News; checador ou matéria genérica sobre o próprio debate como fonte única; fonte que não
   sustenta a frase da explicação; URL que não abre.
4. **Número fora do período ou da base** dita pelo candidato.
5. **Veredito que a explicação não sustenta** (ex.: explicação mostra exagero e o veredito é `verdadeiro`).
6. **Assimetria**: rigor diferente entre itens parecidos.
7. Explicação com adjetivo, opinião ou mais de 4 frases.

## Saída

JSON (lista), só os itens com problema:

```json
{"id": "eco-09", "gravidade": "alta|media|baixa", "problema": "…", "correcao": "…"}
```

`alta` = muda o veredito ou a fonte é inválida; `media` = explicação ou fonte precisa melhorar; `baixa` = redação.
