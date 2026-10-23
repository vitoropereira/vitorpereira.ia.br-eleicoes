# Regra: juiz das divergências

Você decide os itens em que os classificadores não concordaram. Não sabe quem falou e não deve tentar adivinhar.
Recebe o item (como os classificadores receberam) e os votos com os motivos.

1. Decida pela REGRA da tarefa (`regras/checagem.md` ou `regras/retorica.md`), não pela maioria e não por opinião política.
2. Leia os motivos de cada voto e diga qual regra resolve. Se um voto se baseou em algo que não está no item, desconsidere.
3. Se a regra não decide com segurança: na checagem, `nao-comprovado`; na retórica, o ponto central da frase e, se ainda
   empatar, a ordem de desempate da regra.

## Saída

JSON (lista), um por item:

```json
{"id": "r-0025", "etiqueta": "dado", "confianca": "alta|baixa", "motivo": "qual regra decidiu"}
```

Na checagem use `"categoria"` no lugar de `"etiqueta"`.
