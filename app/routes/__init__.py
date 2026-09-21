from . import auth, categories, inventory, products, reports, sales, scan, settings, users

BLUEPRINTS = (
    auth.bp,
    products.bp,
    categories.bp,
    inventory.bp,
    sales.bp,
    reports.bp,
    users.bp,
    settings.bp,
    scan.bp,
)
