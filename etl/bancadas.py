"""Membros das bancadas estaduais (deputados federais + senadores por UF e legislatura).

Fontes: API de dados abertos da Câmara e do Senado. A emenda do exercício Y é
apresentada no ano Y-1, então vale a legislatura em curso em Y-1.
"""

from __future__ import annotations

import json
from pathlib import Path

import requests

from .download import HEADERS

CAMARA = "https://dadosabertos.camara.leg.br/api/v2/deputados"
SENADO = "https://legis.senado.leg.br/dadosabertos/senador/lista/legislatura/{leg}"


def legislatura_do_exercicio(ano: int) -> int:
    """Exercício 2024 -> emenda apresentada em 2023 -> 57ª legislatura (2023–2027)."""
    return 55 + (ano - 1 - 2015) // 4


def _deputados(leg: int) -> list[dict]:
    out, pagina = [], 1
    while True:
        r = requests.get(CAMARA, params={"idLegislatura": leg, "itens": 100, "pagina": pagina, "ordem": "ASC", "ordenarPor": "nome"},
                         headers={**HEADERS, "Accept": "application/json"}, timeout=60)
        r.raise_for_status()
        dados = r.json().get("dados", [])
        out += [{"n": d["nome"], "p": d.get("siglaPartido") or "", "uf": d.get("siglaUf") or "", "c": "D"} for d in dados]
        if len(dados) < 100:
            return out
        pagina += 1


def _senadores(leg: int) -> list[dict]:
    r = requests.get(SENADO.format(leg=leg), headers={**HEADERS, "Accept": "application/json"}, timeout=60)
    r.raise_for_status()
    lista = r.json().get("ListaParlamentarLegislatura", {}).get("Parlamentares", {}).get("Parlamentar", [])
    out = []
    for p in lista if isinstance(lista, list) else [lista]:
        i = p.get("IdentificacaoParlamentar", {})
        uf = i.get("UfParlamentar") or ""
        if not uf:  # a UF às vezes vem só no mandato
            m = p.get("Mandatos", {}).get("Mandato", {})
            m = m[0] if isinstance(m, list) else m
            uf = m.get("UfParlamentar", "")
        out.append({"n": i.get("NomeParlamentar", ""), "p": i.get("SiglaPartidoParlamentar", ""), "uf": uf, "c": "S"})
    return out


def gravar_bancadas(anos: list[int], destino: Path) -> None:
    """Grava bancadas.json: {legislatura: {UF: [membros]}}. Falha de rede não interrompe o build."""
    legs = sorted({legislatura_do_exercicio(a) for a in anos})
    resultado: dict[str, dict[str, list]] = {}
    for leg in legs:
        membros = []
        for nome, fn in (("Câmara", _deputados), ("Senado", _senadores)):
            try:
                membros += fn(leg)
            except (requests.RequestException, ValueError, KeyError) as erro:
                print(f"aviso: {nome}, legislatura {leg} indisponível ({type(erro).__name__})")
        por_uf: dict[str, list] = {}
        vistos = set()
        for m in membros:
            chave = (m["uf"], m["c"], m["n"])
            if m["uf"] and chave not in vistos:
                vistos.add(chave)
                por_uf.setdefault(m["uf"], []).append({k: m[k] for k in ("n", "p", "c")})
        if por_uf:
            resultado[str(leg)] = por_uf
    (destino / "bancadas.json").write_text(json.dumps(resultado, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    total = sum(len(v) for leg in resultado.values() for v in leg.values())
    print(f"bancadas: legislaturas {list(resultado)}, {total:,} membros")
