from db import get_conn

with get_conn() as c:
    print("range:", tuple(c.execute(
        "SELECT MIN(arrival_date), MAX(arrival_date), COUNT(DISTINCT arrival_date) FROM mandi_prices"
    ).fetchone()))
    print("total:", c.execute("SELECT COUNT(*) FROM mandi_prices").fetchone()[0])
    for r in c.execute(
        "SELECT market, commodity, arrival_date, modal_price FROM mandi_prices "
        "WHERE market LIKE 'Parry%' ORDER BY arrival_date LIMIT 3"
    ):
        print(tuple(r))
    print("names:", [tuple(r) for r in c.execute(
        "SELECT DISTINCT market FROM mandi_prices WHERE market LIKE '%Corner%' OR market LIKE 'K.R%'"
    )])
