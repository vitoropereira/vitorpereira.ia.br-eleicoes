# Eleições 2026 · Apuração e resultados

Histórico aberto da apuração do 1º turno das Eleições Gerais de 2026 (04/10/2026). Os dados vêm dos arquivos públicos de divulgação do TSE e foram capturados e analisados ao longo da noite.

**Site:** https://eleicoes2026.vitorpereira.ia.br

| Página | O que tem |
|---|---|
| [Resultado final](https://eleicoes2026.vitorpereira.ia.br/) | presidente (com mapa por estado), governadores, Senado, Câmara, Assembleias, a noite da apuração e perguntas frequentes |
| [Ao vivo](https://eleicoes2026.vitorpereira.ia.br/ao-vivo/) | lê o TSE a cada minuto; quando o TSE publicar o 2º turno (25/10), passa a mostrá-lo |
| [Histórico da apuração](https://eleicoes2026.vitorpereira.ia.br/apuracao/) | o painel exatamente como estava em cada leitura (36,6% → 99,7%) |

## Usar os dados

Tudo está em JSON, pronto para usar:

| Arquivo | Conteúdo |
|---|---|
| [`relatorio/relatorio.json`](relatorio/relatorio.json) | resultado consolidado: presidente por UF e região, governadores, Senado, vagas de deputados por partido e os mais votados |
| [`relatorio/dados/`](relatorio/dados/) | arquivos brutos do TSE por UF e cargo (eleições 6257 e 6259), exatamente como baixados |
| [`historico.json`](historico.json) | Flávio × Lula em cada leitura da noite (% apurado, % dos válidos) |
| [`snapshots/`](snapshots/) e [`marcos/`](marcos/) | os dados de cada rodada (`dados.json`), com projeções e simulação |
| [`marcos/75pct/comparacao_fontes.json`](marcos/75pct/comparacao_fontes.json) | o episódio em que o arquivo nacional do TSE travou e a soma das UFs seguiu atualizando |

No site, o consolidado também está em `/dados/relatorio.json`.

## Rodar

Só precisa de Python 3 (sem dependências) e do Google Chrome, usado no pré-render.

```bash
python3 gerar.py                       # painel da apuração (lê o TSE, projeta, salva em snapshots/)
./watch.sh                             # vigia o % apurado e salva os marcos de 50% e 75%
cd relatorio && python3 baixar.py && python3 montar.py && cd ..   # relatório final, todos os cargos
python3 build_site.py                  # gera o site estático em site/
```

| Arquivo | Papel |
|---|---|
| `gerar.py` + `template.html` | painel da apuração (Chart.js) |
| `relatorio/montar.py` + `relatorio/template_relatorio.html` | relatório final (HTML e SVG, sem bibliotecas) |
| `template_aovivo.html` | página ao vivo, que busca o TSE no navegador |
| `build_site.py` | junta tudo, pré-renderiza com Chrome headless e gera SEO (JSON-LD, sitemap, `llms.txt`, imagens Open Graph) e as medições (GA4 e Clarity, só com consentimento de cookies) |
| `site/` | o site pronto, publicado na Vercel (`site/vercel.json` repassa `/tse/*` para o TSE) |

## Como os números são calculados

- **Total nacional = soma das UFs + exterior.** O arquivo nacional do TSE ficou travado em 64,81% por cerca de 30 minutos na noite de 04/10 enquanto os estados seguiam atualizando.
- **Projeção:** o voto que falta em cada UF segue o % já apurado daquela UF. O Monte Carlo (20 mil rodadas) soma um viés nacional ~N(+1 pt Lula, 3 pt) e ruído por UF ~N(0, 2 pt). São premissas escolhidas, não estimadas. Em todas as rodadas, o resultado final caiu dentro da faixa de 80%.
- **Eleitos:** o TSE ainda não tinha proclamado os eleitos na hora da coleta. Governador = mais de 50% dos válidos, calculado com e sem os votos de candidatos com registro anulado sub judice. Senado = os 2 mais votados. As vagas de deputados por partido ou federação são as publicadas pelo TSE; a divisão dentro das federações é estimada.
- **Pesquisas:** tabela agregada da Wikipedia, convertida para votos válidos. Os números não foram conferidos um a um nos institutos.

### Log da noite

| Hora TSE | % apurado | Flávio | Lula | Projeção final (F × L) | Flávio vence no 1º | Flávio termina na frente |
|---|---|---|---|---|---|---|
| 18:19 | 24,45 | 50,94 | 40,97 | 49,0 × 43,0 | — | — |
| 18:23 | 27,88 | 50,85 | 41,05 | 48,8 × 43,2 | 18% | 85% |
| 18:32 | 36,60 | 50,63 | 41,23 | 47,8 × 44,2 | 9% | 86% |
| 19:06 | 64,81 | 49,58 | 42,25 | 47,5 × 44,5 | 0,2% | 95,5% |
| 19:32 | 84,93 | 48,47 | 43,49 | 47,4 × 44,7 | 0,0% | 99,8% |
| 20:47 | 93,21 | 47,79 | 44,26 | 47,3 × 44,9 | 0,0% | 100% |
| 21:56 | 99,71 | 47,09 | 45,09 | 47,1 × 45,1 | — | — |
| 22:49 | 99,95 | 47,04 | 45,15 | resultado | | |

A partir das 18:32, a projeção é a mediana da simulação; nas duas primeiras leituras, é a projeção base. As leituras de 18:19 e 18:23 não têm painel salvo.

## Contribuir

Ideias, correções e novas análises são bem-vindas: veja o [CONTRIBUTING.md](CONTRIBUTING.md).

Todo PR roda o check `ci / gate` (ruff + pytest, Python 3.12). Marcá-lo como obrigatório em Settings → Branches → main é um passo manual do mantenedor.

## Licença

Código sob [MIT](LICENSE). Dados consolidados e análises sob [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.pt_BR): use à vontade, citando a fonte. Os dados brutos são públicos e pertencem ao TSE.

Projeto independente de [Vitor Onofre Pereira](https://vitorpereira.ia.br), sem vínculo com a Justiça Eleitoral.
