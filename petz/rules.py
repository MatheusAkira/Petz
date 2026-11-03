"""Regras puras; limites inclusivos de dias e exclusivos de valor."""
from datetime import date
from decimal import Decimal

# Verifica frete grátis acima de R$ 149 no Sul/Sudeste ou R$ 249 nas demais regiões.
def shipping_threshold(region):
    return Decimal('149') if region in {'Sul', 'Sudeste'} else Decimal('249')

def free_shipping(total, region):
    return Decimal(str(total)) > shipping_threshold(region)

# Verifica os prazos de devolução: até 7 dias por arrependimento ou 30 por defeito.
# Ração e areia abertas só são elegíveis por defeito; datas futuras são recusadas.
def return_eligible(delivered: date, today: date, reason: str, category: str, opened: bool):
    days = (today - delivered).days
    if days < 0:
        return False
    if opened and category in {'racao', 'areia'} and reason != 'defeito':
        return False
    return days <= (30 if reason == 'defeito' else 7)

# Permite solicitar cancelamento apenas nos status Pago e Em separação.
def cancellable(status):
    return status in {'Pago', 'Em separação'}
