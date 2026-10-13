"""Indicadores da Receita, parte 1 (mei_acima_teto, empresa_recem_aberta, atividade_incompativel, socio_doador)
e de comparação (preco_fora_da_curva, gasto_por_voto, transferencia_candidato).

Funções puras, sem limiar fixo no código (tudo vem de rastro/config.json). Cada item segue o contrato
{nome, fato, valor, fonte_url, contraparte?}. Nenhum CPF, nem trecho, vai para a saída; CNPJ de MEI sai mascarado.
"""
import json
import logging
import re
import statistics
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

try:
    from rastro.cnpj import BASE_CNPJ, _norm
    from rastro.contas import ELEITOS, SAIDA_AGREGADOS, SAIDA_CONTAS, SAIDA_HASH, URL_CONTAS, digitos, gravar
except ImportError:  # rodado como script: python3 rastro/indicadores.py
    from cnpj import BASE_CNPJ, _norm
    from contas import ELEITOS, SAIDA_AGREGADOS, SAIDA_CONTAS, SAIDA_HASH, URL_CONTAS, digitos, gravar

log = logging.getLogger("rastro.indicadores")
AQUI = Path(__file__).resolve().parent
CONFIG = AQUI / "config.json"
CNAE_X_TIPO = AQUI / "cnae_x_tipo.json"
FORNECEDORES = AQUI / "dados" / "fornecedores.json"
SAIDA = AQUI / "dados" / "indicadores.json"
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


def percentil(valores, cfg):
    """Percentil de cfg['percentil_comparacao']; None quando o grupo tem menos de cfg['min_campanhas_grupo'] campanhas."""
    if len(valores) < cfg["min_campanhas_grupo"]:
        return None
    return statistics.quantiles(valores, n=100, method=cfg["quantis_metodo"])[cfg["percentil_comparacao"] - 1]


def preco_fora_da_curva(sq, contas, eleito, agregados, cfg):
    cargo, uf = (eleito or {}).get("cargo"), (eleito or {}).get("uf")
    if not cargo or not uf:
        return []
    eleitorado = (agregados.get("eleitorado") or {}).get(uf)
    out = []
    for tipo, gasto in sorted((((contas or {}).get("despesas") or {}).get("por_tipo") or {}).items()):
        grupo = (agregados.get("por_tipo_cargo_uf") or {}).get(f"{tipo}|{cargo}|{uf}") or []
        p = percentil(grupo, cfg)
        if p is None or gasto <= p:
            continue
        mil = f"; {brl(gasto / eleitorado * 1000)} por mil eleitores da UF" if eleitorado else ""
        out.append({
            "nome": "preco_fora_da_curva",
            "fato": (f"Gastou {brl(gasto)} em \"{tipo}\", acima do percentil {cfg['percentil_comparacao']} "
                     f"({brl(p)}) das {len(grupo)} campanhas de {cargo} em {uf}{mil}"),
            "valor": gasto,
            "fonte_url": URL_CONTAS,
        })
    return out


def gasto_por_voto(sq, contas, eleito, agregados, cfg):
    cargo, uf = (eleito or {}).get("cargo"), (eleito or {}).get("uf")
    votos = (eleito or {}).get("votos") or 0
    desp = (contas or {}).get("despesas")
    if not cargo or not uf or votos <= 0 or not (contas or {}).get("prestacao_parcial") or not desp:
        return []
    grupo = (agregados.get("custo_por_voto") or {}).get(f"{cargo}|{uf}") or []
    p = percentil(grupo, cfg)
    custo = round(desp["total_contratado"] / votos, 2)
    if p is None or custo <= p:
        return []
    return [{
        "nome": "gasto_por_voto",
        "fato": (f"Gastou {brl(custo)} por voto ({brl(desp['total_contratado'])} para {votos} votos), acima do "
                 f"percentil {cfg['percentil_comparacao']} ({brl(p)}) das {len(grupo)} campanhas de {cargo} em {uf}"),
        "valor": custo,
        "fonte_url": URL_CONTAS,
    }]


def transferencia_candidato(sq, contas, agregados, eleitorado, cfg, fornecedores=None):
    """Sem `fornecedores` (dados da Receita), todo fornecedor sai só pelo CNPJ mascarado."""
    repasses = (agregados.get("repasses") or {}).get(sq) or {}
    candidatos = agregados.get("candidatos") or {}
    por_cnpj = agregados.get("por_cnpj") or {}
    forn = {cnpj: f for cnpj, f in _fornecedores_pj(contas)}
    out = []
    for rec, valor in repasses.items():
        info = candidatos.get(rec)
        if not info:
            log.warning("repasse %s -> %s sem dados do recebedor: ignorado", sq, rec)
            continue
        comuns = sorted(c for c in forn if rec in (por_cnpj.get(c) or {}).get("campanhas", []))
        if not comuns:
            continue
        nomes = ", ".join((mascarar_cnpj(c) if fornecedores is None else _contraparte(c, forn[c], fornecedores.get(c) or {}))
                          for c in comuns)
        votos = info.get("votos") or 0
        total_uf = (eleitorado or {}).get(info.get("uf"))
        infima = bool(total_uf) and votos / total_uf < cfg["votacao_infima_fracao_eleitorado"]
        destaque = f"; o recebedor teve {votos} votos (votação ínfima)" if infima else ""
        out.append((infima, {
            "nome": "transferencia_candidato",
            "fato": (f"Repassou {brl(valor)} a {info.get('nome') or 'outro candidato'}, que usou "
                     f"{len(comuns)} fornecedor{'es' if len(comuns) != 1 else ''} PJ em comum ({nomes}){destaque}"),
            "valor": valor,
            "fonte_url": URL_CONTAS,
            "contraparte": info.get("nome") or "outro candidato",
        }))
    out.sort(key=lambda t: not t[0])
    return [i for _, i in out]


def calcular(sq, contas, fornecedores, agregados, doadores_hash, cfg, cnae_x_tipo, idx=None, eleito=None):
    """Itens dos indicadores de um eleito; doadores_hash=None pula o socio_doador, eleito=None os de votos/cargo."""
    itens = (mei_acima_teto(sq, contas, fornecedores, agregados, cfg)
             + empresa_recem_aberta(sq, contas, fornecedores, cfg)
             + atividade_incompativel(sq, contas, fornecedores, cnae_x_tipo))
    if doadores_hash is not None:
        itens += socio_doador(sq, contas, fornecedores, doadores_hash, idx)
    if eleito is not None:
        itens += preco_fora_da_curva(sq, contas, eleito, agregados, cfg)
        itens += gasto_por_voto(sq, contas, eleito, agregados, cfg)
    itens += transferencia_candidato(sq, contas, agregados, agregados.get("eleitorado"), cfg, fornecedores)
    return itens


def gerar(dir_contas, fornecedores_path, agregados_path, hash_path, cfg, saida, cnae_x_tipo=None, eleitos_path=ELEITOS):
    cnae_x_tipo = cnae_x_tipo if cnae_x_tipo is not None else ler_json(CNAE_X_TIPO)
    env = ler_json(fornecedores_path)
    fornecedores = env["fornecedores"]
    agregados = ler_json(agregados_path)
    if Path(hash_path).exists():
        doadores_hash = ler_json(hash_path)
    else:
        doadores_hash = None
        log.warning("sem %s: socio_doador pulado", hash_path)
    idx = indice_doadores(doadores_hash) if doadores_hash is not None else None  # uma vez, não por eleito
    if Path(eleitos_path).exists():
        eleitos = {e["sq"]: e for e in ler_json(eleitos_path)["eleitos"]}
    else:
        eleitos = {}
        log.warning("sem %s: preco_fora_da_curva e gasto_por_voto pulados", eleitos_path)
    res = {}
    for arq in sorted(Path(dir_contas).glob("*.json")):
        contas = ler_json(arq)
        sq = str(contas.get("sq") or arq.stem)
        itens = calcular(sq, contas, fornecedores, agregados, doadores_hash, cfg, cnae_x_tipo, idx, eleitos.get(sq))
        if itens:
            res[sq] = itens
    fonte = [FONTE_RECEITA, URL_CONTAS]
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
