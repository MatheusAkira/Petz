"""Contrato de consulta: get_order(numero, Session) -> ApiResult.

Identidade vem do chamador confiável, nunca de argumentos gerados pelo modelo.
200: pedido sem PII; 403: acesso recusado; 404: inexistente; 503: indisponível.
Nenhuma operação de escrita. Falha via fail=True ou pedido 9999.
"""
import json
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class Session:
    customer_id: str

@dataclass
class ApiResult:
    status: int
    data: dict

class OrderAPI:
    def __init__(self, fail=False):
        self.fail = fail
        self.orders = json.loads((Path(__file__).parent / 'pedidos.json').read_text(encoding='utf-8'))

    def get_order(self, number: str, session: Session) -> ApiResult:
        if self.fail or number == '9999':
            return ApiResult(503, {'error': 'temporarily_unavailable'})
        order = next((o for o in self.orders if o['numero'] == number), None)
        if order is None:
            return ApiResult(404, {'error': 'not_found'})
        if order['cliente_id'] != session.customer_id:
            return ApiResult(403, {'error': 'access_denied'})
        return ApiResult(200, {k:v for k,v in order.items() if k != 'cliente_id'})
