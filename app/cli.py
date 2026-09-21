import click
from flask.cli import with_appcontext

from .extensions import db
from .models import ROLE_ADMIN, ROLE_CASHIER, User


def register_cli(app):
    app.cli.add_command(init_db)
    app.cli.add_command(create_user_command)
    app.cli.add_command(seed_demo)


@click.command("init-db")
@with_appcontext
def init_db():
    """Create any missing tables (use migrations in production)."""
    db.create_all()
    click.echo("Database tables are ready.")


@click.command("create-user")
@click.option("--name", prompt=True)
@click.option("--username", prompt=True)
@click.option("--email", prompt=True)
@click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
@click.option("--role", type=click.Choice([ROLE_ADMIN, ROLE_CASHIER]), default=ROLE_ADMIN)
@with_appcontext
def create_user_command(name, username, email, password, role):
    """Create a user account."""
    if User.query.filter_by(username=username.lower()).first():
        raise click.ClickException("That username already exists.")
    if User.query.filter_by(email=email.lower()).first():
        raise click.ClickException("That email is already in use.")
    if len(password) < 8:
        raise click.ClickException("The password must be at least 8 characters.")
    user = User(name=name, username=username.lower(), email=email.lower(), role=role)
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
            "production. Use `flask create-user` for the first administrator."
        )

    from .models import Category, Product
    from .services.inventory_service import apply_movement
    from .models import MOVEMENT_ADJUSTMENT

    db.create_all()

    accounts = [
        ("Admin User", "admin", "admin@example.com", "admin1234", ROLE_ADMIN),
        ("Wayne", "wayne", "wayne@example.com", "cashier1234", ROLE_CASHIER),
    ]
    for name, username, email, password, role in accounts:
        if User.query.filter_by(username=username).first():
            continue
        user = User(name=name, username=username, email=email, role=role)
        user.set_password(password)
        db.session.add(user)
    db.session.flush()
    admin = User.query.filter_by(username="admin").first()

    categories = {}
    for name in ("Drinks", "Bakery", "Groceries", "Household"):
        category = Category.query.filter_by(name=name).first()
        if category is None:
            category = Category(name=name)
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
        )
        db.session.add(product)
        db.session.flush()
        if stock:
            apply_movement(
                product, stock, MOVEMENT_ADJUSTMENT, user=admin, note="Opening stock"
            )

    db.session.commit()
    click.echo("Demo data ready. Sign in as admin / admin1234 or wayne / cashier1234.")
