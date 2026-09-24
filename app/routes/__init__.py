from . import (
    auth,
    backups,
    categories,
    inventory,
    products,
    reports,
    sales,
    scan,
    settings,
    setup,
    system,
    users,
)

BLUEPRINTS = (
    auth.bp,
    setup.bp,
    products.bp,
    categories.bp,
    inventory.bp,
    sales.bp,
    reports.bp,
    users.bp,
    settings.bp,
    scan.bp,
    system.bp,
    backups.bp,
)
