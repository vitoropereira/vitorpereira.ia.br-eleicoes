"""Indicadores da Receita (mei_acima_teto, empresa_recem_aberta, atividade_incompativel, socio_doador, mais o
ramo de nomeações do socio_ligado) e de pessoal e extrato (pessoal_pf, saque_especie, pagamento_tardio).

Funções puras, sem limiar fixo no código (tudo vem de rastro/config.json). Cada item segue o contrato
{nome, fato, valor, fonte_url, contraparte?}. Nenhum CPF, nem trecho, vai para a saída; CNPJ de MEI sai mascarado; pessoa física paga só entra como contagem.
"""
import json
import logging
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

try:
    from rastro.baixar import URL_EXTRATO
    from rastro.cnpj import BASE_CNPJ, _norm
    from rastro.contas import SAIDA_AGREGADOS, SAIDA_CONTAS, SAIDA_HASH, SAIDA_PF, URL_CONTAS, digitos, gravar
    from rastro.extrato import SAIDA_SAQUES
    from rastro.nomeacoes import NOMEADOS
except ImportError:  # rodado como script: python3 rastro/indicadores.py
    from baixar import URL_EXTRATO
    from cnpj import BASE_CNPJ, _norm
    from contas import SAIDA_AGREGADOS, SAIDA_CONTAS, SAIDA_HASH, SAIDA_PF, URL_CONTAS, digitos, gravar
    from extrato import SAIDA_SAQUES
    from nomeacoes import NOMEADOS

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


def calcular(sq, contas, fornecedores, agregados, doadores_hash, cfg, cnae_x_tipo, idx=None,
             pf_hash=None, saques=None, idx_pf=None, idx_nomeados=None):
    """Itens dos indicadores de um eleito; doadores_hash, idx_nomeados, pf_hash e saques None pulam socio_doador,
    socio_ligado, a parte de repetidos do pessoal_pf e o saque_especie."""
    itens = (mei_acima_teto(sq, contas, fornecedores, agregados, cfg)
             + empresa_recem_aberta(sq, contas, fornecedores, cfg)
             + atividade_incompativel(sq, contas, fornecedores, cnae_x_tipo))
    if doadores_hash is not None:
        itens += socio_doador(sq, contas, fornecedores, doadores_hash, idx)
    if idx_nomeados is not None:
        itens += socio_nomeado(sq, contas, fornecedores, idx_nomeados, cfg)
    itens += pessoal_pf(sq, contas, pf_hash, cfg, idx_pf)
    if saques is not None:
        itens += saque_especie(sq, contas, saques, cfg)
    return itens + pagamento_tardio(sq, contas, cfg)


def ler_opcional(caminho, o_que):
    """JSON de um arquivo opcional de brutos/; ausente (ou caminho None) vira None e um aviso."""
    if caminho is not None and Path(caminho).exists():
        return ler_json(caminho)
    log.warning("sem %s: %s pulado", caminho, o_que)
    return None


def gerar(dir_contas, fornecedores_path, agregados_path, hash_path, cfg, saida, cnae_x_tipo=None,
          pf_path=None, saques_path=None, nomeados_path=NOMEADOS):
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
    pf_hash = ler_opcional(pf_path, "repetidos do pessoal_pf")
    idx_pf = indice_pf(pf_hash) if pf_hash is not None else None
    saques = ler_opcional(saques_path, "saque_especie")
    idx_nomeados = None
    if nomeados_path is not None and Path(nomeados_path).exists():
        env_nom = ler_json(nomeados_path)
        if (env_nom.get("data_base") or "")[:7] != cfg["nomeacoes_mes"]:
            log.warning("%s é de %s mas config.nomeacoes_mes=%s: rode rastro/nomeacoes.py", nomeados_path,
                        env_nom.get("data_base"), cfg["nomeacoes_mes"])
        idx_nomeados = indice_nomeados(env_nom)
    else:
        log.warning("sem %s: socio_ligado (nomeações) pulado", nomeados_path)
    res = {}
    for arq in sorted(Path(dir_contas).glob("*.json")):
        contas = ler_json(arq)
        sq = str(contas.get("sq") or arq.stem)
        itens = calcular(sq, contas, fornecedores, agregados, doadores_hash, cfg, cnae_x_tipo, idx,
                         pf_hash=pf_hash, saques=saques, idx_pf=idx_pf, idx_nomeados=idx_nomeados)
        if itens:
            res[sq] = itens
    fonte = [FONTE_RECEITA, URL_CONTAS] + ([URL_EXTRATO] if saques is not None else [])
    if idx_nomeados is not None and (cfg.get("nomeacoes_fontes") or {}).get("siape"):
        fonte.append(cfg["nomeacoes_fontes"]["siape"].format(mes=cfg["nomeacoes_mes"].replace("-", "")))
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
    res = gerar(SAIDA_CONTAS, FORNECEDORES, SAIDA_AGREGADOS, SAIDA_HASH, ler_json(CONFIG), SAIDA,
                pf_path=SAIDA_PF, saques_path=SAIDA_SAQUES)
    log.info("%d eleitos com indicadores -> %s", len(res), SAIDA)


if __name__ == "__main__":
    main()
