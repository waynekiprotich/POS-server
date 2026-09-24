from app.demo_catalog import catalog_rows, ean13


def _valid_ean13(code):
    return len(code) == 13 and ean13(code[:12]) == code


def test_catalog_barcodes_and_skus_are_valid_and_unique():
    rows = list(catalog_rows())
    assert len(rows) > 100
    barcodes = [r[2] for r in rows if r[2]]
    assert all(_valid_ean13(code) for code in barcodes)
    assert len(set(barcodes)) == len(barcodes)
    assert len({r[1] for r in rows}) == len(rows)
    assert all(r[5] > r[4] > 0 for r in rows)  # price above cost


def test_known_ean13_check_digit():
    assert ean13("544900000099") == "5449000000996"  # Coca-Cola 500ml
