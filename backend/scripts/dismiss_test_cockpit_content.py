"""Oculta da TV publicações de teste (`opr_publish_cockpit_content` usado para validar a conexão
MCP, ex.: "Teste de conexão", "Teste de publicação") que ficaram com status ACTIVE misturadas com
conteúdo operacional real - achado real 2026-08-24, ver conversa sobre hierarquia visual do
cockpit.

Não apaga nada: reaproveita `dismiss_cockpit_content` (mesma função usada pelo botão "Dismiss" de
Administração → Publicações), que só muda `status` para DISMISSED - `_content_query` (o que a TV
vê) já filtra por status ACTIVE, então isso é suficiente pra sair da tela sem perder o histórico.

Casa por título (case-insensitive) numa lista fechada de termos de teste - evita casar publicações
reais que só citem a palavra "teste" no meio do corpo (ex.: "período de teste da nova ONU").

Uso (dentro do container do backend, como módulo):

    # 1. Sempre rode em modo dry-run primeiro e leia a lista antes de aplicar:
    docker exec opr-gamification-backend python -m scripts.dismiss_test_cockpit_content

    # 2. Só quando estiver de acordo com o que seria ocultado:
    docker exec opr-gamification-backend python -m scripts.dismiss_test_cockpit_content --apply
"""
from __future__ import annotations

import argparse

import app.main  # noqa: F401 - registra todos os mappers antes de qualquer query
from app.db.session import SessionLocal
from app.modules.intelligence.cockpit import dismiss_cockpit_content, list_cockpit_content

TEST_TITLE_PREFIXES = (
    "teste de conexão",
    "teste de conex",  # variação sem acentuação
    "teste de publicação",
    "teste de publica",  # variação sem acentuação
    "connection test",
    "test publish",
)


def is_test_content(title: str) -> bool:
    normalized = title.strip().lower()
    return normalized.startswith(TEST_TITLE_PREFIXES)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Aplica de fato (sem isso, só mostra o que seria ocultado).")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        active = list_cockpit_content(db, status="ACTIVE", limit=1000)
        targets = [row for row in active if is_test_content(row.title)]

        if not targets:
            print("Nenhuma publicação de teste ACTIVE encontrada.")
            return

        print(f"{len(targets)} publicação(ões) de teste encontrada(s):")
        for row in targets:
            print(f"  #{row.id} [{row.content_type}] {row.title!r} (source_key={row.source_key!r}, criado em {row.created_at})")

        if not args.apply:
            print("\nModo dry-run - nenhuma alteração feita. Rode novamente com --apply para ocultar.")
            return

        for row in targets:
            dismiss_cockpit_content(db, row)
        print(f"\n{len(targets)} publicação(ões) marcada(s) como DISMISSED.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
