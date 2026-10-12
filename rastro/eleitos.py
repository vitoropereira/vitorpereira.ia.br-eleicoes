#!/usr/bin/env python3
"""Lê os resultados do 1º turno em relatorio/dados/ e grava rastro/dados/eleitos.json. Não baixa nada."""
import json
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "relatorio" / "dados"
SAIDA = Path(__file__).resolve().parent / "dados" / "eleitos.json"
UFS = "ac al ap am ba ce df es go ma mt ms mg pa pb pr pe pi rj rn rs ro rr sc sp se to".split()
CARGOS = {3: "governador", 5: "senador", 6: "depfed", 7: "depest", 8: "distrital"}
URL = "https://resultados.tse.jus.br/oficial/ele2026/{ele}/dados/{uf}/{uf}-c{c:04d}-e00{ele}-u.json"


def codigos(uf):
    """Códigos de cargo lidos para a UF: o DF tem distrital (8) no lugar de estadual (7)."""
    return [c for c in CARGOS if not (c == 7 and uf == "df") and not (c == 8 and uf != "df")]


def montar(dados_dir, ufs):
    dados_dir = Path(dados_dir)
    eleitos, fonte, datas = [], [], []
    for uf in ufs:
        for c in codigos(uf):
            d = json.loads((dados_dir / f"{uf}-c{c:04d}.json").read_text(encoding="utf-8"))
            if d.get("tf") != "s":
                raise SystemExit(f"{uf}-c{c:04d}: apuração ainda não totalizada (tf != 's')")
            if not d.get("carg") or int(d["carg"][0]["cd"]) != c:
                raise SystemExit(f"{uf}-c{c:04d}: cargo inesperado no arquivo")
            fonte.append(URL.format(ele=d["ele"], uf=uf, c=c))
            datas.append(datetime.strptime(d["dg"], "%d/%m/%Y").date())
            for agr in d["carg"][0].get("agr", []):
                for par in agr.get("par", []):
                    for cand in par.get("cand", []):
                        if cand.get("e") != "s" or cand.get("st") == "2º turno":
                            continue
                        eleitos.append({
                            "sq": str(cand["sqcand"]),
                            "nome_urna": cand["nmu"],
                            "cargo": CARGOS[c],
                            "uf": uf.upper(),
                            "partido": par["sg"],
                            "votos": int(cand["vap"]),
                            "situacao": cand["st"],
                        })
    ordem = list(CARGOS.values())
    eleitos.sort(key=lambda e: (ordem.index(e["cargo"]), e["uf"], -e["votos"], e["sq"]))
    return {
        "fonte": fonte,
        "data_base": max(datas).isoformat() if datas else None,
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "eleitos": eleitos,
    }


def main():
    out = montar(DADOS, UFS)
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    por_cargo = {}
    for e in out["eleitos"]:
        por_cargo[e["cargo"]] = por_cargo.get(e["cargo"], 0) + 1
    print(f"{len(out['eleitos'])} eleitos {por_cargo} -> {SAIDA}")


if __name__ == "__main__":
    main()
