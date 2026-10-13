"""Indicadores da Receita: mei_acima_teto, empresa_recem_aberta, atividade_incompativel, socio_doador (parte 1) e
socio_ligado, multicampanha, situacao_irregular, concentracao, endereco_compartilhado (parte 2).

Funções puras, sem limiar fixo no código (tudo vem de rastro/config.json). Cada item segue o contrato
{nome, fato, valor, fonte_url, contraparte?}. Nenhum CPF, nem trecho, vai para a saída; CNPJ de MEI sai mascarado.
"""
import functools
import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

try:
    from rastro.baixar import URL_CAND
    from rastro.cnpj import BASE_CNPJ, _norm
    from rastro.contas import SAIDA_AGREGADOS, SAIDA_CONTAS, SAIDA_HASH, URL_CONTAS, digitos, gravar
except ImportError:  # rodado como script: python3 rastro/indicadores.py
    from baixar import URL_CAND
    from cnpj import BASE_CNPJ, _norm
    from contas import SAIDA_AGREGADOS, SAIDA_CONTAS, SAIDA_HASH, URL_CONTAS, digitos, gravar

log = logging.getLogger("rastro.indicadores")
AQUI = Path(__file__).resolve().parent
CONFIG = AQUI / "config.json"
CNAE_X_TIPO = AQUI / "cnae_x_tipo.json"
FORNECEDORES = AQUI / "dados" / "fornecedores.json"
SAIDA = AQUI / "dados" / "indicadores.json"
CANDIDATOS = AQUI / "brutos" / "candidatos.json"
FONTE_RECEITA = BASE_CNPJ.rsplit("/download", 1)[0]
RE_MEIO = re.compile(r"\*{3}(\d{6})\*{2}")
PAPEIS_DOADOR = ("doador", "ambos")


def ler_json(caminho):
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


def brl(v):
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def mascarar_cnpj(cnpj):
    """Mantém só a filial: '12345678000195' -> '**.***.***/0001-**'. Menos de 14 dígitos vira tudo máscara."""
    d = digitos(cnpj)
    filial = d[8:12] if len(d) == 14 else "****"
    return f"**.***.***/{filial}-**"


def _contraparte(cnpj, forn_pj, receita):
    """Nome do fornecedor; MEI só pelo CNPJ mascarado."""
    if receita.get("mei"):
        return mascarar_cnpj(cnpj)
    return receita.get("razao") or forn_pj.get("nome") or mascarar_cnpj(cnpj)


def _fornecedores_pj(contas):
    for f in ((contas or {}).get("despesas") or {}).get("fornecedores_pj", []):
        cnpj = digitos(f.get("cnpj"))
        if len(cnpj) == 14:
            yield cnpj, f


def mei_acima_teto(sq, contas, fornecedores, agregados, cfg):
    teto = cfg["mei_teto_anual"]
    out = []
    for cnpj, f in _fornecedores_pj(contas):
        rec = fornecedores.get(cnpj) or {}
        agr = (agregados.get("por_cnpj") or {}).get(cnpj)
        if rec.get("mei") is not True or not agr or agr["total_recebido"] <= teto:
            continue
        n = agr["n_campanhas"]
        out.append({
            "nome": "mei_acima_teto",
            "fato": (f"MEI recebeu {brl(agr['total_recebido'])} de {n} campanha{'s' if n != 1 else ''} em 2026, "
                     f"acima do teto de faturamento anual do MEI ({brl(teto)}; {cfg['mei_teto_fonte']})"),
            "valor": agr["total_recebido"],
            "fonte_url": cfg.get("mei_teto_url") or FONTE_RECEITA,
            "contraparte": mascarar_cnpj(cnpj),
        })
    return out


def empresa_recem_aberta(sq, contas, fornecedores, cfg):
    inicio = date.fromisoformat(cfg["campanha_inicio"])
    limite = inicio - timedelta(days=cfg["recem_aberta_dias"])
    out = []
    for cnpj, f in _fornecedores_pj(contas):
        rec = fornecedores.get(cnpj) or {}
        if not rec.get("abertura"):
            continue
        abertura = date.fromisoformat(rec["abertura"])
        if abertura <= limite:
            continue
        out.append({
            "nome": "empresa_recem_aberta",
            "fato": (f"Empresa aberta em {abertura.strftime('%d/%m/%Y')}, {'depois' if abertura > inicio else 'menos de ' + str(cfg['recem_aberta_dias']) + ' dias antes'}"
                     f" do início da campanha ({inicio.strftime('%d/%m/%Y')})"),
            "valor": f["total"],
            "fonte_url": FONTE_RECEITA,
            "contraparte": _contraparte(cnpj, f, rec),
        })
    return out


def atividade_incompativel(sq, contas, fornecedores, cnae_x_tipo):
    out = []
    for cnpj, f in _fornecedores_pj(contas):
        rec = fornecedores.get(cnpj) or {}
        cnae = digitos(rec.get("cnae") or f.get("cnae"))
        todos = f.get("tipos", [])
        tipos = [t for t in todos if t in cnae_x_tipo and not t.startswith("_")]
        if not cnae or not tipos or len(tipos) != len(todos):
            continue  # tipo fora da tabela pode explicar o CNAE: na dúvida, cala
        if any(cnae.startswith(p) for t in tipos for p in cnae_x_tipo[t]):
            continue  # algum tipo é compatível: na dúvida, cala
        out.append({
            "nome": "atividade_incompativel",
            "fato": (f"Atividade principal da empresa (CNAE {cnae}) não costuma corresponder ao que a campanha "
                     f"declarou pagar: {'; '.join(tipos)}"),
            "valor": f["total"],
            "fonte_url": FONTE_RECEITA,
            "contraparte": _contraparte(cnpj, f, rec),
        })
    return out


def indice_doadores(doadores_hash):
    """{(nome normalizado, cpf_meio): {campanhas, total}} só de doador/ambos. O hash em si não é usado."""
    idx = {}
    for d in (doadores_hash or {}).values():
        if d.get("papel") not in PAPEIS_DOADOR or not d.get("cpf_meio") or not d.get("nome"):
            continue
        idx[(_norm(d["nome"]), d["cpf_meio"])] = d
    return idx


def socio_doador(sq, contas, fornecedores, doadores_hash, idx=None):
    if idx is None:
        idx = indice_doadores(doadores_hash)
    out = []
    for cnpj, f in _fornecedores_pj(contas):
        rec = fornecedores.get(cnpj) or {}
        if rec.get("mei"):
            continue  # sócio de MEI é a própria pessoa física: fica fora
        vistos = set()
        for s in rec.get("socios") or []:
            m = RE_MEIO.fullmatch((s.get("cpf_mascarado") or "").strip())
            if not m or not s.get("nome"):
                continue
            chave = (_norm(s["nome"]), m.group(1))
            d = idx.get(chave)
            if not d or chave in vistos:
                continue
            vistos.add(chave)
            n = len(d.get("campanhas") or [])
            out.append({
                "nome": "socio_doador",
                "fato": (f"{chave[0]}, sócio(a) desta empresa, consta como doador(a) em {n} campanha{'s' if n != 1 else ''} "
                         f"de 2026, num total de {brl(d['total'])}; pode ser homônimo"),
                "valor": d["total"],
                "fonte_url": URL_CONTAS,
                "contraparte": _contraparte(cnpj, f, rec),
            })
    return out


@functools.lru_cache(maxsize=4)
def _ignorar_chave(particulas, comuns):
    return frozenset(_norm(x) for x in particulas + comuns)


def _ignorar(cfg):
    return _ignorar_chave(tuple(cfg["sobrenome_particulas"]), tuple(cfg["sobrenomes_comuns"]))


def sobrenomes(nome, cfg):
    """Sobrenomes de um nome civil: tokens depois do prenome, sem partículas nem sobrenomes comuns (normalizados)."""
    ignorar = _ignorar(cfg)
    return {t for t in _norm(nome).split()[1:] if t not in ignorar}


def indice_candidatos(candidatos):
    """{(nome normalizado, cpf_meio): [sq]} só de quem tem CPF; sem CPF não casa só por nome."""
    idx = {}
    for sq, c in (candidatos or {}).items():
        if c.get("cpf_meio") and c.get("nome"):
            idx.setdefault((_norm(c["nome"]), c["cpf_meio"]), []).append(sq)
    return idx


def socio_ligado(sq, contas, fornecedores, candidatos, cfg, idx=None):
    """Sócio que consta como candidato/suplente em 2026 (nome e trecho do CPF), ou que tem o mesmo sobrenome do pagador."""
    if idx is None:
        idx = indice_candidatos(candidatos)
    pagador = (candidatos or {}).get(sq)
    sob_pagador = sobrenomes(pagador["nome"], cfg) if pagador and pagador.get("nome") else set()
    out = []
    for cnpj, f in _fornecedores_pj(contas):
        rec = fornecedores.get(cnpj) or {}
        if rec.get("mei"):
            continue  # sócio de MEI é a própria pessoa física: fica fora
        vistos = set()
        for s in rec.get("socios") or []:
            if not s.get("nome"):
                continue
            nome = _norm(s["nome"])
            m = RE_MEIO.fullmatch((s.get("cpf_mascarado") or "").strip())
            chave = (nome, m.group(1) if m else None)
            if chave in vistos:
                continue
            fato = None
            cands = [c for c in idx.get(chave, []) if c != sq] if m else []
            if cands:
                c = candidatos[cands[0]]
                fato = (f"{nome}, sócio(a) desta empresa, consta como candidato(a)/suplente em 2026 "
                        f"({c.get('cargo') or 'cargo não informado'}, {c.get('uf') or 'UF não informada'}); pode ser homônimo")
            elif sob_pagador and nome != _norm(pagador["nome"]):
                comum = sorted(sob_pagador & sobrenomes(s["nome"], cfg))
                if comum:
                    fato = (f"{nome}, sócio(a) desta empresa, tem o mesmo sobrenome ({', '.join(comum)}) do(a) "
                            f"candidato(a) que a contratou; sobrenome igual não prova relação entre as pessoas")
            if not fato:
                continue
            vistos.add(chave)
            out.append({"nome": "socio_ligado", "fato": fato, "valor": f["total"], "fonte_url": URL_CAND,
                        "contraparte": _contraparte(cnpj, f, rec)})
    return out


def multicampanha(sq, contas, fornecedores, agregados, cfg):
    minimo = cfg["multicampanha_min"]
    out = []
    for cnpj, f in _fornecedores_pj(contas):
        agr = (agregados.get("por_cnpj") or {}).get(cnpj)
        if not agr or agr["n_campanhas"] < minimo:
            continue
        out.append({
            "nome": "multicampanha",
            "fato": f"Fornecedor de {agr['n_campanhas']} campanhas em 2026 (o painel destaca a partir de {minimo})",
            "valor": agr["n_campanhas"],
            "fonte_url": URL_CONTAS,
            "contraparte": _contraparte(cnpj, f, fornecedores.get(cnpj) or {}),
        })
    return out


def situacao_irregular(sq, contas, fornecedores, cfg, data_base=None):
    irregulares = {s.upper() for s in cfg["situacoes_irregulares"]}
    base = f" (base de {data_base})" if data_base else ""
    out = []
    for cnpj, f in _fornecedores_pj(contas):
        rec = fornecedores.get(cnpj) or {}
        sit = (rec.get("situacao") or "").upper()
        if sit not in irregulares:
            continue
        out.append({
            "nome": "situacao_irregular",
            "fato": f"Situação cadastral na Receita: {sit}{base}",
            "valor": f["total"],
            "fonte_url": FONTE_RECEITA,
            "contraparte": _contraparte(cnpj, f, rec),
        })
    return out


def concentracao(sq, contas, fornecedores, cfg):
    total = ((contas or {}).get("despesas") or {}).get("total_contratado")
    limite = cfg["concentracao_pct"]
    if not total or total <= 0:
        return []  # sem base não há percentual: cala
    out = []
    for cnpj, f in _fornecedores_pj(contas):
        if f["total"] * 100 <= limite * total:
            continue
        pct = round(f["total"] * 100 / total, 1)
        out.append({
            "nome": "concentracao",
            "fato": (f"Concentra {str(pct).replace('.', ',')}% do total contratado pela campanha "
                     f"({brl(f['total'])} de {brl(total)}); o painel destaca acima de {limite}%"),
            "valor": pct,
            "fonte_url": URL_CONTAS,
            "contraparte": _contraparte(cnpj, f, fornecedores.get(cnpj) or {}),
        })
    return out


def endereco_compartilhado(sq, contas, fornecedores, cfg):
    """Fornecedores da mesma campanha com o mesmo endereço na Receita. O endereço não sai (de MEI pode ser a casa)."""
    grupos = {}
    for cnpj, f in _fornecedores_pj(contas):
        chave = (fornecedores.get(cnpj) or {}).get("endereco_chave")
        if chave:
            grupos.setdefault(chave, []).append((cnpj, f))
    out = []
    for membros in grupos.values():
        if len({c[:8] for c, _ in membros}) < cfg["endereco_min_fornecedores"]:  # matriz e filial são a mesma empresa
            continue
        for cnpj, f in membros:
            rec = fornecedores.get(cnpj) or {}
            outros = [_contraparte(c, g, fornecedores.get(c) or {}) for c, g in membros if c != cnpj]
            out.append({
                "nome": "endereco_compartilhado",
                "fato": f"Mesmo endereço cadastrado na Receita que outro(s) fornecedor(es) da campanha: {'; '.join(outros)}",
                "valor": f["total"],
                "fonte_url": FONTE_RECEITA,
                "contraparte": _contraparte(cnpj, f, rec),
            })
    return out


def calcular(sq, contas, fornecedores, agregados, doadores_hash, cfg, cnae_x_tipo, idx=None,
             candidatos=None, idx_cand=None, data_base=None):
    """Itens dos nove indicadores de um eleito; doadores_hash=None pula o socio_doador, candidatos=None o socio_ligado."""
    itens = (mei_acima_teto(sq, contas, fornecedores, agregados, cfg)
             + empresa_recem_aberta(sq, contas, fornecedores, cfg)
             + atividade_incompativel(sq, contas, fornecedores, cnae_x_tipo))
    if doadores_hash is not None:
        itens += socio_doador(sq, contas, fornecedores, doadores_hash, idx)
    if candidatos is not None:
        itens += socio_ligado(sq, contas, fornecedores, candidatos, cfg, idx_cand)
    return (itens + multicampanha(sq, contas, fornecedores, agregados, cfg)
            + situacao_irregular(sq, contas, fornecedores, cfg, data_base)
            + concentracao(sq, contas, fornecedores, cfg)
            + endereco_compartilhado(sq, contas, fornecedores, cfg))


def gerar(dir_contas, fornecedores_path, agregados_path, hash_path, cfg, saida, cnae_x_tipo=None,
          candidatos_path=CANDIDATOS):
    cnae_x_tipo = cnae_x_tipo if cnae_x_tipo is not None else ler_json(CNAE_X_TIPO)
    env = ler_json(fornecedores_path)
    fornecedores = env["fornecedores"]
    agregados = ler_json(agregados_path)
    if Path(hash_path).exists():
        doadores_hash = ler_json(hash_path)
    else:
        doadores_hash = None
        log.warning("sem %s: socio_doador pulado", hash_path)
    if Path(candidatos_path).exists():
        candidatos = ler_json(candidatos_path)
        if not any(c.get("cpf_meio") for c in candidatos.values()):
            log.warning("%s sem nenhum cpf_meio: o ramo candidato do socio_ligado não vai casar", candidatos_path)
    else:
        candidatos = None
        log.warning("sem %s: socio_ligado pulado", candidatos_path)
    idx = indice_doadores(doadores_hash) if doadores_hash is not None else None  # uma vez, não por eleito
    idx_cand = indice_candidatos(candidatos) if candidatos is not None else None
    res = {}
    for arq in sorted(Path(dir_contas).glob("*.json")):
        contas = ler_json(arq)
        sq = str(contas.get("sq") or arq.stem)
        itens = calcular(sq, contas, fornecedores, agregados, doadores_hash, cfg, cnae_x_tipo, idx,
                         candidatos, idx_cand, env.get("data_base"))
        if itens:
            res[sq] = itens
    fonte = [FONTE_RECEITA, URL_CONTAS, URL_CAND]
    for e in (env, agregados):
        for u in e.get("fonte") or []:
            if u not in fonte:
                fonte.append(u)
    gravar(saida, {"fonte": fonte, "data_base": env.get("data_base"),
                   "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "indicadores": res})
    return res


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    res = gerar(SAIDA_CONTAS, FORNECEDORES, SAIDA_AGREGADOS, SAIDA_HASH, ler_json(CONFIG), SAIDA)
    log.info("%d eleitos com indicadores -> %s", len(res), SAIDA)


if __name__ == "__main__":
    main()
