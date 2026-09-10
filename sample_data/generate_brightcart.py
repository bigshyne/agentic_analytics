"""
generate_brightcart.py
=======================
Builds brightcart_sample.sql: a self-contained MySQL dump for a fictional
online store + subscription business ("Brightcart"). 30 normalized tables,
realistic synthetic data, ready to import into a blank MySQL database.

Run:
    python generate_brightcart.py

Output:
    brightcart_sample.sql   (schema + data, single file)
"""

import random
from datetime import datetime, timedelta

from faker import Faker

fake = Faker()
Faker.seed(42)
random.seed(42)

OUT_PATH = "brightcart_sample.sql"
lines = []


def sql_escape(s):
    if s is None:
        return "NULL"
    s = str(s).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{s}'"


def val(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, datetime):
        return f"'{v.strftime('%Y-%m-%d %H:%M:%S')}'"
    return sql_escape(v)


def insert_batch(table, columns, rows, batch_size=200):
    if not rows:
        return
    col_list = ", ".join(columns)
    for i in range(0, len(rows), batch_size):
        chunk = rows[i:i + batch_size]
        value_lines = []
        for row in chunk:
            value_lines.append("(" + ", ".join(val(v) for v in row) + ")")
        lines.append(f"INSERT INTO {table} ({col_list}) VALUES\n" + ",\n".join(value_lines) + ";")


def rand_dt(start, end):
    delta = end - start
    seconds = random.randint(0, int(delta.total_seconds()))
    return start + timedelta(seconds=seconds)


TWO_YEARS_AGO = datetime.now() - timedelta(days=730)
NOW = datetime.now()

# ----------------------------------------------------------------------
# SCHEMA
# ----------------------------------------------------------------------
SCHEMA = """
-- Brightcart sample database — 30 tables
-- Fictional online store + subscription business, for semantic-layer testing.

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

CREATE TABLE customer_segments (
    segment_id INT AUTO_INCREMENT PRIMARY KEY,
    segment_name VARCHAR(50) NOT NULL,
    description VARCHAR(255)
) ENGINE=InnoDB;

CREATE TABLE customers (
    customer_id INT AUTO_INCREMENT PRIMARY KEY,
    segment_id INT,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    phone VARCHAR(30),
    created_at DATETIME NOT NULL,
    FOREIGN KEY (segment_id) REFERENCES customer_segments(segment_id)
) ENGINE=InnoDB;

CREATE TABLE addresses (
    address_id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NOT NULL,
    address_line1 VARCHAR(120) NOT NULL,
    city VARCHAR(60) NOT NULL,
    state VARCHAR(60),
    postal_code VARCHAR(20),
    country VARCHAR(60) NOT NULL,
    address_type VARCHAR(20) NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
) ENGINE=InnoDB;

CREATE TABLE employees (
    employee_id INT AUTO_INCREMENT PRIMARY KEY,
    department VARCHAR(60) NOT NULL,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    hire_date DATE NOT NULL
) ENGINE=InnoDB;

CREATE TABLE accounts (
    account_id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NOT NULL,
    owner_employee_id INT,
    account_name VARCHAR(100) NOT NULL,
    account_type VARCHAR(30) NOT NULL,
    created_at DATETIME NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    FOREIGN KEY (owner_employee_id) REFERENCES employees(employee_id)
) ENGINE=InnoDB;

CREATE TABLE account_users (
    account_user_id INT AUTO_INCREMENT PRIMARY KEY,
    account_id INT NOT NULL,
    customer_id INT NOT NULL,
    role_name VARCHAR(30) NOT NULL,
    joined_at DATETIME NOT NULL,
    FOREIGN KEY (account_id) REFERENCES accounts(account_id),
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
) ENGINE=InnoDB;

CREATE TABLE product_categories (
    category_id INT AUTO_INCREMENT PRIMARY KEY,
    category_name VARCHAR(60) NOT NULL,
    parent_category_id INT,
    FOREIGN KEY (parent_category_id) REFERENCES product_categories(category_id)
) ENGINE=InnoDB;

CREATE TABLE products (
    product_id INT AUTO_INCREMENT PRIMARY KEY,
    category_id INT NOT NULL,
    product_name VARCHAR(120) NOT NULL,
    description VARCHAR(255),
    unit_price DECIMAL(10,2) NOT NULL,
    created_at DATETIME NOT NULL,
    FOREIGN KEY (category_id) REFERENCES product_categories(category_id)
) ENGINE=InnoDB;

CREATE TABLE product_variants (
    variant_id INT AUTO_INCREMENT PRIMARY KEY,
    product_id INT NOT NULL,
    sku VARCHAR(30) NOT NULL UNIQUE,
    variant_name VARCHAR(60) NOT NULL,
    price_adjustment DECIMAL(10,2) NOT NULL DEFAULT 0,
    FOREIGN KEY (product_id) REFERENCES products(product_id)
) ENGINE=InnoDB;

CREATE TABLE suppliers (
    supplier_id INT AUTO_INCREMENT PRIMARY KEY,
    supplier_name VARCHAR(100) NOT NULL,
    contact_email VARCHAR(100),
    country VARCHAR(60)
) ENGINE=InnoDB;

CREATE TABLE product_suppliers (
    product_supplier_id INT AUTO_INCREMENT PRIMARY KEY,
    product_id INT NOT NULL,
    supplier_id INT NOT NULL,
    cost_price DECIMAL(10,2) NOT NULL,
    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id)
) ENGINE=InnoDB;

CREATE TABLE warehouses (
    warehouse_id INT AUTO_INCREMENT PRIMARY KEY,
    warehouse_name VARCHAR(60) NOT NULL,
    city VARCHAR(60),
    country VARCHAR(60)
) ENGINE=InnoDB;

CREATE TABLE inventory (
    inventory_id INT AUTO_INCREMENT PRIMARY KEY,
    variant_id INT NOT NULL,
    warehouse_id INT NOT NULL,
    quantity_on_hand INT NOT NULL,
    reorder_level INT NOT NULL,
    FOREIGN KEY (variant_id) REFERENCES product_variants(variant_id),
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(warehouse_id)
) ENGINE=InnoDB;

CREATE TABLE carriers (
    carrier_id INT AUTO_INCREMENT PRIMARY KEY,
    carrier_name VARCHAR(60) NOT NULL,
    contact_phone VARCHAR(30)
) ENGINE=InnoDB;

CREATE TABLE discounts (
    discount_id INT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(30) NOT NULL UNIQUE,
    description VARCHAR(120),
    discount_pct DECIMAL(5,2) NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE NOT NULL
) ENGINE=InnoDB;

CREATE TABLE orders (
    order_id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NOT NULL,
    shipping_address_id INT NOT NULL,
    order_date DATETIME NOT NULL,
    status VARCHAR(20) NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    FOREIGN KEY (shipping_address_id) REFERENCES addresses(address_id)
) ENGINE=InnoDB;

CREATE TABLE order_items (
    order_item_id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    variant_id INT NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(10,2) NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(order_id),
    FOREIGN KEY (variant_id) REFERENCES product_variants(variant_id)
) ENGINE=InnoDB;

CREATE TABLE order_discounts (
    order_discount_id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    discount_id INT NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(order_id),
    FOREIGN KEY (discount_id) REFERENCES discounts(discount_id)
) ENGINE=InnoDB;

CREATE TABLE payments (
    payment_id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    payment_date DATETIME NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    payment_method VARCHAR(30) NOT NULL,
    status VARCHAR(20) NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
) ENGINE=InnoDB;

CREATE TABLE refunds (
    refund_id INT AUTO_INCREMENT PRIMARY KEY,
    payment_id INT NOT NULL,
    refund_date DATETIME NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    reason VARCHAR(120),
    FOREIGN KEY (payment_id) REFERENCES payments(payment_id)
) ENGINE=InnoDB;

CREATE TABLE invoices (
    invoice_id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    invoice_date DATE NOT NULL,
    due_date DATE NOT NULL,
    total_amount DECIMAL(10,2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
) ENGINE=InnoDB;

CREATE TABLE shipments (
    shipment_id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    carrier_id INT NOT NULL,
    shipped_date DATETIME,
    delivered_date DATETIME,
    tracking_number VARCHAR(40),
    FOREIGN KEY (order_id) REFERENCES orders(order_id),
    FOREIGN KEY (carrier_id) REFERENCES carriers(carrier_id)
) ENGINE=InnoDB;

CREATE TABLE subscription_plans (
    plan_id INT AUTO_INCREMENT PRIMARY KEY,
    plan_name VARCHAR(60) NOT NULL,
    monthly_price DECIMAL(10,2) NOT NULL,
    billing_interval VARCHAR(20) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE subscriptions (
    subscription_id INT AUTO_INCREMENT PRIMARY KEY,
    account_id INT NOT NULL,
    plan_id INT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE,
    status VARCHAR(20) NOT NULL,
    FOREIGN KEY (account_id) REFERENCES accounts(account_id),
    FOREIGN KEY (plan_id) REFERENCES subscription_plans(plan_id)
) ENGINE=InnoDB;

CREATE TABLE subscription_events (
    event_id INT AUTO_INCREMENT PRIMARY KEY,
    subscription_id INT NOT NULL,
    event_type VARCHAR(30) NOT NULL,
    event_date DATETIME NOT NULL,
    FOREIGN KEY (subscription_id) REFERENCES subscriptions(subscription_id)
) ENGINE=InnoDB;

CREATE TABLE support_tickets (
    ticket_id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NOT NULL,
    assigned_employee_id INT,
    subject VARCHAR(150) NOT NULL,
    status VARCHAR(20) NOT NULL,
    priority VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    FOREIGN KEY (assigned_employee_id) REFERENCES employees(employee_id)
) ENGINE=InnoDB;

CREATE TABLE ticket_messages (
    message_id INT AUTO_INCREMENT PRIMARY KEY,
    ticket_id INT NOT NULL,
    sender_type VARCHAR(20) NOT NULL,
    message_text VARCHAR(500) NOT NULL,
    sent_at DATETIME NOT NULL,
    FOREIGN KEY (ticket_id) REFERENCES support_tickets(ticket_id)
) ENGINE=InnoDB;

CREATE TABLE marketing_campaigns (
    campaign_id INT AUTO_INCREMENT PRIMARY KEY,
    campaign_name VARCHAR(100) NOT NULL,
    channel VARCHAR(40) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    budget DECIMAL(10,2) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE campaign_events (
    campaign_event_id INT AUTO_INCREMENT PRIMARY KEY,
    campaign_id INT NOT NULL,
    customer_id INT NOT NULL,
    event_type VARCHAR(30) NOT NULL,
    event_date DATETIME NOT NULL,
    FOREIGN KEY (campaign_id) REFERENCES marketing_campaigns(campaign_id),
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
) ENGINE=InnoDB;

CREATE TABLE reviews (
    review_id INT AUTO_INCREMENT PRIMARY KEY,
    product_id INT NOT NULL,
    customer_id INT NOT NULL,
    rating INT NOT NULL,
    review_text VARCHAR(500),
    created_at DATETIME NOT NULL,
    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
) ENGINE=InnoDB;

SET FOREIGN_KEY_CHECKS = 1;
"""

lines.append(SCHEMA.strip())

# ----------------------------------------------------------------------
# DATA
# ----------------------------------------------------------------------

# customer_segments
segment_names = [
    ("Consumer", "Individual retail shoppers"),
    ("Small Business", "Accounts under 50 employees"),
    ("Mid-Market", "Accounts 50-500 employees"),
    ("Enterprise", "Accounts over 500 employees"),
    ("Reseller", "Partners who resell Brightcart products"),
]
insert_batch("customer_segments", ["segment_id", "segment_name", "description"],
             [(i + 1, n, d) for i, (n, d) in enumerate(segment_names)])
N_SEGMENTS = len(segment_names)

# customers
N_CUSTOMERS = 250
customers = []
for i in range(1, N_CUSTOMERS + 1):
    first, last = fake.first_name(), fake.last_name()
    email = f"{first.lower()}.{last.lower()}{i}@{fake.free_email_domain()}"
    customers.append((i, random.randint(1, N_SEGMENTS), first, last, email,
                       fake.phone_number()[:29], rand_dt(TWO_YEARS_AGO, NOW)))
insert_batch("customers", ["customer_id", "segment_id", "first_name", "last_name", "email", "phone", "created_at"], customers)

# addresses (1-2 per customer)
addresses = []
addr_id = 1
customer_addr_ids = {}
for cid in range(1, N_CUSTOMERS + 1):
    customer_addr_ids[cid] = []
    for _ in range(random.choice([1, 1, 1, 2])):
        addresses.append((addr_id, cid, fake.street_address()[:119], fake.city(), fake.state()[:59],
                           fake.postcode(), "United States", random.choice(["shipping", "billing"])))
        customer_addr_ids[cid].append(addr_id)
        addr_id += 1
insert_batch("addresses", ["address_id", "customer_id", "address_line1", "city", "state", "postal_code", "country", "address_type"], addresses)

# employees
departments = ["Sales", "Customer Success", "Support", "Marketing", "Operations"]
N_EMPLOYEES = 25
employees = []
for i in range(1, N_EMPLOYEES + 1):
    first, last = fake.first_name(), fake.last_name()
    employees.append((i, random.choice(departments), first, last,
                       f"{first.lower()}.{last.lower()}{i}@brightcart.com",
                       fake.date_between(start_date="-5y", end_date="-30d")))
insert_batch("employees", ["employee_id", "department", "first_name", "last_name", "email", "hire_date"], employees)

# accounts (subset of customers act as B2B accounts)
N_ACCOUNTS = 90
account_customer_ids = random.sample(range(1, N_CUSTOMERS + 1), N_ACCOUNTS)
accounts = []
for i, cid in enumerate(account_customer_ids, start=1):
    accounts.append((i, cid, random.randint(1, N_EMPLOYEES), f"{fake.company()[:80]}",
                      random.choice(["business", "reseller", "partner"]), rand_dt(TWO_YEARS_AGO, NOW)))
insert_batch("accounts", ["account_id", "customer_id", "owner_employee_id", "account_name", "account_type", "created_at"], accounts)

# account_users
account_users = []
for i in range(1, 151):
    aid = random.randint(1, N_ACCOUNTS)
    cid = account_customer_ids[aid - 1]
    account_users.append((i, aid, cid, random.choice(["admin", "member", "billing_contact"]),
                           rand_dt(TWO_YEARS_AGO, NOW)))
insert_batch("account_users", ["account_user_id", "account_id", "customer_id", "role_name", "joined_at"], account_users)

# product_categories (4 top-level + subcategories)
top_categories = ["Home & Kitchen", "Electronics", "Apparel", "Outdoor & Sport"]
subcategories = {
    "Home & Kitchen": ["Cookware", "Small Appliances", "Storage"],
    "Electronics": ["Audio", "Accessories", "Smart Home"],
    "Apparel": ["Men's", "Women's"],
    "Outdoor & Sport": ["Camping", "Fitness"],
}
categories = []
cat_id = 1
top_ids = {}
for name in top_categories:
    categories.append((cat_id, name, None))
    top_ids[name] = cat_id
    cat_id += 1
for parent, subs in subcategories.items():
    for s in subs:
        categories.append((cat_id, s, top_ids[parent]))
        cat_id += 1
insert_batch("product_categories", ["category_id", "category_name", "parent_category_id"], categories)
N_CATEGORIES = cat_id - 1

# products
N_PRODUCTS = 160
adjectives = ["Classic", "Pro", "Compact", "Deluxe", "Essential", "Ultra", "Everyday", "Premium"]
nouns = ["Blender", "Speaker", "Jacket", "Tent", "Skillet", "Backpack", "Lamp", "Mixer", "Headphones",
         "Water Bottle", "Sneaker", "Charger", "Organizer", "Grill", "Yoga Mat"]
products = []
for i in range(1, N_PRODUCTS + 1):
    name = f"{random.choice(adjectives)} {random.choice(nouns)}"
    products.append((i, random.randint(1, N_CATEGORIES), name[:119], fake.sentence(nb_words=8)[:254],
                      round(random.uniform(9.99, 249.99), 2), rand_dt(TWO_YEARS_AGO, NOW)))
insert_batch("products", ["product_id", "category_id", "product_name", "description", "unit_price", "created_at"], products)

# product_variants
variants = []
variant_id = 1
product_variant_ids = {pid: [] for pid in range(1, N_PRODUCTS + 1)}
for pid in range(1, N_PRODUCTS + 1):
    for color in random.sample(["Black", "White", "Blue", "Red", "Green"], random.choice([1, 2, 2, 3])):
        sku = f"BC-{pid:04d}-{color[:3].upper()}"
        variants.append((variant_id, pid, sku, color, round(random.uniform(-5, 15), 2)))
        product_variant_ids[pid].append(variant_id)
        variant_id += 1
insert_batch("product_variants", ["variant_id", "product_id", "sku", "variant_name", "price_adjustment"], variants)
N_VARIANTS = variant_id - 1

# suppliers
N_SUPPLIERS = 20
suppliers = []
for i in range(1, N_SUPPLIERS + 1):
    suppliers.append((i, fake.company()[:99], fake.company_email()[:99], fake.country()[:59]))
insert_batch("suppliers", ["supplier_id", "supplier_name", "contact_email", "country"], suppliers)

# product_suppliers
product_suppliers = []
for i in range(1, 221):
    pid = random.randint(1, N_PRODUCTS)
    product_suppliers.append((i, pid, random.randint(1, N_SUPPLIERS), round(random.uniform(3, 150), 2)))
insert_batch("product_suppliers", ["product_supplier_id", "product_id", "supplier_id", "cost_price"], product_suppliers)

# warehouses
warehouse_data = [("North DC", "Columbus", "United States"), ("West DC", "Reno", "United States"),
                   ("South DC", "Dallas", "United States"), ("East DC", "Allentown", "United States")]
insert_batch("warehouses", ["warehouse_id", "warehouse_name", "city", "country"],
             [(i + 1, n, c, co) for i, (n, c, co) in enumerate(warehouse_data)])
N_WAREHOUSES = len(warehouse_data)

# inventory
inventory = []
inv_id = 1
for vid in range(1, N_VARIANTS + 1):
    for wid in random.sample(range(1, N_WAREHOUSES + 1), random.choice([1, 1, 2])):
        inventory.append((inv_id, vid, wid, random.randint(0, 500), random.randint(10, 50)))
        inv_id += 1
insert_batch("inventory", ["inventory_id", "variant_id", "warehouse_id", "quantity_on_hand", "reorder_level"], inventory)

# carriers
carrier_names = ["ParcelSwift", "MetroExpress", "NationalFreight", "QuickShip", "BlueArrow"]
insert_batch("carriers", ["carrier_id", "carrier_name", "contact_phone"],
             [(i + 1, n, fake.phone_number()[:29]) for i, n in enumerate(carrier_names)])
N_CARRIERS = len(carrier_names)

# discounts
discounts = []
for i in range(1, 16):
    start = fake.date_between(start_date="-2y", end_date="-30d")
    discounts.append((i, f"SAVE{random.randint(10, 40)}-{i}", f"{random.choice(['Seasonal', 'Loyalty', 'Clearance'])} discount",
                       round(random.uniform(5, 30), 2), start, start + timedelta(days=random.randint(14, 90))))
insert_batch("discounts", ["discount_id", "code", "description", "discount_pct", "valid_from", "valid_to"], discounts)
N_DISCOUNTS = len(discounts)

# orders
N_ORDERS = 600
orders = []
order_customer = {}
for i in range(1, N_ORDERS + 1):
    cid = random.randint(1, N_CUSTOMERS)
    aid = random.choice(customer_addr_ids[cid])
    odate = rand_dt(TWO_YEARS_AGO, NOW)
    status = random.choices(["completed", "shipped", "processing", "cancelled"], weights=[70, 15, 10, 5])[0]
    orders.append((i, cid, aid, odate, status))
    order_customer[i] = (cid, odate)
insert_batch("orders", ["order_id", "customer_id", "shipping_address_id", "order_date", "status"], orders)

# order_items
order_items = []
oi_id = 1
order_totals = {}
for oid in range(1, N_ORDERS + 1):
    total = 0
    for _ in range(random.choice([1, 1, 2, 2, 3, 4])):
        vid = random.randint(1, N_VARIANTS)
        pid = next(p for p, vs in product_variant_ids.items() if vid in vs)
        base_price = products[pid - 1][4]
        qty = random.randint(1, 3)
        order_items.append((oi_id, oid, vid, qty, base_price))
        total += float(base_price) * qty
        oi_id += 1
    order_totals[oid] = round(total, 2)
insert_batch("order_items", ["order_item_id", "order_id", "variant_id", "quantity", "unit_price"], order_items)

# order_discounts (~25% of orders)
order_discounts = []
discounted_orders = random.sample(range(1, N_ORDERS + 1), N_ORDERS // 4)
for i, oid in enumerate(discounted_orders, start=1):
    order_discounts.append((i, oid, random.randint(1, N_DISCOUNTS)))
insert_batch("order_discounts", ["order_discount_id", "order_id", "discount_id"], order_discounts)

# payments
payments = []
for oid in range(1, N_ORDERS + 1):
    cid, odate = order_customer[oid]
    status = "refunded" if random.random() < 0.05 else "completed"
    payments.append((oid, oid, odate + timedelta(minutes=random.randint(1, 30)), order_totals[oid],
                      random.choice(["credit_card", "paypal", "bank_transfer"]), status))
insert_batch("payments", ["payment_id", "order_id", "payment_date", "amount", "payment_method", "status"], payments)

# refunds (only for refunded payments)
refunds = []
refund_id = 1
for pid, row in enumerate(payments, start=1):
    if row[5] == "refunded":
        refunds.append((refund_id, pid, row[2] + timedelta(days=random.randint(1, 10)),
                         row[3], random.choice(["damaged item", "wrong size", "changed mind", "late delivery"])))
        refund_id += 1
insert_batch("refunds", ["refund_id", "payment_id", "refund_date", "amount", "reason"], refunds)

# invoices
invoices = []
for oid in range(1, N_ORDERS + 1):
    cid, odate = order_customer[oid]
    inv_date = odate.date()
    invoices.append((oid, oid, inv_date, inv_date + timedelta(days=30), order_totals[oid],
                      random.choice(["paid", "paid", "paid", "open", "overdue"])))
insert_batch("invoices", ["invoice_id", "order_id", "invoice_date", "due_date", "total_amount", "status"], invoices)

# shipments (skip ~10% of orders, e.g. cancelled)
shipments = []
sid = 1
for oid in range(1, N_ORDERS + 1):
    if orders[oid - 1][4] == "cancelled":
        continue
    cid, odate = order_customer[oid]
    ship_date = odate + timedelta(days=random.randint(1, 3))
    delivered = ship_date + timedelta(days=random.randint(2, 7)) if random.random() > 0.1 else None
    shipments.append((sid, oid, random.randint(1, N_CARRIERS), ship_date, delivered,
                       fake.bothify(text="1Z#########").upper()))
    sid += 1
insert_batch("shipments", ["shipment_id", "order_id", "carrier_id", "shipped_date", "delivered_date", "tracking_number"], shipments)

# subscription_plans
plans = [("Starter", 19.00, "monthly"), ("Growth", 49.00, "monthly"), ("Scale", 149.00, "monthly"),
         ("Starter Annual", 190.00, "annual"), ("Growth Annual", 490.00, "annual")]
insert_batch("subscription_plans", ["plan_id", "plan_name", "monthly_price", "billing_interval"],
             [(i + 1, n, p, b) for i, (n, p, b) in enumerate(plans)])
N_PLANS = len(plans)

# subscriptions
N_SUBS = 140
subscriptions = []
sub_ids = []
for i in range(1, N_SUBS + 1):
    aid = random.randint(1, N_ACCOUNTS)
    start = fake.date_between(start_date="-2y", end_date="-30d")
    status = random.choices(["active", "cancelled", "trialing"], weights=[70, 20, 10])[0]
    end = None if status == "active" else start + timedelta(days=random.randint(30, 500))
    subscriptions.append((i, aid, random.randint(1, N_PLANS), start, end, status))
    sub_ids.append(i)
insert_batch("subscriptions", ["subscription_id", "account_id", "plan_id", "start_date", "end_date", "status"], subscriptions)

# subscription_events
sub_events = []
for i in range(1, 301):
    sid_ref = random.choice(sub_ids)
    sub_events.append((i, sid_ref, random.choice(["created", "upgraded", "downgraded", "renewed", "cancelled"]),
                        rand_dt(TWO_YEARS_AGO, NOW)))
insert_batch("subscription_events", ["event_id", "subscription_id", "event_type", "event_date"], sub_events)

# support_tickets
N_TICKETS = 130
tickets = []
for i in range(1, N_TICKETS + 1):
    tickets.append((i, random.randint(1, N_CUSTOMERS), random.randint(1, N_EMPLOYEES),
                     fake.sentence(nb_words=6)[:149], random.choice(["open", "closed", "pending"]),
                     random.choice(["low", "medium", "high"]), rand_dt(TWO_YEARS_AGO, NOW)))
insert_batch("support_tickets", ["ticket_id", "customer_id", "assigned_employee_id", "subject", "status", "priority", "created_at"], tickets)

# ticket_messages
ticket_messages = []
for i in range(1, 351):
    tid = random.randint(1, N_TICKETS)
    ticket_messages.append((i, tid, random.choice(["customer", "agent"]), fake.sentence(nb_words=12)[:499],
                             rand_dt(TWO_YEARS_AGO, NOW)))
insert_batch("ticket_messages", ["message_id", "ticket_id", "sender_type", "message_text", "sent_at"], ticket_messages)

# marketing_campaigns
N_CAMPAIGNS = 18
campaigns = []
for i in range(1, N_CAMPAIGNS + 1):
    start = fake.date_between(start_date="-2y", end_date="-60d")
    campaigns.append((i, f"{fake.bs().title()[:80]} Campaign", random.choice(["email", "social", "search", "referral"]),
                       start, start + timedelta(days=random.randint(14, 60)), round(random.uniform(500, 20000), 2)))
insert_batch("marketing_campaigns", ["campaign_id", "campaign_name", "channel", "start_date", "end_date", "budget"], campaigns)

# campaign_events
campaign_events = []
for i in range(1, 451):
    campaign_events.append((i, random.randint(1, N_CAMPAIGNS), random.randint(1, N_CUSTOMERS),
                             random.choice(["impression", "click", "signup", "purchase"]), rand_dt(TWO_YEARS_AGO, NOW)))
insert_batch("campaign_events", ["campaign_event_id", "campaign_id", "customer_id", "event_type", "event_date"], campaign_events)

# reviews
reviews = []
for i in range(1, 301):
    reviews.append((i, random.randint(1, N_PRODUCTS), random.randint(1, N_CUSTOMERS),
                     random.choices([1, 2, 3, 4, 5], weights=[3, 5, 12, 35, 45])[0],
                     fake.sentence(nb_words=15)[:499], rand_dt(TWO_YEARS_AGO, NOW)))
insert_batch("reviews", ["review_id", "product_id", "customer_id", "rating", "review_text", "created_at"], reviews)

with open(OUT_PATH, "w", encoding="utf-8") as f:
    f.write("\n\n".join(lines) + "\n")

print(f"Wrote {OUT_PATH}")
