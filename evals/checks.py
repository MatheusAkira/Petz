"""Verifica??es determin?sticas usadas pela su?te unificada."""

def check(reply, expected, products):
    errors = []
    for key in ['route','eligible','days','status_code']:
        if key in expected:
            actual = reply.route if key == 'route' else reply.data.get(key)
            if actual != expected[key]: errors.append(f'{key}: esperado {expected[key]!r}; recebido {actual!r}')
    for text in expected.get('contains',[]):
        if text not in reply.text: errors.append(f'Texto ausente: {text}')
    for text in expected.get('not_contains',[]):
        if text in reply.text: errors.append(f'Exposição inesperada: {text}')
    if 'source' in expected and f"kit/politicas/{expected['source']}.md" not in reply.sources:
        errors.append('Fonte ausente')
    if 'species' in expected:
        skus = reply.data.get('skus',[])
        if not skus: errors.append('Recomendação vazia')
        for sku in skus:
            p = next((p for p in products if p['SKU'] == sku),None)
            if not p: errors.append('SKU inventado'); continue
            if p['especie'] != expected['species']: errors.append('Espécie incorreta')
            if p['categoria'] != expected['category']: errors.append('Categoria incorreta')
            if int(p['estoque']) <= 0: errors.append('Sem estoque')
            if float(p['preco']) > expected.get('budget',float('inf')): errors.append('Acima do orçamento')
    return errors
