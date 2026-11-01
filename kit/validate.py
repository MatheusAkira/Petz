"""Validação independente do gerador. Execute python -m kit.validate."""
import csv
import json
from datetime import date
from pathlib import Path

def validate():
    root = Path(__file__).parent
    docs = list((root / 'politicas').glob('*.md'))
    assert len(docs) == 8
    for p in docs:
        assert 150 <= len(p.read_text(encoding='utf-8').split()) <= 400, p.name
    with (root / 'catalogo.csv').open(encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        assert set(reader.fieldnames) == {'SKU','nome','categoria','especie','preco','estoque','descricao'}
        products = list(reader)
    assert 40 <= len(products) <= 60
    skus = {p['SKU'] for p in products}
    assert len(skus) == len(products)
    assert all(float(p['preco']) > 0 and int(p['estoque']) >= 0 for p in products)
    assert {'cao','gato'} <= {p['especie'] for p in products}
    assert {'racao','areia'} <= {p['categoria'] for p in products}
    assert any(int(p['estoque']) == 0 for p in products)
    orders = json.loads((root / 'pedidos.json').read_text(encoding='utf-8'))
    assert 8 <= len(orders) <= 10 and len({o['numero'] for o in orders}) == len(orders)
    assert len({o['cliente_id'] for o in orders}) >= 3
    assert {'Pago','Em separação','Enviado','Entregue','Cancelado'} <= {o['status'] for o in orders}
    assert all(i['sku'] in skus and i['quantidade'] > 0 for o in orders for i in o['itens'])
    ages = [(date(2026,10,29)-date.fromisoformat(o['entregue_em'])).days for o in orders if o['entregue_em']]
    assert any(0 <= a < 7 for a in ages) and any(8 <= a <= 30 for a in ages)
    assert all((o['status'] == 'Entregue') == bool(o['entregue_em']) for o in orders)
    print(f'Kit válido: {len(docs)} políticas, {len(products)} SKUs, {len(orders)} pedidos.')

if __name__ == '__main__':
    validate()
