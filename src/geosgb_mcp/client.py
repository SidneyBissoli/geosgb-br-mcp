"""Cliente HTTP para ArcGIS REST API do Serviço Geológico do Brasil."""

import asyncio
import httpx
from typing import Any

from .constants import BASE_URL as _BASE_URL, DEFAULT_TIMEOUT, ENDPOINTS as _ENDPOINTS


class GeoSGBClient:
    """Cliente para ArcGIS REST API do SGB.

    BASE_URL e ENDPOINTS vivem em constants.py (fonte única da verdade);
    aqui são apenas aliases de classe para conveniência dos chamadores.
    """

    BASE_URL = _BASE_URL

    ENDPOINTS = _ENDPOINTS

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = 3,
        retry_delay: float = 2.0,
    ):
        """
        Inicializa o cliente.

        Args:
            timeout: Timeout em segundos para requisições (constants.DEFAULT_TIMEOUT)
            max_retries: Número máximo de tentativas em caso de erro
            retry_delay: Delay em segundos entre tentativas
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Retorna o cliente HTTP, criando-o se necessário."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def _request_with_retry(
        self, url: str, params: dict[str, Any]
    ) -> httpx.Response:
        """
        Executa requisição com retry em caso de erro.

        Args:
            url: URL da requisição
            params: Parâmetros da query

        Returns:
            Resposta HTTP

        Raises:
            httpx.HTTPStatusError: Se todas as tentativas falharem
        """
        client = await self._get_client()
        last_error = None

        for attempt in range(self.max_retries):
            try:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as e:
                last_error = e
                # Retry apenas para erros 5xx (servidor)
                if e.response.status_code >= 500:
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(self.retry_delay * (attempt + 1))
                        continue
                raise
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue
                raise

        if last_error:
            raise last_error
        raise RuntimeError("Erro inesperado no retry")

    async def query(
        self,
        endpoint_key: str,
        where: str = "1=1",
        out_fields: str = "*",
        return_geometry: bool = True,
        geometry: tuple[float, float, float, float] | None = None,
        return_count_only: bool = False,
        f: str = "json",
    ) -> dict[str, Any]:
        """
        Executa query na ArcGIS REST API.

        Args:
            endpoint_key: Chave do endpoint (ex: "ocorrencias", "afloramentos")
            where: Cláusula SQL WHERE
            out_fields: Campos a retornar ("*" para todos)
            return_geometry: Se True, inclui geometria na resposta
            geometry: Bounding box (xmin, ymin, xmax, ymax) em WGS84
            return_count_only: Se True, retorna apenas contagem
            f: Formato de saída (json, geojson, pjson)

        Returns:
            Dicionário com a resposta da API

        Note:
            A API do SGB não suporta paginação (resultOffset/resultRecordCount).
            O limite de registros é aplicado no lado do cliente.

            A chave "litoestratigrafia_estados" aponta para a RAIZ do serviço
            (uma camada por estado, ids instáveis) e NÃO pode ser usada aqui
            diretamente — resolva a camada via ?f=json antes (ver constants.py).
        """
        endpoint = self.ENDPOINTS.get(endpoint_key)
        if not endpoint:
            raise ValueError(f"Endpoint desconhecido: {endpoint_key}")

        url = f"{self.BASE_URL}{endpoint}/query"

        params: dict[str, Any] = {
            "where": where,
            "f": f,
        }

        if return_count_only:
            params["returnCountOnly"] = "true"
        else:
            params["outFields"] = out_fields
            params["returnGeometry"] = str(return_geometry).lower()
            params["outSR"] = "4326"

        if geometry:
            xmin, ymin, xmax, ymax = geometry
            params["geometry"] = f"{xmin},{ymin},{xmax},{ymax}"
            params["geometryType"] = "esriGeometryEnvelope"
            params["spatialRel"] = "esriSpatialRelIntersects"
            params["inSR"] = "4326"

        response = await self._request_with_retry(url, params)
        return response.json()

    async def get_count(self, endpoint_key: str, where: str = "1=1") -> int:
        """
        Retorna contagem total de registros.

        Args:
            endpoint_key: Chave do endpoint
            where: Cláusula SQL WHERE

        Returns:
            Número total de registros
        """
        result = await self.query(
            endpoint_key=endpoint_key, where=where, return_count_only=True
        )
        return result.get("count", 0)

    async def close(self) -> None:
        """Fecha o cliente HTTP."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
