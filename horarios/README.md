# horarios: horário dos votos do 2º turno (25/10/2026)

Lê os logs de urna do TSE (`bu_imgbu_logjez_rdv_vscmr_2026_2t_UF.zip`) direto do CDN por HTTP Range, sem baixar o ZIP,
e grava por seção cada voto: hora (relógio local da urna), tempo na mesa, tempo na cabine, tipo de habilitação.
O log diz **quando** se votou, nunca **em quem** (voto secreto; o RDV vem embaralhado).

- `ler_logs.py` → `brutos/2t_UF.jsonl.gz` (fora do git). Pula UF pronta; retoma pela seção (lotes de 1000).
- `estatisticas.py` → `dados/estatisticas.json` (agregados). Fuso inferido pelo 1º voto (abertura 8h de Brasília).
  Cruza com `municipios/brutos_secao/votacao_secao_2026_BR.zip` (`python3 municipios/baixar_secao.py`).
- Testes: `tests/test_horarios.py`.

## Estado em 02/11/2026 (pausado: internet do Vitor caindo)

- Prontas (23): AC AL AM AP CE DF ES GO MA MS MT PA PB PE PI RN RO RR RS SC SE TO ZZ (~69 mi de votos).
- Faltam: BA (parou em 18 mil/35 mil, recomeça do zero), PR (falhou por DNS), RJ, MG, SP. ~45 mi de votos, ~2–3 h.
- Retomar: `python3 horarios/ler_logs.py` (no worktree `~/projects/eleicoes-horarios`, branch `horarios-votos`).
- Uso de rede: lê ~60–70% do tamanho dos ZIPs (SP sozinho ~25 GB). Não rodar em internet ruim/limitada.

## Achados parciais (19 UFs, sem Sudeste; não publicar ainda)

- Cobertura log × TSE: 99,80–99,97% por UF. Fusos certos (MT MS RO RR AM +1h; AC e oeste do AM +2h).
- 61,9% dos votos até 12h; 8.641 depois das 17h; cabine mediana 12 s; mesa 15 s; biometria 88,6% (ES 72,7%).
- Simpson: seção que vota mais cedo dá mais Lula (0,74 no agregado), mas dentro do município cai para 0,22;
  ES e RO invertem o sinal. A maior parte é efeito de lugar (o Nordeste vota cedo e vota Lula).

## Pendências

1. Terminar a leitura (BA, PR, RJ, MG, SP) e rodar `estatisticas.py`.
2. Conferir seções com votos até 18h50 (fila real ou relógio da urna errado).
3. Backup no Cloudflare R2: Vitor cria bucket `eleicoes-2026-horarios` + token só desse bucket e põe
   `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET` no `.env` **deste** repo (não usar o do Domus).
   Depois: `backup_r2.py` (stdlib, SigV4) com sha256 e conferência baixando de volta. Supabase não serve (free 1 GB).
4. PR (`/ship`) com código + `dados/estatisticas.json`.
5. Antes de remover o worktree: mover `horarios/brutos/` para o repo principal (senão os dados somem junto).
