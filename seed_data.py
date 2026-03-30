"""Populate the database with realistic demo data."""

import sys
from datetime import datetime, timedelta, timezone

from app.auth.security import hash_password
from app.database import Base, SessionLocal, engine
from app.models.category import Category
from app.models.inventory import Inventory
from app.models.order import Order, OrderItem
from app.models.product import Product
from app.models.user import User


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    # Check if already seeded
    if db.query(User).first():
        print("Database already contains data. Drop inventory.db and re-run to reseed.")
        db.close()
        return

    print("Seeding database...")

    # --- Users ---------------------------------------------------------------
    users = [
        User(
            email="admin@inventory.io",
            username="admin",
            hashed_password=hash_password("admin123"),
            full_name="System Admin",
            is_admin=True,
        ),
        User(
            email="alice@inventory.io",
            username="alice",
            hashed_password=hash_password("alice123"),
            full_name="Alice Johnson",
        ),
        User(
            email="bob@inventory.io",
            username="bob",
            hashed_password=hash_password("bob12345"),
            full_name="Bob Williams",
        ),
    ]
    db.add_all(users)
    db.flush()
    print(f"  Created {len(users)} users")

    # --- Categories ----------------------------------------------------------
    categories = [
        Category(name="Electronics", description="Electronic devices, components, and accessories"),
        Category(name="Office Supplies", description="Pens, paper, binders, and desk essentials"),
        Category(name="Furniture", description="Desks, chairs, shelving, and storage units"),
        Category(name="Clothing", description="Apparel, uniforms, and protective wear"),
        Category(name="Tools & Hardware", description="Hand tools, power tools, and fasteners"),
    ]
    db.add_all(categories)
    db.flush()
    print(f"  Created {len(categories)} categories")

    # --- Products ------------------------------------------------------------
    now = datetime.now(timezone.utc)
    products = [
        # Electronics
        Product(sku="ELEC-001", name="Wireless Mouse", description="Ergonomic 2.4GHz wireless mouse with USB-A receiver", price=29.99, category_id=categories[0].id),
        Product(sku="ELEC-002", name="Mechanical Keyboard", description="Cherry MX Blue switches, full-size, backlit", price=89.99, category_id=categories[0].id),
        Product(sku="ELEC-003", name="USB-C Hub (7-port)", description="Multi-port adapter: HDMI, USB-A x3, SD, USB-C PD", price=49.99, category_id=categories[0].id),
        Product(sku="ELEC-004", name="27\" IPS Monitor", description="2560x1440 QHD, 75Hz, VESA mount, USB-C input", price=349.99, category_id=categories[0].id),
        Product(sku="ELEC-005", name="Webcam 1080p", description="Full HD webcam with built-in mic and privacy shutter", price=59.99, category_id=categories[0].id),
        # Office Supplies
        Product(sku="OFFC-001", name="Ballpoint Pens (12-pack)", description="Medium-point black ink pens", price=8.99, category_id=categories[1].id),
        Product(sku="OFFC-002", name="Copy Paper (500 sheets)", description="20lb white letter-size paper", price=12.49, category_id=categories[1].id),
        Product(sku="OFFC-003", name="3-Ring Binder (1\")", description="White view binder with two inside pockets", price=5.99, category_id=categories[1].id),
        Product(sku="OFFC-004", name="Sticky Notes (5-pack)", description="3x3 inch, assorted colors, 100 sheets per pad", price=6.49, category_id=categories[1].id),
        # Furniture
        Product(sku="FURN-001", name="Adjustable Standing Desk", description="Electric sit-stand desk, 48x30 inches, programmable presets", price=499.99, category_id=categories[2].id),
        Product(sku="FURN-002", name="Ergonomic Office Chair", description="Mesh back, lumbar support, adjustable armrests", price=329.99, category_id=categories[2].id),
        Product(sku="FURN-003", name="3-Shelf Bookcase", description="Laminate wood, adjustable shelves, 36\" wide", price=89.99, category_id=categories[2].id),
        # Clothing
        Product(sku="CLTH-001", name="Safety Vest (Hi-Vis)", description="ANSI Class 2 high-visibility vest, orange", price=14.99, category_id=categories[3].id),
        Product(sku="CLTH-002", name="Work Gloves (pair)", description="Leather palm, reinforced fingertips, size L", price=19.99, category_id=categories[3].id),
        # Tools
        Product(sku="TOOL-001", name="Cordless Drill 20V", description="Lithium-ion, 1/2\" chuck, two batteries included", price=129.99, category_id=categories[4].id),
        Product(sku="TOOL-002", name="Socket Set (40-piece)", description="SAE & metric, 1/4\" and 3/8\" drive", price=44.99, category_id=categories[4].id),
        Product(sku="TOOL-003", name="Tape Measure 25ft", description="Magnetic hook, nylon-coated blade", price=12.99, category_id=categories[4].id),
        Product(sku="TOOL-004", name="Level (48\")", description="Aluminum I-beam, 3 vial, shock-resistant end caps", price=34.99, category_id=categories[4].id),
    ]
    db.add_all(products)
    db.flush()
    print(f"  Created {len(products)} products")

    # --- Inventory -----------------------------------------------------------
    stock_levels = [
        150, 75, 200, 30, 120,   # Electronics
        500, 800, 300, 450,       # Office
        15, 20, 40,               # Furniture
        250, 180,                 # Clothing
        60, 90, 300, 55,          # Tools
    ]
    thresholds = [
        20, 10, 25, 5, 15,
        50, 100, 30, 50,
        3, 5, 8,
        30, 20,
        10, 15, 40, 10,
    ]
    locations = [
        "A1-01", "A1-02", "A1-03", "A1-04", "A1-05",
        "B2-01", "B2-02", "B2-03", "B2-04",
        "C3-01", "C3-02", "C3-03",
        "D4-01", "D4-02",
        "E5-01", "E5-02", "E5-03", "E5-04",
    ]
    inventory_records = []
    for i, product in enumerate(products):
        inv = Inventory(
            product_id=product.id,
            quantity=stock_levels[i],
            low_stock_threshold=thresholds[i],
            warehouse_location=locations[i],
            last_restocked=now - timedelta(days=i * 2),
        )
        inventory_records.append(inv)
    db.add_all(inventory_records)
    db.flush()
    print(f"  Created {len(inventory_records)} inventory records")

    # --- Orders --------------------------------------------------------------
    order_data = [
        {
            "order_number": "ORD-A1B2C3D4",
            "customer_name": "TechCorp Industries",
            "customer_email": "purchasing@techcorp.com",
            "status": "delivered",
            "notes": "Deliver to loading dock B",
            "items": [(0, 10), (1, 5), (4, 3)],
        },
        {
            "order_number": "ORD-E5F6G7H8",
            "customer_name": "Metro Office Solutions",
            "customer_email": "orders@metrooffice.com",
            "status": "shipped",
            "notes": None,
            "items": [(5, 50), (6, 100), (8, 25)],
        },
        {
            "order_number": "ORD-I9J0K1L2",
            "customer_name": "BuildRight Construction",
            "customer_email": "supply@buildright.com",
            "status": "confirmed",
            "notes": "Rush order - job site delivery",
            "items": [(14, 4), (15, 2), (16, 10), (12, 20)],
        },
        {
            "order_number": "ORD-M3N4O5P6",
            "customer_name": "HomeStart Furnishings",
            "customer_email": "buyer@homestart.com",
            "status": "pending",
            "notes": "Hold until warehouse confirms availability",
            "items": [(9, 2), (10, 3), (11, 5)],
        },
    ]
    for od in order_data:
        total = 0.0
        order = Order(
            order_number=od["order_number"],
            customer_name=od["customer_name"],
            customer_email=od["customer_email"],
            status=od["status"],
            notes=od["notes"],
            created_at=now - timedelta(days=len(order_data)),
        )
        for prod_idx, qty in od["items"]:
            product = products[prod_idx]
            subtotal = product.price * qty
            total += subtotal
            order.items.append(
                OrderItem(
                    product_id=product.id,
                    quantity=qty,
                    unit_price=product.price,
                    subtotal=round(subtotal, 2),
                )
            )
        order.total_amount = round(total, 2)
        db.add(order)
    db.flush()
    print(f"  Created {len(order_data)} orders")

    db.commit()
    db.close()
    print("\nSeed complete. Demo credentials:")
    print("  admin / admin123  (admin user)")
    print("  alice / alice123")
    print("  bob   / bob12345")


if __name__ == "__main__":
    seed()
