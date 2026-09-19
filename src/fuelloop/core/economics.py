"""Экономика: платежи по каналам, резервные тарифы, дисконтирование."""


def channel_variable_payment(price: float, ordered: float, top_share: float, reserved: float) -> float:
    billable = max(ordered, top_share * reserved)
    return price * billable


def reserve_payment(reserve_rate: float, reserved: float, year_fraction: float = 1.0) -> float:
    return reserve_rate * reserved * year_fraction


def npv(flows: list[tuple[float, float]], rate: float) -> float:
    return sum(amount / (1.0 + rate) ** t for t, amount in flows)
