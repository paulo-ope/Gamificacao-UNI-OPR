"""Normaliza nomes de atendentes do SGP Suporte ja importados, usando a dimensao
`user` do OPA Suite (`support_opa_dimensions`) como fonte de verdade.

Por que existe
--------------
`_normalize_attendance` (opa_ingestion.py) ja resolve o nome do atendente pela
dimensao `user` quando a API do OPA nao manda um nome legivel. Esse fallback,
porem, so entra quando o campo de nome vem VAZIO. Quando a API devolve o proprio
`id_atendente` no lugar do nome -- ou quando o atendimento foi importado antes da
dimensao de usuarios existir localmente -- o id fica gravado em `attendant_name` e
aparece cru na tela (ranking, tabela, filtros e detalhe leem essa coluna direto).

Esse e o estado observado na VM. O ambiente local, que importou depois das
dimensoes estarem sincronizadas, nao tem o problema.

O que este script NAO faz
-------------------------
- Nao chama a API do OPA Suite (trabalha 100% com dado local ja gravado).
- Nao dispara importacao.
- Nao altera `attendant_id`, `raw_payload`, TMA, TMR nem qualquer metrica.
- Nao sobrescreve nome humano valido: so mexe onde o nome esta vazio/nulo ou e
  literalmente igual ao `attendant_id`.
- Nao instala nada: usa apenas dependencias que ja estao na imagem do backend.

Idempotencia
------------
A correcao exige que o nome vindo da dimensao seja DIFERENTE do id. Sem essa
guarda, um atendente cuja dimensao tambem guarda o id como nome seria "corrigido"
de id para id em toda execucao, e o script reportaria trabalho pendente pra
sempre. Rodar duas vezes seguidas deve atualizar 0 na segunda.

Uso (dentro do container do backend, sem instalar nada)
-------------------------------------------------------
    docker compose exec -T backend python scripts/fix_opa_attendant_names.py --dry-run
    docker compose exec -T backend python scripts/fix_opa_attendant_names.py --apply

`--dry-run` e o padrao: rodar sem argumento nenhum NAO grava nada.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Rodando como `python scripts/fix_opa_attendant_names.py`, o Python coloca
# /app/scripts em sys.path[0] -- e nao /app --, entao `import app` falharia.
# Este bootstrap deixa as duas formas de chamada funcionarem (caminho e `-m`),
# pra que a VM nao precise de PYTHONPATH nem de nenhum ajuste de ambiente.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import and_, exists, func, or_, select  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.modules.support.models import SupportOpaAttendance, SupportOpaDimension  # noqa: E402
from app.modules.support.opa_ingestion import backfill_attendant_names  # noqa: E402

SAMPLE_LIMIT = 10


def _usable_dimension():
    """Dimensao `user` que realmente traduz o id num nome legivel."""
    return exists().where(
        and_(
            SupportOpaDimension.dimension_type == "user",
            SupportOpaDimension.source_id == SupportOpaAttendance.attendant_id,
            SupportOpaDimension.name.isnot(None),
            SupportOpaDimension.name != "",
            SupportOpaDimension.name != SupportOpaAttendance.attendant_id,
        )
    )


def _needs_fix():
    """Nome ausente ou igual ao id -- os dois casos que devem ser normalizados."""
    return and_(
        SupportOpaAttendance.attendant_id.isnot(None),
        SupportOpaAttendance.attendant_id != "",
        or_(
            SupportOpaAttendance.attendant_name.is_(None),
            SupportOpaAttendance.attendant_name == "",
            SupportOpaAttendance.attendant_name == SupportOpaAttendance.attendant_id,
        ),
    )


def _count(db, *conditions) -> int:
    statement = select(func.count(SupportOpaAttendance.id))
    if conditions:
        statement = statement.where(*conditions)
    return int(db.scalar(statement) or 0)


def diagnose(db) -> dict[str, int]:
    total = _count(db)
    com_id = _count(db, SupportOpaAttendance.attendant_id.isnot(None), SupportOpaAttendance.attendant_id != "")
    nome_igual_id = _count(
        db,
        SupportOpaAttendance.attendant_id.isnot(None),
        SupportOpaAttendance.attendant_name == SupportOpaAttendance.attendant_id,
    )
    nome_vazio = _count(
        db,
        SupportOpaAttendance.attendant_id.isnot(None),
        SupportOpaAttendance.attendant_id != "",
        or_(SupportOpaAttendance.attendant_name.is_(None), SupportOpaAttendance.attendant_name == ""),
    )
    dimensoes = int(
        db.scalar(
            select(func.count(SupportOpaDimension.id)).where(SupportOpaDimension.dimension_type == "user")
        )
        or 0
    )
    corrigiveis = _count(db, _needs_fix(), _usable_dimension())
    # Precisa de correcao mas nao ha dimensao que traduza o id: o script nao
    # inventa nome -- fica pendente ate a dimensao ser sincronizada.
    pendentes = _count(db, _needs_fix(), ~_usable_dimension())
    return {
        "total_atendimentos": total,
        "com_attendant_id": com_id,
        "nome_igual_ao_id": nome_igual_id,
        "nome_vazio": nome_vazio,
        "dimensoes_user": dimensoes,
        "corrigiveis": corrigiveis,
        "pendentes_sem_dimensao": pendentes,
    }


def _pending_sample(db) -> list[tuple[str, int]]:
    """Amostra de ids pendentes com a contagem de atendimentos afetados.

    Devolve apenas `attendant_id` e quantidade -- nenhum dado de cliente,
    protocolo ou conteudo de atendimento (AGENTS.md: logs sem dado sensivel).
    """
    rows = db.execute(
        select(SupportOpaAttendance.attendant_id, func.count(SupportOpaAttendance.id).label("total"))
        .where(_needs_fix(), ~_usable_dimension())
        .group_by(SupportOpaAttendance.attendant_id)
        .order_by(func.count(SupportOpaAttendance.id).desc())
        .limit(SAMPLE_LIMIT)
    ).all()
    return [(str(row[0]), int(row[1])) for row in rows]


def _fmt(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def _print_diagnosis(titulo: str, dados: dict[str, int]) -> None:
    print(f"\n=== {titulo} ===")
    print(f"  Total de atendimentos................. {_fmt(dados['total_atendimentos']):>9}")
    print(f"  Com attendant_id...................... {_fmt(dados['com_attendant_id']):>9}")
    print(f"  Com attendant_name == attendant_id.... {_fmt(dados['nome_igual_ao_id']):>9}")
    print(f"  Com attendant_name vazio/nulo......... {_fmt(dados['nome_vazio']):>9}")
    print(f"  Dimensoes OPA (user).................. {_fmt(dados['dimensoes_user']):>9}")
    print(f"  Corrigiveis (tem dimensao usavel)..... {_fmt(dados['corrigiveis']):>9}")
    print(f"  Pendentes (sem dimensao).............. {_fmt(dados['pendentes_sem_dimensao']):>9}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Normaliza attendant_name do SGP Suporte pela dimensao `user` do OPA.",
    )
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument(
        "--dry-run",
        action="store_true",
        help="So diagnostica e mostra o que seria alterado (padrao).",
    )
    grupo.add_argument(
        "--apply",
        action="store_true",
        help="Aplica a correcao e faz commit.",
    )
    args = parser.parse_args(argv)
    aplicar = bool(args.apply)

    db = SessionLocal()
    try:
        antes = diagnose(db)
        _print_diagnosis("DIAGNOSTICO ANTES", antes)

        pendentes = _pending_sample(db)
        if pendentes:
            print(f"\n  Amostra de atendentes pendentes (top {len(pendentes)} por volume):")
            for attendant_id, total in pendentes:
                print(f"    - attendant_id={attendant_id}  atendimentos={total}")
            print("    Motivo: nao ha dimensao `user` com nome legivel para esses ids.")
            print("    Acao: sincronizar dimensoes do OPA e rodar este script de novo.")

        if not aplicar:
            print("\n>>> DRY-RUN: nenhuma alteracao gravada.")
            print(f">>> Seriam atualizados: {antes['corrigiveis']} atendimento(s).")
            if antes["corrigiveis"]:
                print(">>> Para aplicar: python scripts/fix_opa_attendant_names.py --apply")
            return 0

        atualizados = backfill_attendant_names(db)
        db.commit()
        print(f"\n>>> APPLY: {atualizados} atendimento(s) atualizado(s).")

        depois = diagnose(db)
        _print_diagnosis("DIAGNOSTICO DEPOIS", depois)
        if depois["corrigiveis"]:
            # Nao deveria sobrar nada corrigivel: se sobrou, algo na condicao
            # divergiu entre a contagem e o UPDATE -- vale investigar antes de
            # confiar no resultado.
            print(f"\n  ATENCAO: ainda restam {depois['corrigiveis']} corrigiveis apos o apply.")
            return 1
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
