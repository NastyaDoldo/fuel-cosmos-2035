"""Материальный баланс хранилища с внутригодовыми шагами."""


def run_balance(
    start_stock: float,
    inflow_total: float,
    loss_rate: float,
    demand_total: float,
    capacity: float,
    steps: int,
    days_per_year: float,
) -> dict:
    if steps < 1:
        raise ValueError("steps >= 1")
    per_step_days = days_per_year / steps
    d_step = demand_total / steps
    i_step = inflow_total / steps

    stock = start_stock
    served = 0.0
    deficit = 0.0
    losses = 0.0
    stock_min = stock
    stock_max = stock
    overflow_events = 0
    overflow_max = 0.0
    post_receipt_peak = stock
    stock_days_sum = 0.0

    for _ in range(steps):
        loss = i_step * loss_rate
        losses += loss
        post = stock + i_step - loss
        post_receipt_peak = max(post_receipt_peak, post)
        if post > capacity + 1e-9:
            overflow_events += 1
            overflow_max = max(overflow_max, post - capacity)
        available = post
        issued = min(available, d_step)
        served += issued
        deficit += d_step - issued
        if available < d_step:
            avg_step = available * available / (2.0 * d_step) if d_step > 0 else available
        else:
            avg_step = available - d_step / 2.0
        stock_days_sum += avg_step * per_step_days
        stock = available - issued
        stock_min = min(stock_min, stock)
        stock_max = max(stock_max, stock)

    return {
        "served": served,
        "deficit": deficit,
        "losses": losses,
        "stock_start": start_stock,
        "stock_end": stock,
        "stock_min": stock_min,
        "stock_max": stock_max,
        "stock_days_sum": stock_days_sum,
        "overflow_events": overflow_events,
        "overflow_max": overflow_max,
        "post_receipt_peak": post_receipt_peak,
    }
