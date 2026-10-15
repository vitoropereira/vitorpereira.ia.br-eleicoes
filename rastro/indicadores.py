"""Indicadores da Receita (mei_acima_teto, empresa_recem_aberta, atividade_incompativel, socio_doador, mais o
ramo de nomeações do socio_ligado; parte 2: socio_ligado, multicampanha, situacao_irregular, concentracao,
endereco_compartilhado), de comparação (preco_fora_da_curva, gasto_por_voto, transferencia_candidato)
e de pessoal e extrato (pessoal_pf, saque_especie, pagamento_tardio).

Funções puras, sem limiar fixo no código (tudo vem de rastro/config.json). Cada item segue o contrato
{nome, fato, valor, fonte_url, contraparte?}. Nenhum CPF, nem trecho, vai para a saída; CNPJ de MEI sai mascarado; pessoa física paga só entra como contagem.
"""
import functools
import json
import logging
import re
import statistics
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

try:
    from rastro.baixar import URL_CAND, URL_EXTRATO
    from rastro.cnpj import BASE_CNPJ, _norm
    from rastro.contas import ELEITOS, SAIDA_AGREGADOS, SAIDA_CONTAS, SAIDA_HASH, SAIDA_PF, URL_CONTAS, digitos, gravar
    from rastro.extrato import SAIDA_SAQUES
    from rastro.nomeacoes import NOMEADOS
except ImportError:  # rodado como script: python3 rastro/indicadores.py
    from baixar import URL_CAND, URL_EXTRATO
    from cnpj import BASE_CNPJ, _norm
    from contas import ELEITOS, SAIDA_AGREGADOS, SAIDA_CONTAS, SAIDA_HASH, SAIDA_PF, URL_CONTAS, digitos, gravar
    from extrato import SAIDA_SAQUES
    from nomeacoes import NOMEADOS

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
        votos = info.get("votos")  # None: recebedor sem apuração conhecida, não é "votação ínfima"
        total_uf = (eleitorado or {}).get(info.get("uf"))
        infima = votos is not None and bool(total_uf) and votos / total_uf < cfg["votacao_infima_fracao_eleitorado"]
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


def indice_pf(pf_hash_campanhas):
    """{hash do CPF: nº de campanhas que o pagaram}. Só a contagem; o hash nunca sai daqui."""
    n = Counter()
    for hashes in (pf_hash_campanhas or {}).values():
        n.update(set(hashes))
    return n


def pessoal_pf(sq, contas, pf_hash_campanhas, cfg, idx=None):
    """Pagamentos a pessoas físicas: muitas pessoas, as mesmas pessoas em várias campanhas, valores redondos e altos.
    Nunca traz nome nem CPF, só contagens e totais; por isso nenhum item tem contraparte."""
    pf = ((contas or {}).get("despesas") or {}).get("fornecedores_pf") or {}
    if not pf:
        return []
    total, qtd = pf.get("total") or 0, pf.get("qtd") or 0
    out = []

    def item(fato, valor):
        out.append({"nome": "pessoal_pf", "fato": fato, "valor": valor, "fonte_url": URL_CONTAS})

    if qtd and qtd >= cfg["pf_qtd_min"]:
        item(f"Campanha pagou {qtd} pessoas físicas, num total de {brl(total)}", total)
    hashes = (pf_hash_campanhas or {}).get(sq)
    if hashes:
        if idx is None:
            idx = indice_pf(pf_hash_campanhas)
        n = sum(1 for h in set(hashes) if idx[h] >= cfg["pf_repetido_min_campanhas"])
        if n:
            item(f"{n} {'pessoa paga também recebeu' if n == 1 else 'pessoas pagas também receberam'} de outras "
                 f"campanhas de 2026 (ao menos {cfg['pf_repetido_min_campanhas']} campanhas no total)", total)
    altos = [v for v in pf.get("valores") or [] if v >= cfg["pf_valor_alto"] and v % cfg["pf_redondo_multiplo"] == 0]
    if len(altos) >= cfg["pf_redondo_alto_min_qtd"]:
        item(f"{len(altos)} pessoas físicas receberam valores redondos (múltiplos de {brl(cfg['pf_redondo_multiplo'])}) "
             f"de {brl(cfg['pf_valor_alto'])} ou mais, num total de {brl(sum(altos))}", sum(altos))
    return out


def saque_especie(sq, contas, saques, cfg):
    """Saques e pagamentos em espécie no extrato da campanha, casados pelo CNPJ da conta (NR_CNPJ_PRESTADOR_CONTA)."""
    cnpj = digitos((contas or {}).get("cnpj_prestador"))
    lanc = (saques or {}).get(cnpj) if len(cnpj) == 14 else None
    if not lanc:
        return []
    total = round(sum(x["valor"] for x in lanc), 2)
    datas = sorted({x["data"] for x in lanc if x.get("data")})
    mostradas = ", ".join(date.fromisoformat(d).strftime("%d/%m/%Y") for d in datas[:5])
    resto = f" e mais {len(datas) - 5}" if len(datas) > 5 else ""
    n = len(lanc)
    return [{"nome": "saque_especie",
             "fato": (f"{n} lançamento{'s' if n != 1 else ''} de saque ou pagamento em espécie na conta bancária da "
                      f"campanha, num total de {brl(total)}" + (f" (em {mostradas}{resto})" if datas else "")),
             "valor": total, "fonte_url": URL_EXTRATO}]


def pagamento_tardio(sq, contas, cfg):
    """Pagamentos depois do dia da eleição e fração do pago na semana final (de dia_eleicao-tardio_dias até o dia)."""
    por_dia = ((contas or {}).get("despesas") or {}).get("pago_por_dia") or {}
    total = sum(por_dia.values())
    if total <= 0:
        return []
    eleicao = date.fromisoformat(cfg["dia_eleicao"])
    ini = eleicao - timedelta(days=cfg["tardio_dias"])
    depois = sum(v for d, v in por_dia.items() if date.fromisoformat(d) > eleicao)
    janela = sum(v for d, v in por_dia.items() if ini <= date.fromisoformat(d) <= eleicao)
    out = []
    if depois > 0:
        out.append({"nome": "pagamento_tardio",
                    "fato": f"{brl(depois)} em pagamentos registrados depois do dia da eleição ({eleicao.strftime('%d/%m/%Y')})",
                    "valor": round(depois, 2), "fonte_url": URL_CONTAS})
    if janela / total > cfg["tardio_pct_ultimos_dias"]:
        out.append({"nome": "pagamento_tardio",
                    "fato": (f"{janela / total:.0%} do total pago ({brl(janela)} de {brl(total)}) saiu entre "
                             f"{ini.strftime('%d/%m/%Y')} e {eleicao.strftime('%d/%m/%Y')}, a semana final antes da eleição"),
                    "valor": round(janela, 2), "fonte_url": URL_CONTAS})
    return out


def indice_nomeados(nomeados):
    """{(nome normalizado, cpf_meio): {funcao, orgao, base}} do rastro/brutos/nomeados.json."""
    idx = {}
    for d in (nomeados or {}).get("nomeados") or []:
        if d.get("cpf_meio") and d.get("nome"):
            idx[(_norm(d["nome"]), d["cpf_meio"])] = d
    return idx


ORIGEM_NOMEADOS = {"siape": "Portal da Transparência", "camara": "Câmara dos Deputados", "senado": "Senado Federal"}


def socio_nomeado(sq, contas, fornecedores, idx_nomeados, cfg):
    """socio_ligado, ramo nomeações: sócio de fornecedor (não MEI) com função comissionada no serviço federal."""
    mes = datetime.strptime(cfg["nomeacoes_mes"], "%Y-%m").strftime("%m/%Y")
    fontes = cfg.get("nomeacoes_fontes") or {}
    ref = cfg["nomeacoes_mes"].replace("-", "")
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
            d = idx_nomeados.get(chave)
            if not d or chave in vistos:
                continue
            vistos.add(chave)
            base = d.get("base") or "siape"
            url = (fontes.get(base) or "").format(mes=ref)
            if not url:
                continue
            out.append({
                "nome": "socio_ligado",
                "fato": (f"{chave[0]}, sócio(a) desta empresa, consta no cadastro de servidores federais "
                         f"({ORIGEM_NOMEADOS.get(base, base)}, {mes}) com função {d.get('funcao') or 'comissionada'} "
                         f"em {d.get('orgao') or 'órgão não informado'}; pode ser homônimo"),
                "valor": f["total"],
                "fonte_url": url,
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
             pf_hash=None, saques=None, idx_pf=None, idx_nomeados=None, eleito=None,
             candidatos=None, idx_cand=None, data_base=None):
    """Itens dos indicadores de um eleito; doadores_hash, idx_nomeados, pf_hash e saques None pulam socio_doador,
    socio_ligado, a parte de repetidos do pessoal_pf e o saque_especie; eleito=None pula os de votos/cargo; candidatos=None
    pula o ramo candidato/sobrenome do socio_ligado."""
    itens = (mei_acima_teto(sq, contas, fornecedores, agregados, cfg)
             + empresa_recem_aberta(sq, contas, fornecedores, cfg)
             + atividade_incompativel(sq, contas, fornecedores, cnae_x_tipo))
    if doadores_hash is not None:
        itens += socio_doador(sq, contas, fornecedores, doadores_hash, idx)
    if candidatos is not None:
        itens += socio_ligado(sq, contas, fornecedores, candidatos, cfg, idx_cand)
    if idx_nomeados is not None:
        itens += socio_nomeado(sq, contas, fornecedores, idx_nomeados, cfg)
    itens += (multicampanha(sq, contas, fornecedores, agregados, cfg)
              + situacao_irregular(sq, contas, fornecedores, cfg, data_base)
              + concentracao(sq, contas, fornecedores, cfg)
              + endereco_compartilhado(sq, contas, fornecedores, cfg))
    if eleito is not None:
        itens += preco_fora_da_curva(sq, contas, eleito, agregados, cfg)
        itens += gasto_por_voto(sq, contas, eleito, agregados, cfg)
    itens += transferencia_candidato(sq, contas, agregados, agregados.get("eleitorado"), cfg, fornecedores)
    itens += pessoal_pf(sq, contas, pf_hash, cfg, idx_pf)
    if saques is not None:
        itens += saque_especie(sq, contas, saques, cfg)
    return itens + pagamento_tardio(sq, contas, cfg)


def ler_opcional(caminho, o_que, avisos=None):
    """JSON de um arquivo opcional de brutos/; ausente (ou caminho None) vira None e um aviso (no log e em `avisos`)."""
    if caminho is not None and Path(caminho).exists():
        return ler_json(caminho)
    log.warning("sem %s: %s pulado", caminho, o_que)
    if avisos is not None:
        avisos.append(f"{o_que}: pulado (fonte indisponível)")
    return None


def gerar(dir_contas, fornecedores_path, agregados_path, hash_path, cfg, saida, cnae_x_tipo=None,
          pf_path=None, saques_path=None, nomeados_path=NOMEADOS,
          eleitos_path=ELEITOS, candidatos_path=CANDIDATOS):
    cnae_x_tipo = cnae_x_tipo if cnae_x_tipo is not None else ler_json(CNAE_X_TIPO)
    env = ler_json(fornecedores_path)
    fornecedores = env["fornecedores"]
    agregados = ler_json(agregados_path)
    avisos = []  # vão para indicadores.json["avisos"] e para a metodologia: o que não foi calculado nesta base
    doadores_hash = ler_opcional(hash_path, "socio_doador", avisos)
    if Path(candidatos_path).exists():
        candidatos = ler_json(candidatos_path)
        if not any(c.get("cpf_meio") for c in candidatos.values()):
            log.warning("%s sem nenhum cpf_meio: o ramo candidato do socio_ligado não vai casar", candidatos_path)
    else:
        candidatos = None
        log.warning("sem %s: socio_ligado pulado", candidatos_path)
        avisos.append("socio_ligado (candidatos): pulado (fonte indisponível)")
    idx = indice_doadores(doadores_hash) if doadores_hash is not None else None  # uma vez, não por eleito
    idx_cand = indice_candidatos(candidatos) if candidatos is not None else None
    if Path(eleitos_path).exists():
        eleitos = {e["sq"]: e for e in ler_json(eleitos_path)["eleitos"]}
    else:
        eleitos = {}
        log.warning("sem %s: preco_fora_da_curva e gasto_por_voto pulados", eleitos_path)
        avisos.append("preco_fora_da_curva e gasto_por_voto: pulados (fonte indisponível)")
    pf_hash = ler_opcional(pf_path, "repetidos do pessoal_pf", avisos)
    idx_pf = indice_pf(pf_hash) if pf_hash is not None else None
    saques = ler_opcional(saques_path, "saque_especie", avisos)
    idx_nomeados = None
    if nomeados_path is not None and Path(nomeados_path).exists():
        env_nom = ler_json(nomeados_path)
        if (env_nom.get("data_base") or "")[:7] != cfg["nomeacoes_mes"]:
            log.warning("%s é de %s mas config.nomeacoes_mes=%s: rode rastro/nomeacoes.py", nomeados_path,
                        env_nom.get("data_base"), cfg["nomeacoes_mes"])
        idx_nomeados = indice_nomeados(env_nom)
    else:
        log.warning("sem %s: socio_ligado (nomeações) pulado", nomeados_path)
        avisos.append("socio_ligado (nomeações): pulado (fonte indisponível)")
    res = {}
    for arq in sorted(Path(dir_contas).glob("*.json")):
        contas = ler_json(arq)
        sq = str(contas.get("sq") or arq.stem)
        itens = calcular(sq, contas, fornecedores, agregados, doadores_hash, cfg, cnae_x_tipo, idx,
                         pf_hash=pf_hash, saques=saques, idx_pf=idx_pf, idx_nomeados=idx_nomeados,
                         eleito=eleitos.get(sq), candidatos=candidatos, idx_cand=idx_cand,
                         data_base=env.get("data_base"))
        if itens:
            res[sq] = itens
    fonte = [FONTE_RECEITA, URL_CONTAS, URL_CAND] + ([URL_EXTRATO] if saques is not None else [])
    if idx_nomeados is not None and (cfg.get("nomeacoes_fontes") or {}).get("siape"):
        fonte.append(cfg["nomeacoes_fontes"]["siape"].format(mes=cfg["nomeacoes_mes"].replace("-", "")))
    for e in (env, agregados):
        for u in e.get("fonte") or []:
            if u not in fonte:
                fonte.append(u)
    gravar(saida, {"fonte": fonte, "data_base": env.get("data_base"),
                   "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "avisos": avisos, "indicadores": res})
    return res


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    res = gerar(SAIDA_CONTAS, FORNECEDORES, SAIDA_AGREGADOS, SAIDA_HASH, ler_json(CONFIG), SAIDA,
                pf_path=SAIDA_PF, saques_path=SAIDA_SAQUES)
    log.info("%d eleitos com indicadores -> %s", len(res), SAIDA)


if __name__ == "__main__":
    main()
