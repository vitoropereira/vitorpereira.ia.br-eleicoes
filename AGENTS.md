# eleicoes-2026: o específico deste repo

Pilha **pessoal** do Vitor (conta GitHub `vitoropereira`). Não é Pixel.
Repo **público**: nada de segredo em commit.

## Stack
- Python 3 só com a biblioteca padrão; Chrome headless para pré-render e imagens OG.
- Site estático em `site/`, publicado na Vercel (`build_site.py` gera tudo).
- **PR não commita `site/`.** Quem regenera e publica o `site/` é o lote (`rastro-lote.yml`), que tem o sal do Rastro
  (`RASTRO_SAL`); fora dele o build do `site/rastro/` não sai certo. No PR: mude o código e os testes; para conferir a
  saída, gere num diretório temporário (ou rode o build e depois `git checkout -- site`). Teste que lê HTML gerado
  monta o site em tmp, nunca depende do `site/` commitado estar atualizado.
- Visual: `brand.css` é a única fonte de cores e fontes (brand do vitorpereira.ia.br).

## Supabase (painel ao vivo)
- Projeto `qzczyicspbizosjogmlq` (us-east-1), conta pessoal do Vitor.
  É o mesmo projeto do vitorpereira.ia.br: crie recursos **novos**, não mexa nos existentes.
- Credenciais só no `.env` deste repo (`SUPABASE_PROJECT_REF`, `SUPABASE_TOKEN`, que é um PAT da conta inteira).
- O MCP do Supabase desta máquina está logado na org PIXEL: **não usar** para este repo.
- Sem tabelas: o estado do ao vivo é JSON no Storage (bucket `vivo`). O público lê via rewrite
  da Vercel com cache, nunca direto no Storage.
- Toda escrita/DDL e criação de recurso: mostrar o SQL/comando ao Vitor e esperar o OK.
- "Pessoas agora" (presença no Realtime, `hud/presenca.js`): usa a **publishable key** (`sb_publishable_…`), que é
  pública por desenho e fica como constante em `build_site.py` (`SUPABASE_PUBLISHABLE_KEY`), injetada no HUD como
  `window.HUD_PRESENCE`. Nunca trocar por `service_role`/`sb_secret_`: `tests/test_hud.py` barra isso.
  Só conecta com `vivo/config.json` = `{"presenca": true}` (chave geral; ver `supabase/PROPOSTA.md`, 6c).
- Ensaio geral do 2º turno, todo local: `supabase/ensaio.md`.
- Zerar em `vivo/` o estado do ensaio (24/10, nunca em 25/10 depois das 17h): `supabase/zerar-ensaio.md`.

## Comandos
- Gate (dev-flow): `python3 -m pytest -q` e `ruff check .` (config em `pyproject.toml`, só tooling)
- CI: `.github/workflows/ci.yml` (check `ci / gate`) roda o mesmo gate em todo PR e no push na main.
- Testes: `python3 -m unittest discover -s tests -v` (continua válido)
- Testes do HUD (JS): `deno test hud/`
- Testes do agregador: `cd supabase/functions/agregador-eleicoes && deno test --allow-read --allow-env .`
- Testes do simulador: `deno test --allow-read supabase/simular_test.ts`
- `supabase/simular.ts medir` bate no TSE de verdade (milhares de requisições): **nunca rodar em 25/10**, nem perto da
  noite da apuração; o agregador de produção usa o mesmo IP de saída do TSE que todo mundo.
- Resultado por seção e local de votação (presidente): `python3 municipios/baixar_secao.py && python3 municipios/montar_secao.py`
  (~340 MB do TSE; **nunca em 25/10**). Gera `municipios/geo/locais/`; seção ou local com comparecimento < 30 sai sem voto.
- Relatório: `cd relatorio && python3 montar.py && cd ..`
- Site: `python3 build_site.py`
- PR: `/ship`

## Regras
- `relatorio/relatorio.json` e `historico.json` são dados publicados: mudança visual não pode alterá-los.
- Dados usam só cores de partido; o ciano da brand é só para a moldura.
