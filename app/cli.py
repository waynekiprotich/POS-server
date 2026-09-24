import os
import sqlite3

import click
from flask import current_app
from flask.cli import with_appcontext

from .extensions import db
from .models import (
    ROLE_ADMIN,
    ROLE_CASHIER,
    ROLE_MANAGER,
    ROLE_VIEWER,
    ROLES,
    Business,
    User,
    utcnow,
)


def register_cli(app):
    app.cli.add_command(init_db)
    app.cli.add_command(create_user_command)
    app.cli.add_command(seed_demo)
    app.cli.add_command(backup_command)
    app.cli.add_command(list_backups_command)
    app.cli.add_command(restore_backup_command)


@click.command("init-db")
@with_appcontext
def init_db():
    """Create any missing tables (use migrations in production)."""
    db.create_all()
    click.echo("Database tables are ready.")


@click.command("create-user")
@click.option("--name", prompt=True)
@click.option("--username", prompt=True)
@click.option("--email", prompt="Email (optional)", default="", show_default=False)
@click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
@click.option("--role", type=click.Choice(list(ROLES)), default=ROLE_ADMIN)
@with_appcontext
def create_user_command(name, username, email, password, role):
    """Create a staff account (normally done in the app; this is for recovery)."""
    email = email.strip().lower() or None
    if User.query.filter_by(username=username.lower()).first():
        raise click.ClickException("That username already exists.")
    if email and User.query.filter_by(email=email).first():
        raise click.ClickException("That email is already in use.")
    if len(password) < 8:
        raise click.ClickException("The password must be at least 8 characters.")
    user = User(
        business_id=Business.current_id(),
        name=name,
        username=username.lower(),
        email=email,
        role=role,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    click.echo("Created %s (%s)." % (user.username, user.role))


@click.command("seed-demo")
@with_appcontext
def seed_demo():
    """Create demo accounts, categories and products for local development."""
    from flask import current_app

    if current_app.config.get("PRODUCTION"):
        raise click.ClickException(
            "seed-demo creates accounts with published passwords and is disabled in "
            "production. Use the first-run setup screen instead."
        )

    from .models import Category, Product
    from .services.inventory_service import apply_movement
    from .models import MOVEMENT_ADJUSTMENT

    db.create_all()

    business = Business.current()
    if business is None:
        business = Business(name="Demo Shop")
        db.session.add(business)
    business.setup_completed_at = business.setup_completed_at or utcnow()
    db.session.flush()

    accounts = [
        ("Admin User", "admin", "admin@example.com", "admin1234", ROLE_ADMIN, None),
        ("Wayne", "wayne", "wayne@example.com", "cashier1234", ROLE_CASHIER, "1234"),
        ("Mary Wanjiku", "mary", None, "cashier1234", ROLE_CASHIER, "2468"),
        ("Brian Otieno", "brian", None, "manager1234", ROLE_MANAGER, "5555"),
        ("Grace Accountant", "grace", None, "viewer1234", ROLE_VIEWER, None),
    ]
    for name, username, email, password, role, pin in accounts:
        existing = User.query.filter_by(username=username).first()
        if existing:
            # Older demo databases predate PINs; give the demo account its PIN.
            if pin and not existing.pin_hash and existing.role == role:
                existing.set_pin(pin)
            continue
        user = User(
            business_id=business.id, name=name, username=username, email=email, role=role
        )
        user.set_password(password)
        if pin:
            user.set_pin(pin)
        db.session.add(user)
    db.session.flush()
    admin = User.query.filter_by(username="admin").first()

    categories = {}
    for name in ("Drinks", "Bakery", "Groceries", "Household"):
        category = Category.query.filter_by(name=name).first()
        if category is None:
            category = Category(name=name, business_id=business.id)
            db.session.add(category)
        categories[name] = category
    db.session.flush()

    demo_products = [
        ("Coca-Cola 500ml", "DRK-0001", "6161234567890", "Drinks", 55, 80, 25, 5),
        ("Milk 500ml", "GRC-0001", "6161234567891", "Groceries", 58, 75, 30, 6),
        ("Bread 400g", "BAK-0001", "6161234567892", "Bakery", 52, 70, 12, 6),
        ("Sugar 1kg", "GRC-0002", "6161234567893", "Groceries", 150, 180, 4, 5),
        ("Cooking Oil 1L", "GRC-0003", "6161234567894", "Groceries", 290, 350, 9, 4),
        ("Dish Soap 500ml", "HSE-0001", "6161234567895", "Household", 120, 165, 0, 3),
    ]
    for name, sku, barcode, category, cost, price, stock, threshold in demo_products:
        if Product.query.filter_by(sku=sku).first():
            continue
        product = Product(
            name=name,
            sku=sku,
            barcode=barcode,
            category_id=categories[category].id,
            cost_price=cost,
            selling_price=price,
            low_stock_threshold=threshold,
            stock_quantity=0,
            unit="pc",
            business_id=business.id,
        )
        db.session.add(product)
        db.session.flush()
        if stock:
            apply_movement(
                product, stock, MOVEMENT_ADJUSTMENT, user=admin, note="Opening stock"
            )

    _seed_supermarket(business, admin)
    db.session.commit()
    from .models import Product as ProductModel

    click.echo(
        "Demo data ready: %d products. Sign in as admin / admin1234, "
        "or wayne / cashier1234 (PIN 1234)." % ProductModel.query.count()
    )


def _seed_supermarket(business, admin):
    """Add the demo supermarket catalogue; products that exist are left alone."""
    from .demo_catalog import catalog_rows
    from .models import MOVEMENT_RESTOCK, Category, Product
    from .services.inventory_service import apply_movement

    categories = {c.name: c for c in Category.query.all()}
    for category_name, sku, barcode, name, cost, price, stock, threshold, unit in catalog_rows():
        category = categories.get(category_name)
        if category is None:
            category = Category(name=category_name, business_id=business.id)
            db.session.add(category)
            db.session.flush()
            categories[category_name] = category
        if Product.query.filter(
            (Product.sku == sku) | (Product.name == name)
            | ((Product.barcode == barcode) if barcode else False)
        ).first():
            continue
        product = Product(
            business_id=business.id,
            name=name,
            sku=sku,
            barcode=barcode,
            category_id=category.id,
            cost_price=cost,
            selling_price=price,
            low_stock_threshold=threshold,
            stock_quantity=0,
            unit=unit,
        )
        db.session.add(product)
        db.session.flush()
        if stock:
            apply_movement(
                product, stock, MOVEMENT_RESTOCK, user=admin, reference="OPENING",
                note="Opening stock",
            )


@click.command("backup")
@with_appcontext
def backup_command():
    """Make a backup of the local database now."""
    from .services.backup_service import create_backup

    backup = create_backup("manual")
    click.echo("Backup saved: %s (%d bytes)" % (backup["name"], backup["size"]))


@click.command("list-backups")
@with_appcontext
def list_backups_command():
    """Show the backups kept on this computer."""
    from .services.backup_service import backup_dir, list_backups

    items = list_backups()
    click.echo("Folder: %s" % backup_dir())
    for item in items:
        click.echo("  %s  %8d KB  %s" % (item["name"], item["size"] // 1024, item["kind"]))
    if not items:
        click.echo("  (no backups yet)")


def _server_running():
    pid_file = os.path.join(current_app.instance_path, "pos-server.pid")
    try:
        with open(pid_file) as handle:
            pid = int(handle.read().strip())
        os.kill(pid, 0)
        return pid
    except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError):
        return None


@click.command("restore-backup")
@click.argument("backup")
@click.option("--yes", is_flag=True, help="Skip the typed confirmation.")
@with_appcontext
def restore_backup_command(backup, yes):
    """Replace the live database with BACKUP (a file name or path).

    The current database is backed up first, so a restore can itself be undone.
    """
    from .services.backup_service import (
        backup_dir,
        copy_database,
        create_backup,
        sqlite_path,
    )

    live = sqlite_path()
    if not live:
        raise click.ClickException("Restore only works with the local SQLite database.")
    pid = _server_running()
    if pid:
        raise click.ClickException(
            "The POS server is running (process %d). Stop it with Ctrl+C first." % pid
        )

    source = backup if os.path.isfile(backup) else os.path.join(backup_dir(), backup)
    if not os.path.isfile(source):
        raise click.ClickException("Backup not found: %s" % backup)
    try:
        check = sqlite3.connect("file:%s?mode=ro" % source, uri=True)
        integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
        tables = {r[0] for r in check.execute("SELECT name FROM sqlite_master")}
        sales = check.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
        check.close()
    except sqlite3.DatabaseError as error:
        raise click.ClickException("That file is not a POS backup: %s" % error)
    if integrity != "ok" or "sales" not in tables:
        raise click.ClickException("That file is damaged or is not a POS backup.")

    click.echo("Backup:   %s (%d sales)" % (source, sales))
    click.echo("Replaces: %s" % live)
    if not yes:
        answer = click.prompt(
            "This replaces ALL current data with the backup. Type RESTORE to continue",
            default="",
            show_default=False,
        )
        if answer.strip() != "RESTORE":
            raise click.ClickException("Restore cancelled. Nothing was changed.")

    safety = create_backup("pre-restore")
    click.echo("Current data saved first as %s" % safety["name"])
    db.session.remove()
    db.engine.dispose()
    copy_database(source, live)
    click.echo("Restored. Start the POS again; it will apply any pending migrations.")
