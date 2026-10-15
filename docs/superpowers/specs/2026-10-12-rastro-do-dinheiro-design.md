# Rastro do dinheiro: para onde foi a grana das campanhas dos eleitos · Design

Data: 2026-10-12. O desenho foi aprovado pelo Vitor na conversa, com os ajustes dele já incorporados.
Revisão 1 (2026-10-12): entram 6 indicadores que saíram de um exercício de "como um candidato desviaria o fundo".
O desenho original pegava bem a empresa nova e esquisita, mas quase não via a empresa normal com preço inflado
nem os pagamentos a pessoa física.
Revisão 2 (2026-10-12): entram mais 3 indicadores (sobras, nota fiscal, endereço), o bloco de contestação, a publicação em
lotes diários e a etapa 12 (eleições anteriores).
Revisão 3 (2026-10-14): os lotes diários saem por um workflow agendado do GitHub Actions, sem gate humano. O merge é automático
e condicionado aos testes (LGPD, redação, isolamento sobre as páginas reais); se algum falhar, o PR fica aberto com o label
`bloqueado` e nada é publicado.
Revisão 4 (2026-10-15): a página do eleito ganha o caminho do dinheiro em diagrama e fica mais enxuta. Detalhes na seção
"Revisão 4 (2026-10-15)", no fim.

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
  - Quando saírem as contas finais, entra a etapa de atualização (etapa 10).
  - Os prazos de entrega das contas finais são **3/11** para o 1º turno e **14/11** para quem foi ao 2º
    [VERIFICADO: TRE-SP, notícia de out/2026].
- **Stack do repo:** Python 3 só com a biblioteca padrão, site estático gerado e `brand.css` como única fonte de cores e fontes. Sem tabelas no Supabase.
- **Não encosta no ao vivo do 2º turno (25/10).**
  - Nenhum arquivo do painel ao vivo, do HUD ou do agregador muda.
  - **Nenhum deploy entre 23 e 26/10.**

## Arquitetura

```
rastro/
  baixar.py        # baixa os ZIPs (TSE, Receita) para rastro/brutos/ (fora do git), com cache e User-Agent do repo
  eleitos.py       # resultados + candidatos → eleitos.json (cargo, UF, partido, votos, sq_candidato)
  contas.py        # receitas/despesas/extratos de TODOS os candidatos → contas/<sq>.json (eleitos) + base/ (agregados de comparação)
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

**Base de comparação: todos os candidatos.** Os não eleitos entram no processamento, mas não ganham página. Sem eles:
- não existe a curva de preço (`preco_fora_da_curva`, `gasto_por_voto`);
- não aparece a candidata de votação ínfima que recebeu repasse do eleito (`transferencia_candidato`).

Um não eleito só aparece no site **como contraparte de um indicador de um eleito**, com nome e valor.

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
| `preco_fora_da_curva` | o valor pago num tipo de gasto (impressão, combustível, locação, produção de vídeo…) está acima do percentil 95 das campanhas do mesmo cargo e UF, proporcional ao eleitorado da UF |
| `gasto_por_voto` | o custo por voto do eleito está acima do percentil 95 do cargo/UF |
| `pessoal_pf` | pagamentos a pessoa física fora do padrão: muitos CPFs, os mesmos CPFs pagos por várias campanhas, valores redondos e altos. **O site mostra só a contagem e o total, nunca nome ou CPF de pessoa física paga** |
| `saque_especie` | saque ou pagamento em espécie no extrato bancário da campanha (pacote "Extratos Bancários de Candidatos") |
| `transferencia_candidato` | o eleito repassou dinheiro para outro candidato que gastou com os mesmos fornecedores dele. O destaque vai para quem recebeu o repasse e teve votação ínfima, por exemplo candidaturas da cota de gênero |
| `sobra_sem_destino` | o que entrou menos o que saiu dá saldo positivo, e não há devolução registrada ao Tesouro (sobra de FEFC) nem à conta do partido (Fundo Partidário e outros recursos). **Só com as contas finais** (etapa 10) |
| `nota_fiscal_suspeita` | o fornecedor emitiu para a campanha notas com numeração sequencial (sinal de que ela é o único cliente), ou a nota tem data anterior à abertura do CNPJ ou posterior à eleição. Fonte: pacote "Documentos fiscais de despesa" |
| `endereco_compartilhado` | dois ou mais fornecedores da mesma campanha têm o mesmo endereço na Receita. O endereço do candidato não é público, então não entra |
| `pagamento_tardio` | pagamento depois do dia da eleição (2026-10-04) ou mais de X% do gasto nos últimos 7 dias antes dela |

Os percentis e limiares ficam em configuração (`rastro/config.json`), com o valor usado escrito na página.
O CPF de pessoa física é usado **só dentro do processamento**, para contar e casar. Ele não sai em nenhum JSON versionado: o agregado leva só a contagem e um hash com sal local, que não vai para o git.

**Limite declarado no site:**
- parentesco e amizade não estão em nenhuma base pública;
- "mesmo sobrenome" é um fato textual, não uma relação;
- o casamento por nome pode errar com homônimos, e a página diz isso.

## Páginas

- `/rastro/`: total por cargo, top fornecedores, mais votados com o gasto de cada um e indicadores mais frequentes.
- `/rastro/<cargo>/<uf>/<slug-eleito>/`: receitas por origem, despesas por fornecedor e os indicadores disparados.
- `/rastro/fornecedor/<id>/`: campanhas que pagaram, dados da Receita e indicadores. O `<id>` é o CNPJ para empresa e um hash para MEI.
- Toda página tem a data da base, a metodologia (link para `/rastro/metodologia/`) e o aviso de que indicador não é prova.
- **Contestar este dado.** Toda página tem um bloco com o e-mail de contato.
  - Uma correção aceita fica registrada na própria página, com a data e o que mudou.
  - O registro vem de `rastro/correcoes.json`, que é versionado e entra pelo PR.

## Publicação em lotes

**O processamento e os indicadores rodam para todos os candidatos.** É um lote só, e a curva de comparação depende disso.

**O que é gradual é a página detalhada**, porque a revisão humana (falso positivo, homônimo, contexto) é o custo real.

- **Prioridade:** cargo (governador > senador > deputado federal > deputado estadual/distrital), depois votos e depois o número de indicadores disparados. A ordem fica em `rastro/fila.json`.
- **Lote 1:** os 20 primeiros da fila. Ele serve para calibrar limiares e redação antes de escalar.
- **Lotes seguintes:**
  - um workflow diário do GitHub Actions (`.github/workflows/rastro-lote.yml`) gera as páginas dos próximos N da fila, com N em `rastro/config.json` e padrão de 10 a 15;
  - cada lote abre **um PR** e roda `python3 -m pytest -q` sobre o conteúdo exato do lote: com os testes verdes o merge é automático e é a publicação; com algum vermelho o PR fica aberto com o label `bloqueado`, sem merge, e os lotes seguintes esperam o conserto (Revisão 3);
  - os lotes param entre 23 e 26/10 (trava no `rastro/lote.py`).
- **Eleito sem lote publicado:** aparece na home só como linha da tabela (nome, cargo, gasto total, número de indicadores), sem página.

## Etapas (uma issue cada, com label `agente`)

1. **Eleitos 2026:** `baixar.py` + `eleitos.py` → `rastro/dados/eleitos.json`.
2. **Contas dos eleitos:** `contas.py` → `rastro/dados/contas/<sq>.json` (receitas por origem, despesas por fornecedor).
3. **Base CNPJ filtrada:** `cnpj.py` → `fornecedores.json`, só com os CNPJs que aparecem nas despesas.
4. **Indicadores da Receita, parte 1:** `mei_acima_teto`, `empresa_recem_aberta`, `atividade_incompativel`, `socio_doador`.
5. **Indicadores da Receita, parte 2:** `socio_ligado` (só candidato e sobrenome), `multicampanha`, `situacao_irregular`, `concentracao`.
6. **Indicadores de comparação:** `preco_fora_da_curva`, `gasto_por_voto`, `transferencia_candidato`.
7. **Indicadores de pessoal e extrato:** `pessoal_pf`, `saque_especie`, `pagamento_tardio`.
8. **Página por eleito** + metodologia.
9. **Página por fornecedor** + home da aba + contestação, com o lote 1 publicado.
9b. **Cron de lotes:** a fila mais o PR diário com os próximos N.
10. **Contas finais** (depois de 3/11): rodar tudo de novo com a base final do TSE, mais `sobra_sem_destino` e `nota_fiscal_suspeita`
    com os documentos finais. Presidente e governadores do 2º turno entram depois de 14/11.
11. **`socio_ligado` com nomeações:** bases de servidores federais e secretários parlamentares.
12. **Eleições anteriores (2022/2024):** fornecedor que recebe de campanhas em todas as eleições. Usa os mesmos pacotes do TSE de outros anos.

## Gates do Vitor

- **Deploy público:** cada página só vai ao ar com o ok dele.
- **Nenhum deploy entre 23 e 26/10.**
- **Merge** de cada PR.

## Testes de aceite

- Cada script tem teste com fixture pequena (CSV recortado do TSE e da Receita), sem rede.
- **Teste de LGPD:**
  - **falha** se qualquer arquivo em `rastro/dados/` ou `site/rastro/` tiver um CPF completo (11 dígitos no formato de CPF válido);
  - **falha** se qualquer um deles tiver o CNPJ de um MEI sem máscara;
  - **falha** se o nome de uma pessoa física paga (recebedora de despesa) aparecer em `site/rastro/`.
- **Teste de redação:** **falha** se `site/rastro/` tiver "fraude", "laranja" ou "fictícia".
- **Teste de isolamento:** `relatorio/relatorio.json`, `historico.json` e os arquivos do ao vivo não mudam.

## Fora do escopo

- Score ou ranking de "suspeição".
- Acusação ou conclusão editorial.
- Verificar automaticamente se o serviço foi prestado (fotos, contratos). Fica para a contestação e a apuração manual.

## Revisão 4 (2026-10-15)

**Feedback do Vitor:** a página do eleito é uma parede de tabelas. Falta ver de relance de onde veio o dinheiro e para onde
foi, e o aviso e a contestação ocupam mais espaço que os dados.

A revisão sai em quatro issues:

- **A (esta):** o caminho do dinheiro em diagrama e a página enxuta.
- **B:** destaques de indício no topo da página.
- **C:** busca de eleito e de fornecedor.
- **D:** rede de fornecedores entre campanhas (reaproveita `rastro/diagramas.py`).

Os 5 itens da issue A:

1. **Diagrama Sankey** em SVG estático, gerado no build em Python puro (`rastro/diagramas.py`), na ordem
   origem → campanha → tipo de gasto → fornecedor.
   - Origem: doador PJ com 2% ou mais das receitas tem nó próprio; o resto vira "Outros doadores"; pessoas físicas, recursos
     próprios e "Outros" vêm de `por_origem`; no máximo 6 nós.
   - Tipo de gasto: o fornecedor entra inteiro no seu tipo principal (o de maior valor em `por_tipo`), porque a base não
     divide o total do fornecedor por tipo. "Pessoas físicas (N pagas)" é só agregado, sem nome. O que entrou e não foi
     contratado vira "Ainda não gasto / não declarado", em cinza; o contratado além do recebido vira um nó cinza na origem.
   - Fornecedor: os 10 maiores e, por tipo, "Mais N fornecedores". MEI e fornecedor sem cadastro saem só com o CNPJ mascarado.
     Fornecedor com indicador tem marcador `var(--amber)` e link para a linha dele na tabela.
   - O fluxo fecha em cada nó (tolerância de R$ 0,01). O SVG tem `role="img"`, `<title>`, frase-resumo em `<desc>` e
     nenhuma cor literal. Abaixo dele, a limitação: a base não liga cada receita a cada despesa.
2. **Topo com uma linha de resumo:** "Recebeu R$ X · Contratou R$ Y · N fornecedores · K indicadores".
3. **Aviso curto** numa linha, com link para a metodologia, onde fica o texto completo.
4. **Rodapé único** com a base de dados, as fontes e "Contestar este dado" compacto.
5. **Tabelas dentro de `<details>`**, fechadas, com o total no `<summary>`.

Em 390px só o bloco do diagrama rola na horizontal; a página não. As páginas de fornecedor, a home e a metodologia
continuam com o aviso e a contestação completos.
