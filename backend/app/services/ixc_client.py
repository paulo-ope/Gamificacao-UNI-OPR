from __future__ import annotations

import base64
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Iterator

import httpx

from app.core.config import get_settings

# Log de auditoria de TODA requisição feita ao webservice do IXC (tabela, página, tamanho de página,
# filtros, quantidade de registros devolvidos e duração) - pedido do dono do produto pra ter
# comprovação concreta do volume de consultas e garantir que a integração não está sobrecarregando o
# IXC. Nível INFO de propósito (não é erro), fica registrado no log do container do backend.
logger = logging.getLogger("ixc_client")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


class IxcApiError(RuntimeError):
    """Erro de comunicação com o webservice v1 do IXC (rede, autenticação ou formato de resposta)."""


class IxcQueryLimitError(IxcApiError):
    """Consulta filtrada que excede o limite de segurança definido pelo consumidor."""


@dataclass
class IxcPage:
    records: list[dict[str, Any]]
    total: int
    page: int


class IxcClient:
    """Cliente HTTP puro para o webservice v1 do IXC.

    Não contém lógica de negócio da gamificação (matching, auditoria, bloqueio de período pago etc.) -
    só autenticação, paginação e leitura das tabelas brutas. Essa separação é intencional (ver
    docs/plano-integracao-ixc.md, Fase A): o adaptador que liga isso ao pipeline de importação existente
    vem depois, num módulo próprio.
    """

    def __init__(self, base_url: str, token: str, verify_ssl: bool = True, timeout: float = 30.0) -> None:
        if not base_url:
            raise IxcApiError("IXC_API_BASE_URL não configurado.")
        if not token:
            raise IxcApiError("IXC_API_TOKEN não configurado.")
        self._base_url = base_url.rstrip("/")
        self._auth_header = "Basic " + base64.b64encode(token.encode("utf-8")).decode("ascii")
        self._verify_ssl = verify_ssl
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self._auth_header,
            "Content-Type": "application/json",
            "ixcsoft": "listar",
        }

    def list(
        self,
        table: str,
        *,
        grid_param: list[dict[str, str]] | None = None,
        page: int = 1,
        rp: int = 100,
        sortname: str | None = None,
        sortorder: str = "asc",
    ) -> IxcPage:
        payload: dict[str, Any] = {"page": str(page), "rp": str(rp)}
        if grid_param:
            payload["grid_param"] = json.dumps(grid_param, ensure_ascii=False)
        if sortname:
            payload["sortname"] = sortname
            payload["sortorder"] = sortorder

        def safe_filter_summary(item: dict[str, str]) -> str:
            operator = str(item.get("OP") or "")
            raw_value = str(item.get("P") or "")
            if operator.upper() == "IN":
                count = len([value for value in raw_value.split(",") if value])
                return f"{item.get('TB')} IN [{count} valores]"
            return f"{item.get('TB')} {operator} {raw_value}"

        filters_summary = ", ".join(safe_filter_summary(item) for item in (grid_param or []))
        started_at = time.monotonic()
        try:
            response = httpx.post(
                f"{self._base_url}/webservice/v1/{table}",
                headers=self._headers(),
                json=payload,
                timeout=self._timeout,
                verify=self._verify_ssl,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            duration_ms = round((time.monotonic() - started_at) * 1000)
            logger.warning(
                "FALHA tabela=%s pagina=%s rp=%s filtros=[%s] duracao_ms=%s erro=%s",
                table, page, rp, filters_summary, duration_ms, exc,
            )
            raise IxcApiError(f"Falha ao consultar '{table}' no IXC: {exc}") from exc

        try:
            body = response.json()
        except ValueError as exc:
            duration_ms = round((time.monotonic() - started_at) * 1000)
            content_type = response.headers.get("content-type", "não informado").split(";", 1)[0]
            logger.warning(
                "RESPOSTA_INVALIDA tabela=%s pagina=%s rp=%s filtros=[%s] status=%s content_type=%s duracao_ms=%s",
                table, page, rp, filters_summary, response.status_code, content_type, duration_ms,
            )
            raise IxcApiError(
                f"O IXC respondeu em formato inválido para '{table}' "
                f"(HTTP {response.status_code}, tipo {content_type}). Tente novamente em alguns instantes."
            ) from exc
        if not isinstance(body, dict) or ("registros" not in body and "total" not in body):
            keys = list(body.keys()) if isinstance(body, dict) else type(body).__name__
            raise IxcApiError(f"Resposta inesperada do IXC para '{table}' (chaves recebidas: {keys}).")

        # Quando não há nenhum registro no filtro, o IXC omite 'registros' inteiramente (só devolve
        # page/total) - trata isso como lista vazia, não como erro.
        records = body.get("registros") or []
        total = int(body.get("total") or len(records))
        duration_ms = round((time.monotonic() - started_at) * 1000)
        logger.info(
            "tabela=%s pagina=%s rp=%s filtros=[%s] registros_recebidos=%s total_no_filtro=%s duracao_ms=%s",
            table, page, rp, filters_summary, len(records), total, duration_ms,
        )
        return IxcPage(records=records, total=total, page=page)

    def list_all(
        self,
        table: str,
        *,
        grid_param: list[dict[str, str]] | None = None,
        rp: int = 100,
        sortname: str | None = None,
        sortorder: str = "asc",
        max_pages: int = 1000,
        max_records: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Itera todos os registros de uma tabela, paginando até a lista de registros vir vazia.

        Não confia cegamente no `rp` pedido ser respeitado pelo servidor (observado na prática que o
        IXC às vezes devolve mais registros do que o solicitado) - a parada é decidida por página vazia
        ou por `max_pages`, nunca por assumir `len(records) == rp`.
        """
        page = 1
        seen = 0
        while page <= max_pages:
            result = self.list(table, grid_param=grid_param, page=page, rp=rp, sortname=sortname, sortorder=sortorder)
            if max_records is not None and result.total > max_records:
                raise IxcQueryLimitError(
                    f"A consulta filtrada de '{table}' retornaria {result.total} registros, "
                    f"acima do limite seguro de {max_records}. Reduza o período selecionado."
                )
            if not result.records:
                return
            yield from result.records
            seen += len(result.records)
            if result.total and seen >= result.total:
                return
            page += 1


def get_ixc_client() -> IxcClient:
    settings = get_settings()
    return IxcClient(
        base_url=settings.ixc_api_base_url,
        token=settings.ixc_api_token,
        verify_ssl=settings.ixc_api_verify_ssl,
    )


def fetch_latest_service_order_timestamp(client: IxcClient) -> str | None:
    """Retorna o `ultima_atualizacao` da O.S. mais recente do IXC (relógio do próprio IXC, não o nosso -
    o servidor do IXC grava datas em horário local, não UTC, então não dá pra confiar no nosso relógio
    para calcular janelas de tempo relativas ao dado dele)."""
    page = client.list("su_oss_chamado", page=1, rp=1, sortname="su_oss_chamado.id", sortorder="desc")
    if not page.records:
        return None
    return page.records[0].get("ultima_atualizacao") or page.records[0].get("data_abertura")


def _build_service_order_grid_param(
    *,
    opened_after: str | None = None,
    opened_before: str | None = None,
    closed_after: str | None = None,
    closed_before: str | None = None,
    updated_after: str | None = None,
    updated_before: str | None = None,
    setor_ids: list[str] | None = None,
    only_finalized: bool = False,
    statuses: list[str] | None = None,
    id_after: int | None = None,
    id_before: int | None = None,
) -> list[dict[str, str]]:
    grid_param: list[dict[str, str]] = []
    if opened_after:
        grid_param.append({"TB": "su_oss_chamado.data_abertura", "OP": ">=", "P": opened_after})
    if opened_before:
        grid_param.append({"TB": "su_oss_chamado.data_abertura", "OP": "<=", "P": opened_before})
    if closed_after:
        grid_param.append({"TB": "su_oss_chamado.data_fechamento", "OP": ">=", "P": closed_after})
    if closed_before:
        grid_param.append({"TB": "su_oss_chamado.data_fechamento", "OP": "<=", "P": closed_before})
    if updated_after:
        grid_param.append({"TB": "su_oss_chamado.ultima_atualizacao", "OP": ">=", "P": updated_after})
    if updated_before:
        grid_param.append({"TB": "su_oss_chamado.ultima_atualizacao", "OP": "<=", "P": updated_before})
    if setor_ids:
        grid_param.append({
            "TB": "su_oss_chamado.setor",
            "OP": "=" if len(setor_ids) == 1 else "IN",
            "P": setor_ids[0] if len(setor_ids) == 1 else ",".join(setor_ids),
        })
    if only_finalized:
        grid_param.append({"TB": "su_oss_chamado.status", "OP": "=", "P": "F"})
    elif statuses:
        # O IXC desta instalação retorna uma página de erro quando recebe
        # `status IN` com um único valor. O operador simples preserva o mesmo
        # recorte e evita essa falha do webservice.
        grid_param.append({
            "TB": "su_oss_chamado.status",
            "OP": "=" if len(statuses) == 1 else "IN",
            "P": statuses[0] if len(statuses) == 1 else ",".join(statuses),
        })
    if id_after is not None:
        grid_param.append({"TB": "su_oss_chamado.id", "OP": ">=", "P": str(id_after)})
    if id_before is not None:
        grid_param.append({"TB": "su_oss_chamado.id", "OP": "<=", "P": str(id_before)})
    return grid_param


def fetch_service_orders(
    client: IxcClient,
    *,
    opened_after: str | None = None,
    opened_before: str | None = None,
    closed_after: str | None = None,
    closed_before: str | None = None,
    updated_after: str | None = None,
    updated_before: str | None = None,
    setor_ids: list[str] | None = None,
    only_finalized: bool = False,
    statuses: list[str] | None = None,
    id_after: int | None = None,
    id_before: int | None = None,
    rp: int = 200,
    max_records: int | None = None,
) -> Iterator[dict[str, Any]]:
    """Busca O.S. do IXC.

    `updated_after` filtra por `ultima_atualizacao` (pega tanto O.S. novas quanto já existentes que
    mudaram - ex: uma que estava aberta e foi fechada) - é o campo certo para sincronização incremental.
    `updated_before` fecha essa janela por cima com um instante fixo capturado ANTES de começar a paginar
    (ver `sync_ixc_service_orders`) - sem isso, uma O.S. cujo `ultima_atualizacao` passa a satisfazer o
    filtro EM QUANTO a busca ainda está paginando pode cair numa página já lida (paginação por
    offset/página, não por cursor) e ser perdida pra sempre, já que a próxima sincronização só olha pra
    frente a partir da marca d'água (achado real: 2 O.S. de Nova Brasilândia D'Oeste fecharam durante a
    janela de uma sincronização e nunca mais apareceram - ver docs/plano-integracao-ixc.md).
    `opened_after`/`opened_before` filtram por `data_abertura`; `closed_after`/`closed_before` filtram por
    `data_fechamento` - use os de fechamento para importação retroativa de um período específico (ex.: um
    mês fechado no passado), porque a apuração agrupa O.S. pelo mês em que FECHARAM, não em que abriram.
    Uma O.S. aberta no fim de um mês e fechada só no início do seguinte fica de fora do backfill do mês de
    abertura se filtrar por `data_abertura` (achado real: 4 O.S. abertas em 31/05 e fechadas em 01/06 só
    apareceram depois que o backfill passou a usar `data_fechamento` - ver docs/plano-integracao-ixc.md).
    `setor_ids` filtra por `su_oss_chamado.setor` (o departamento/equipe do IXC, ex. "9" = Suporte Externo
    Fibra) - usado para restringir a importação só aos setores de campo que interessam à gamificação,
    evitando trazer O.S. administrativas/comerciais que nunca vão pontuar (ver
    `ixc_importer.IXC_TECHNICAL_SETOR_IDS`). `only_finalized` filtra por `su_oss_chamado.status = 'F'` -
    decisão do dono do produto: uma O.S ainda "Em andamento" pode trocar de colaborador (`id_tecnico`) até
    fechar, então só traz pra dentro do sistema quando já está definitiva (ver
    docs/plano-integracao-ixc.md). `id_after`/`id_before` filtram por `su_oss_chamado.id` (campo estável e
    sequencial) - usado só para particionar uma consulta que sozinha excederia `max_records` em fatias
    menores (ver `ixc_ingestion._fetch_id_range_partitioned`), nunca para filtro de negócio. Todos os
    filtros passados são combinados com E.
    """
    grid_param = _build_service_order_grid_param(
        opened_after=opened_after,
        opened_before=opened_before,
        closed_after=closed_after,
        closed_before=closed_before,
        updated_after=updated_after,
        updated_before=updated_before,
        setor_ids=setor_ids,
        only_finalized=only_finalized,
        statuses=statuses,
        id_after=id_after,
        id_before=id_before,
    )
    yield from client.list_all(
        "su_oss_chamado",
        grid_param=grid_param or None,
        rp=rp,
        sortname="su_oss_chamado.id",
        sortorder="asc",
        max_records=max_records,
    )


def fetch_service_order_id_bounds(
    client: IxcClient,
    *,
    setor_ids: list[str] | None = None,
    statuses: list[str] | None = None,
    only_finalized: bool = False,
) -> tuple[int, int] | None:
    """Descobre o menor e o maior `su_oss_chamado.id` que satisfazem o filtro passado, sem aplicar
    limite de segurança (usa `rp=1`, então nunca levanta `IxcQueryLimitError`) - usado só para saber
    onde bissectar uma consulta grande por faixa de id, sem precisar conhecer o total antecipadamente.
    Retorna None quando o filtro não encontra nenhum registro.
    """
    grid_param = _build_service_order_grid_param(
        setor_ids=setor_ids, statuses=statuses, only_finalized=only_finalized,
    )
    first_page = client.list(
        "su_oss_chamado", grid_param=grid_param or None, page=1, rp=1,
        sortname="su_oss_chamado.id", sortorder="asc",
    )
    if not first_page.records:
        return None
    last_page = client.list(
        "su_oss_chamado", grid_param=grid_param or None, page=1, rp=1,
        sortname="su_oss_chamado.id", sortorder="desc",
    )
    try:
        min_id = int(first_page.records[0]["id"])
        max_id = int(last_page.records[0]["id"])
    except (KeyError, TypeError, ValueError):
        return None
    return (min_id, max_id)


def fetch_assuntos(client: IxcClient) -> Iterator[dict[str, Any]]:
    yield from client.list_all("su_oss_assunto", sortname="su_oss_assunto.id")


def fetch_diagnosticos(client: IxcClient) -> Iterator[dict[str, Any]]:
    yield from client.list_all("su_diagnostico", sortname="su_diagnostico.id")


def fetch_funcionarios(client: IxcClient) -> Iterator[dict[str, Any]]:
    yield from client.list_all("funcionarios", sortname="funcionarios.id")


def fetch_funcionarios_by_ids(client: IxcClient, funcionario_ids: list[int], *, rp: int = 200) -> Iterator[dict[str, Any]]:
    """Resolve `id_tecnico` (funcionários/RH, referenciado nas O.S. como técnico de campo) para
    nome, sem precisar buscar a tabela inteira (~800+ registros) toda vez que um id novo aparece."""
    if not funcionario_ids:
        return
    grid_param = [{"TB": "funcionarios.id", "OP": "IN", "P": ",".join(str(fid) for fid in funcionario_ids)}]
    yield from client.list_all("funcionarios", grid_param=grid_param, rp=rp, sortname="funcionarios.id")


def fetch_cidades(client: IxcClient) -> Iterator[dict[str, Any]]:
    yield from client.list_all("cidade", sortname="cidade.id")


def fetch_setores(client: IxcClient) -> Iterator[dict[str, Any]]:
    yield from client.list_all("empresa_setor", sortname="empresa_setor.id")


def fetch_logins_by_ids(client: IxcClient, login_ids: list[int], *, rp: int = 200) -> Iterator[dict[str, Any]]:
    if not login_ids:
        return
    grid_param = [{"TB": "radusuarios.id", "OP": "IN", "P": ",".join(str(lid) for lid in login_ids)}]
    yield from client.list_all("radusuarios", grid_param=grid_param, rp=rp, sortname="radusuarios.id")


def fetch_onu_signal_by_login_ids(client: IxcClient, login_ids: list[int], *, rp: int = 200) -> Iterator[dict[str, Any]]:
    """Telemetria de sinal óptico/ONU (transmissor, sinal RX/TX em dBm, serial da ONU, causa da
    última queda) - tabela `radpop_radio_cliente_fibra`, achada por sondagem manual contra a API
    real (não documentada publicamente pelo IXC; é a fonte da aba "Cliente Fibra (ONU)" da tela de
    login). Não varre a tabela inteira (~90 mil linhas) de propósito - só os logins que o chamador
    já monitora (ver `operations/onu_signal_snapshot.py`), para não sobrecarregar a API do IXC."""
    if not login_ids:
        return
    grid_param = [{"TB": "radpop_radio_cliente_fibra.id_login", "OP": "IN", "P": ",".join(str(lid) for lid in login_ids)}]
    yield from client.list_all(
        "radpop_radio_cliente_fibra", grid_param=grid_param, rp=rp, sortname="radpop_radio_cliente_fibra.id_login"
    )


LOGIN_STATUS_SNAPSHOT_FIELDS = (
    "id",
    "login",
    "online",
    "latitude",
    "longitude",
    "ultima_conexao_inicial",
    "ultima_conexao_final",
)


def fetch_login_status_snapshot(client: IxcClient, *, rp: int = 500) -> Iterator[dict[str, Any]]:
    """Varre todos os logins ativos (`radusuarios.ativo = 'S'`) trazendo só os campos usados pelo
    histórico de status/geolocalização (`LOGIN_STATUS_SNAPSHOT_FIELDS`) - filtrado por ativo pra não
    varrer também os ~30 mil logins de contrato encerrado/cancelado que compõem o restante da tabela
    (confirmado em produção: 88079 ativos de ~120060 no total)."""
    grid_param = [{"TB": "radusuarios.ativo", "OP": "=", "P": "S"}]
    yield from client.list_all("radusuarios", grid_param=grid_param, rp=rp, sortname="radusuarios.id")


def fetch_clientes_by_ids(client: IxcClient, cliente_ids: list[int], *, rp: int = 200) -> Iterator[dict[str, Any]]:
    if not cliente_ids:
        return
    grid_param = [{"TB": "cliente.id", "OP": "IN", "P": ",".join(str(cid) for cid in cliente_ids)}]
    yield from client.list_all("cliente", grid_param=grid_param, rp=rp, sortname="cliente.id")


def fetch_usuarios_by_ids(client: IxcClient, usuario_ids: list[int], *, rp: int = 200) -> Iterator[dict[str, Any]]:
    """Resolve `id_operador` (login interno do sistema IXC, tabela `usuarios`) para nome/e-mail.

    Distinto de `fetch_funcionarios` (`funcionarios.id`, o cadastro de RH/técnico de campo,
    referenciado por `id_tecnico`) - `usuarios` é quem efetivamente loga no sistema e realiza ações
    como agendar uma O.S.
    """
    if not usuario_ids:
        return
    grid_param = [{"TB": "usuarios.id", "OP": "IN", "P": ",".join(str(uid) for uid in usuario_ids)}]
    yield from client.list_all("usuarios", grid_param=grid_param, rp=rp, sortname="usuarios.id")
