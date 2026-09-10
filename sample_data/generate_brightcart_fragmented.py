"""
generate_brightcart_fragmented.py
==================================
Same Brightcart business (online store + subscriptions), but Account and
Product are modeled the way real, heavily-normalized OLTP systems do it:
as bare "hub" tables (just an ID, a status, and lifecycle dates) with the
actual descriptive attributes split across separate "satellite" tables,
joined in through link tables. There is no `customers` or `products` table
— those concepts only exist once you join hub -> link -> satellite.

Everything else (orders, subscriptions, support, marketing) stays as
normal, reasonably-shaped tables, so you can compare "easy" entities
against "hard" ones in the same schema.

No MySQL needed: this writes straight to a DuckDB file — a single file on
disk, no server or install required. It plugs directly into
agentic_analytics_prototype.py by pointing SemanticLayer's connection at it.

Run:
    python generate_brightcart_fragmented.py

Output:
    brightcart_fragmented.duckdb
"""

import random
from datetime import datetime, timedelta, date

import duckdb
from faker import Faker

fake = Faker()
Faker.seed(42)
random.seed(42)

DB_PATH = "brightcart_fragmented.duckdb"
START_DATE = datetime(2023, 1, 1)
NOW = datetime.now()
# Original script covered a ~730-day (2yr) window at the volumes below.
# History now runs from START_DATE, so scale time-driven volume up to match
# (catalog-ish tables -- items, suppliers, warehouses, carriers -- stay fixed).
HISTORY_SCALE = (NOW - START_DATE).days / 730


def rand_dt(start, end):
    delta = end - start
    seconds = random.randint(0, int(delta.total_seconds()))
    return start + timedelta(seconds=seconds)


def rand_date(start, end):
    return rand_dt(start, end).date()


import os
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)
con = duckdb.connect(DB_PATH)

# ----------------------------------------------------------------------
# SCHEMA
# ----------------------------------------------------------------------
con.execute("""
CREATE TABLE account_status (
    status_code VARCHAR PRIMARY KEY,
    status_description VARCHAR
)
""")

con.execute("""
CREATE TABLE account (
    account_id INTEGER PRIMARY KEY,
    status_code VARCHAR REFERENCES account_status(status_code),
    inception_date DATE,
    created_date TIMESTAMP,
    modified_date TIMESTAMP
)
""")

con.execute("""
CREATE TABLE customer_segments (
    segment_id INTEGER PRIMARY KEY,
    segment_name VARCHAR,
    description VARCHAR
)
""")

con.execute("""
CREATE TABLE employees (
    employee_id INTEGER PRIMARY KEY,
    department VARCHAR,
    first_name VARCHAR,
    last_name VARCHAR,
    email VARCHAR,
    hire_date DATE
)
""")

con.execute("""
CREATE TABLE account_detail (
    account_detail_id INTEGER PRIMARY KEY,
    account_id INTEGER REFERENCES account(account_id),
    segment_id INTEGER REFERENCES customer_segments(segment_id),
    account_type_code VARCHAR,
    account_name VARCHAR,
    owner_employee_id INTEGER REFERENCES employees(employee_id),
    effective_date DATE
)
""")

con.execute("""
CREATE TABLE party_type (
    party_type_code VARCHAR PRIMARY KEY,
    type_description VARCHAR
)
""")

con.execute("""
CREATE TABLE party (
    party_id INTEGER PRIMARY KEY,
    party_type_code VARCHAR REFERENCES party_type(party_type_code),
    created_date TIMESTAMP
)
""")

con.execute("""
CREATE TABLE party_name (
    party_name_id INTEGER PRIMARY KEY,
    party_id INTEGER REFERENCES party(party_id),
    first_name VARCHAR,
    last_name VARCHAR,
    effective_date DATE,
    end_date DATE
)
""")

con.execute("""
CREATE TABLE party_contact (
    party_contact_id INTEGER PRIMARY KEY,
    party_id INTEGER REFERENCES party(party_id),
    contact_type VARCHAR,
    contact_value VARCHAR,
    is_primary BOOLEAN
)
""")

con.execute("""
CREATE TABLE party_address (
    party_address_id INTEGER PRIMARY KEY,
    party_id INTEGER REFERENCES party(party_id),
    address_type VARCHAR,
    address_line1 VARCHAR,
    city VARCHAR,
    state VARCHAR,
    postal_code VARCHAR,
    country VARCHAR
)
""")

# --- Type-specific party satellites: individuals and organizations have
# genuinely different attribute shapes, so each gets its own satellite
# rather than bolting company fields onto party_name. ---
con.execute("""
CREATE TABLE gender (
    gender_code VARCHAR PRIMARY KEY,
    description VARCHAR
)
""")

con.execute("""
CREATE TABLE party_individual_detail (
    party_id INTEGER PRIMARY KEY REFERENCES party(party_id),
    gender_code VARCHAR REFERENCES gender(gender_code),
    date_of_birth DATE
)
""")

con.execute("""
CREATE TABLE company_type (
    company_type_code VARCHAR PRIMARY KEY,
    description VARCHAR
)
""")

con.execute("""
CREATE TABLE industry (
    industry_code VARCHAR PRIMARY KEY,
    description VARCHAR
)
""")

con.execute("""
CREATE TABLE party_organization_detail (
    party_id INTEGER PRIMARY KEY REFERENCES party(party_id),
    company_type_code VARCHAR REFERENCES company_type(company_type_code),
    industry_code VARCHAR REFERENCES industry(industry_code),
    legal_name VARCHAR,
    employee_count_band VARCHAR
)
""")

con.execute("""
CREATE TABLE account_party_role (
    role_code VARCHAR PRIMARY KEY,
    role_description VARCHAR
)
""")

con.execute("""
CREATE TABLE account_party (
    account_party_id INTEGER PRIMARY KEY,
    account_id INTEGER REFERENCES account(account_id),
    party_id INTEGER REFERENCES party(party_id),
    role_code VARCHAR REFERENCES account_party_role(role_code),
    start_date DATE,
    end_date DATE
)
""")

con.execute("""
CREATE TABLE item_status (
    status_code VARCHAR PRIMARY KEY,
    status_description VARCHAR
)
""")

con.execute("""
CREATE TABLE item (
    item_id INTEGER PRIMARY KEY,
    status_code VARCHAR REFERENCES item_status(status_code),
    created_date TIMESTAMP,
    modified_date TIMESTAMP
)
""")

con.execute("""
CREATE TABLE item_descriptor (
    item_descriptor_id INTEGER PRIMARY KEY,
    item_id INTEGER REFERENCES item(item_id),
    name VARCHAR,
    description VARCHAR,
    effective_date DATE,
    end_date DATE
)
""")

con.execute("""
CREATE TABLE item_price (
    item_price_id INTEGER PRIMARY KEY,
    item_id INTEGER REFERENCES item(item_id),
    price DECIMAL(10,2),
    currency_code VARCHAR,
    effective_date DATE,
    end_date DATE
)
""")

con.execute("""
CREATE TABLE product_categories (
    category_id INTEGER PRIMARY KEY,
    category_name VARCHAR,
    parent_category_id INTEGER REFERENCES product_categories(category_id)
)
""")

con.execute("""
CREATE TABLE item_category_xref (
    item_category_xref_id INTEGER PRIMARY KEY,
    item_id INTEGER REFERENCES item(item_id),
    category_id INTEGER REFERENCES product_categories(category_id)
)
""")

con.execute("""
CREATE TABLE item_variant (
    item_variant_id INTEGER PRIMARY KEY,
    item_id INTEGER REFERENCES item(item_id),
    variant_attribute VARCHAR,
    price_adjustment DECIMAL(10,2)
)
""")

con.execute("""
CREATE TABLE item_identifier (
    item_identifier_id INTEGER PRIMARY KEY,
    item_variant_id INTEGER REFERENCES item_variant(item_variant_id),
    identifier_type VARCHAR,
    identifier_value VARCHAR
)
""")

con.execute("""
CREATE TABLE suppliers (
    supplier_id INTEGER PRIMARY KEY,
    supplier_name VARCHAR,
    contact_email VARCHAR,
    country VARCHAR
)
""")

con.execute("""
CREATE TABLE item_suppliers (
    item_supplier_id INTEGER PRIMARY KEY,
    item_id INTEGER REFERENCES item(item_id),
    supplier_id INTEGER REFERENCES suppliers(supplier_id),
    cost_price DECIMAL(10,2)
)
""")

con.execute("""
CREATE TABLE warehouses (
    warehouse_id INTEGER PRIMARY KEY,
    warehouse_name VARCHAR,
    city VARCHAR,
    country VARCHAR
)
""")

con.execute("""
CREATE TABLE inventory (
    inventory_id INTEGER PRIMARY KEY,
    item_variant_id INTEGER REFERENCES item_variant(item_variant_id),
    warehouse_id INTEGER REFERENCES warehouses(warehouse_id),
    quantity_on_hand INTEGER,
    reorder_level INTEGER
)
""")

con.execute("""
CREATE TABLE carriers (
    carrier_id INTEGER PRIMARY KEY,
    carrier_name VARCHAR,
    contact_phone VARCHAR
)
""")

con.execute("""
CREATE TABLE discounts (
    discount_id INTEGER PRIMARY KEY,
    code VARCHAR,
    description VARCHAR,
    discount_pct DECIMAL(5,2),
    valid_from DATE,
    valid_to DATE
)
""")

con.execute("""
CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    account_id INTEGER REFERENCES account(account_id),
    shipping_party_address_id INTEGER REFERENCES party_address(party_address_id),
    order_date TIMESTAMP,
    status VARCHAR
)
""")

con.execute("""
CREATE TABLE order_items (
    order_item_id INTEGER PRIMARY KEY,
    order_id INTEGER REFERENCES orders(order_id),
    item_variant_id INTEGER REFERENCES item_variant(item_variant_id),
    quantity INTEGER,
    unit_price DECIMAL(10,2)
)
""")

con.execute("""
CREATE TABLE order_discounts (
    order_discount_id INTEGER PRIMARY KEY,
    order_id INTEGER REFERENCES orders(order_id),
    discount_id INTEGER REFERENCES discounts(discount_id)
)
""")

con.execute("""
CREATE TABLE payments (
    payment_id INTEGER PRIMARY KEY,
    order_id INTEGER REFERENCES orders(order_id),
    payment_date TIMESTAMP,
    amount DECIMAL(10,2),
    payment_method VARCHAR,
    status VARCHAR
)
""")

con.execute("""
CREATE TABLE refunds (
    refund_id INTEGER PRIMARY KEY,
    payment_id INTEGER REFERENCES payments(payment_id),
    refund_date TIMESTAMP,
    amount DECIMAL(10,2),
    reason VARCHAR
)
""")

con.execute("""
CREATE TABLE invoices (
    invoice_id INTEGER PRIMARY KEY,
    order_id INTEGER REFERENCES orders(order_id),
    invoice_date DATE,
    due_date DATE,
    total_amount DECIMAL(10,2),
    status VARCHAR
)
""")

con.execute("""
CREATE TABLE shipments (
    shipment_id INTEGER PRIMARY KEY,
    order_id INTEGER REFERENCES orders(order_id),
    carrier_id INTEGER REFERENCES carriers(carrier_id),
    shipped_date TIMESTAMP,
    delivered_date TIMESTAMP,
    tracking_number VARCHAR
)
""")

con.execute("""
CREATE TABLE subscription_plans (
    plan_id INTEGER PRIMARY KEY,
    plan_name VARCHAR,
    monthly_price DECIMAL(10,2),
    billing_interval VARCHAR
)
""")

con.execute("""
CREATE TABLE subscriptions (
    subscription_id INTEGER PRIMARY KEY,
    account_id INTEGER REFERENCES account(account_id),
    plan_id INTEGER REFERENCES subscription_plans(plan_id),
    start_date DATE,
    end_date DATE,
    status VARCHAR
)
""")

con.execute("""
CREATE TABLE subscription_events (
    event_id INTEGER PRIMARY KEY,
    subscription_id INTEGER REFERENCES subscriptions(subscription_id),
    event_type VARCHAR,
    event_date TIMESTAMP
)
""")

con.execute("""
CREATE TABLE support_tickets (
    ticket_id INTEGER PRIMARY KEY,
    account_id INTEGER REFERENCES account(account_id),
    assigned_employee_id INTEGER REFERENCES employees(employee_id),
    subject VARCHAR,
    status VARCHAR,
    priority VARCHAR,
    created_at TIMESTAMP
)
""")

con.execute("""
CREATE TABLE ticket_messages (
    message_id INTEGER PRIMARY KEY,
    ticket_id INTEGER REFERENCES support_tickets(ticket_id),
    sender_type VARCHAR,
    message_text VARCHAR,
    sent_at TIMESTAMP
)
""")

con.execute("""
CREATE TABLE marketing_campaigns (
    campaign_id INTEGER PRIMARY KEY,
    campaign_name VARCHAR,
    channel VARCHAR,
    start_date DATE,
    end_date DATE,
    budget DECIMAL(10,2)
)
""")

con.execute("""
CREATE TABLE campaign_events (
    campaign_event_id INTEGER PRIMARY KEY,
    campaign_id INTEGER REFERENCES marketing_campaigns(campaign_id),
    account_id INTEGER REFERENCES account(account_id),
    event_type VARCHAR,
    event_date TIMESTAMP
)
""")

con.execute("""
CREATE TABLE reviews (
    review_id INTEGER PRIMARY KEY,
    item_id INTEGER REFERENCES item(item_id),
    account_id INTEGER REFERENCES account(account_id),
    rating INTEGER,
    review_text VARCHAR,
    created_at TIMESTAMP
)
""")

# ----------------------------------------------------------------------
# DATA
# ----------------------------------------------------------------------

def insert(table, columns, rows):
    if not rows:
        return
    placeholders = ", ".join(["?"] * len(columns))
    con.executemany(f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})", rows)


# account_status / item_status / party_type / account_party_role lookups
insert("account_status", ["status_code", "status_description"], [
    ("active", "Account is active and in good standing"),
    ("suspended", "Account temporarily suspended"),
    ("closed", "Account has been closed"),
    ("pending", "Account created but not yet activated"),
])
insert("item_status", ["status_code", "status_description"], [
    ("active", "Available for sale"),
    ("discontinued", "No longer sold"),
    ("draft", "Not yet published"),
])
insert("party_type", ["party_type_code", "type_description"], [
    ("individual", "A single person"),
    ("organization", "A business or organization"),
])
insert("gender", ["gender_code", "description"], [
    ("male", "Male"),
    ("female", "Female"),
    ("non_binary", "Non-binary"),
    ("prefer_not_to_say", "Prefer not to say"),
])
insert("company_type", ["company_type_code", "description"], [
    ("llc", "Limited liability company"),
    ("corporation", "Corporation"),
    ("partnership", "Partnership"),
    ("sole_proprietorship", "Sole proprietorship"),
    ("nonprofit", "Nonprofit organization"),
])
insert("industry", ["industry_code", "description"], [
    ("retail", "Retail"),
    ("technology", "Technology"),
    ("healthcare", "Healthcare"),
    ("manufacturing", "Manufacturing"),
    ("professional_services", "Professional Services"),
    ("other", "Other"),
])
insert("account_party_role", ["role_code", "role_description"], [
    ("primary_holder", "Primary account holder"),
    ("authorized_user", "Authorized to act on the account"),
    ("billing_contact", "Receives billing communications"),
])

# customer_segments
segment_names = [
    ("Consumer", "Individual retail shoppers"),
    ("Small Business", "Accounts under 50 employees"),
    ("Mid-Market", "Accounts 50-500 employees"),
    ("Enterprise", "Accounts over 500 employees"),
    ("Reseller", "Partners who resell Brightcart products"),
]
insert("customer_segments", ["segment_id", "segment_name", "description"],
       [(i + 1, n, d) for i, (n, d) in enumerate(segment_names)])
N_SEGMENTS = len(segment_names)

# employees
departments = ["Sales", "Customer Success", "Support", "Marketing", "Operations"]
N_EMPLOYEES = 25
employees = []
for i in range(1, N_EMPLOYEES + 1):
    first, last = fake.first_name(), fake.last_name()
    employees.append((i, random.choice(departments), first, last,
                       f"{first.lower()}.{last.lower()}{i}@brightcart.com",
                       fake.date_between(start_date="-5y", end_date="-30d")))
insert("employees", ["employee_id", "department", "first_name", "last_name", "email", "hire_date"], employees)

# --- Account hub + satellites -----------------------------------------
N_ACCOUNTS = int(250 * HISTORY_SCALE)
accounts = []
account_details = []
for i in range(1, N_ACCOUNTS + 1):
    status = random.choices(["active", "active", "active", "suspended", "closed", "pending"],
                             weights=[50, 20, 10, 5, 10, 5])[0]
    inception = rand_date(START_DATE, NOW - timedelta(days=1))
    created = datetime.combine(inception, datetime.min.time()) + timedelta(hours=random.randint(0, 23))
    modified = min(created + timedelta(days=random.randint(0, 400)), NOW)
    accounts.append((i, status, inception, created, modified))
insert("account", ["account_id", "status_code", "inception_date", "created_date", "modified_date"], accounts)

account_type_by_id = {}  # account_id -> "consumer"/"business"/"reseller", drives party_type below
for i, acc in enumerate(accounts, start=1):
    account_type = random.choices(["consumer", "business", "reseller"], weights=[75, 20, 5])[0]
    account_type_by_id[i] = account_type
    account_name = fake.company()[:80] if account_type != "consumer" else None
    account_details.append((i, i, random.randint(1, N_SEGMENTS), account_type, account_name,
                             random.randint(1, N_EMPLOYEES) if account_type != "consumer" else None,
                             acc[2]))
insert("account_detail", ["account_detail_id", "account_id", "segment_id", "account_type_code",
                           "account_name", "owner_employee_id", "effective_date"], account_details)

# --- Party hub + satellites (the actual people/companies behind each account) --
GENDER_CODES = ["male", "female", "non_binary", "prefer_not_to_say"]
GENDER_WEIGHTS = [47, 47, 3, 3]
COMPANY_TYPE_CODES = ["llc", "corporation", "partnership", "sole_proprietorship", "nonprofit"]
COMPANY_TYPE_WEIGHTS = [45, 25, 10, 15, 5]
INDUSTRY_CODES = ["retail", "technology", "healthcare", "manufacturing", "professional_services", "other"]
INDUSTRY_WEIGHTS = [20, 20, 15, 15, 20, 10]
EMPLOYEE_BANDS = ["1-9", "10-49", "50-249", "250-999", "1000+"]
EMPLOYEE_BAND_WEIGHTS = [35, 30, 20, 10, 5]

parties = []
party_names = []
party_individual_details = []
party_organization_details = []
party_contacts = []
party_addresses = []
account_parties = []
party_id_counter = 1
pname_id = 1
pcontact_id = 1
paddr_id = 1
aparty_id = 1

account_primary_party = {}  # account_id -> party_id, used by orders for shipping address lookup later


def add_individual(pid: int, created: datetime, simulate_name_change: bool):
    """Adds party_name (+ optional history) and party_individual_detail rows for an individual party."""
    global pname_id
    first, last = fake.first_name(), fake.last_name()
    name_effective = created.date()
    if simulate_name_change and random.random() < 0.15:
        # simulate a name change: an old row that ended, and a current row
        old_first, old_last = fake.first_name(), fake.last_name()
        change_date = name_effective + timedelta(days=random.randint(60, 500))
        party_names.append((pname_id, pid, old_first, old_last, name_effective, change_date))
        pname_id += 1
        party_names.append((pname_id, pid, first, last, change_date, None))
        pname_id += 1
    else:
        party_names.append((pname_id, pid, first, last, name_effective, None))
        pname_id += 1

    dob = created.date() - timedelta(days=random.randint(18 * 365, 85 * 365))
    party_individual_details.append((pid, random.choices(GENDER_CODES, weights=GENDER_WEIGHTS)[0], dob))

    return first, last


def add_organization(pid: int):
    """Adds a party_organization_detail row for an organization party. Organizations have no
    party_name row -- legal_name lives here instead, since a company's name isn't a person's name."""
    legal_name = fake.company()[:120]
    party_organization_details.append((
        pid,
        random.choices(COMPANY_TYPE_CODES, weights=COMPANY_TYPE_WEIGHTS)[0],
        random.choices(INDUSTRY_CODES, weights=INDUSTRY_WEIGHTS)[0],
        legal_name,
        random.choices(EMPLOYEE_BANDS, weights=EMPLOYEE_BAND_WEIGHTS)[0],
    ))
    return legal_name


for account_id in range(1, N_ACCOUNTS + 1):
    # every account has exactly one primary_holder party; consumer accounts are held by a
    # person, business/reseller accounts are held by a company
    pid = party_id_counter
    party_id_counter += 1
    created = accounts[account_id - 1][3]
    is_org = account_type_by_id[account_id] != "consumer"
    parties.append((pid, "organization" if is_org else "individual", created))
    account_primary_party[account_id] = pid

    if is_org:
        legal_name = add_organization(pid)
        email = f"info@{fake.domain_name()}"
    else:
        first, last = add_individual(pid, created, simulate_name_change=True)
        email = f"{first.lower()}.{last.lower()}{account_id}@{fake.free_email_domain()}"

    party_contacts.append((pcontact_id, pid, "email", email, True))
    pcontact_id += 1
    if random.random() < 0.7:
        party_contacts.append((pcontact_id, pid, "phone", fake.phone_number()[:29], False))
        pcontact_id += 1

    for _ in range(random.choice([1, 1, 1, 2])):
        party_addresses.append((paddr_id, pid, random.choice(["shipping", "billing"]),
                                 fake.street_address()[:119], fake.city(), fake.state()[:59],
                                 fake.postcode(), "United States"))
        paddr_id += 1

    account_parties.append((aparty_id, account_id, pid, "primary_holder", created.date(), None))
    aparty_id += 1

    # ~20% of accounts also have a second linked party -- always a real person (authorized
    # user / billing contact), even when the primary holder is an organization
    if random.random() < 0.2:
        pid2 = party_id_counter
        party_id_counter += 1
        parties.append((pid2, "individual", created))
        first2, last2 = add_individual(pid2, created, simulate_name_change=False)
        party_contacts.append((pcontact_id, pid2, "email",
                                f"{first2.lower()}.{last2.lower()}{pid2}@{fake.free_email_domain()}", True))
        pcontact_id += 1
        account_parties.append((aparty_id, account_id, pid2,
                                 random.choice(["authorized_user", "billing_contact"]),
                                 created.date(), None))
        aparty_id += 1

insert("party", ["party_id", "party_type_code", "created_date"], parties)
insert("party_name", ["party_name_id", "party_id", "first_name", "last_name", "effective_date", "end_date"], party_names)
insert("party_individual_detail", ["party_id", "gender_code", "date_of_birth"], party_individual_details)
insert("party_organization_detail",
       ["party_id", "company_type_code", "industry_code", "legal_name", "employee_count_band"],
       party_organization_details)
insert("party_contact", ["party_contact_id", "party_id", "contact_type", "contact_value", "is_primary"], party_contacts)
insert("party_address", ["party_address_id", "party_id", "address_type", "address_line1", "city", "state", "postal_code", "country"], party_addresses)
insert("account_party", ["account_party_id", "account_id", "party_id", "role_code", "start_date", "end_date"], account_parties)

# every account needs at least one address to ship to; index by account -> list of that account's primary party's address ids
account_addr_ids = {}
addr_by_party = {}
for row in party_addresses:
    addr_by_party.setdefault(row[1], []).append(row[0])
for account_id, pid in account_primary_party.items():
    account_addr_ids[account_id] = addr_by_party.get(pid, [1])

# --- Item hub + satellites ----------------------------------------------
N_ITEMS = 160
items = []
item_descriptors = []
item_prices = []
adjectives = ["Classic", "Pro", "Compact", "Deluxe", "Essential", "Ultra", "Everyday", "Premium"]
nouns = ["Blender", "Speaker", "Jacket", "Tent", "Skillet", "Backpack", "Lamp", "Mixer", "Headphones",
         "Water Bottle", "Sneaker", "Charger", "Organizer", "Grill", "Yoga Mat"]

idesc_id = 1
iprice_id = 1
for item_id in range(1, N_ITEMS + 1):
    status = random.choices(["active", "active", "active", "discontinued", "draft"], weights=[60, 20, 10, 5, 5])[0]
    created = rand_dt(START_DATE, NOW)
    modified = min(created + timedelta(days=random.randint(0, 300)), NOW)
    items.append((item_id, status, created, modified))

    name = f"{random.choice(adjectives)} {random.choice(nouns)}"
    desc_effective = created.date()
    if random.random() < 0.1:
        old_name = f"{random.choice(adjectives)} {random.choice(nouns)}"
        change_date = desc_effective + timedelta(days=random.randint(60, 400))
        item_descriptors.append((idesc_id, item_id, old_name, fake.sentence(nb_words=8)[:254], desc_effective, change_date))
        idesc_id += 1
        item_descriptors.append((idesc_id, item_id, name, fake.sentence(nb_words=8)[:254], change_date, None))
        idesc_id += 1
    else:
        item_descriptors.append((idesc_id, item_id, name, fake.sentence(nb_words=8)[:254], desc_effective, None))
        idesc_id += 1

    base_price = round(random.uniform(9.99, 249.99), 2)
    if random.random() < 0.2:
        old_price = round(base_price * random.uniform(0.8, 0.95), 2)
        change_date = desc_effective + timedelta(days=random.randint(30, 400))
        item_prices.append((iprice_id, item_id, old_price, "USD", desc_effective, change_date))
        iprice_id += 1
        item_prices.append((iprice_id, item_id, base_price, "USD", change_date, None))
        iprice_id += 1
    else:
        item_prices.append((iprice_id, item_id, base_price, "USD", desc_effective, None))
        iprice_id += 1

insert("item", ["item_id", "status_code", "created_date", "modified_date"], items)
insert("item_descriptor", ["item_descriptor_id", "item_id", "name", "description", "effective_date", "end_date"], item_descriptors)
insert("item_price", ["item_price_id", "item_id", "price", "currency_code", "effective_date", "end_date"], item_prices)

# current price per item, for downstream order/order_item pricing
current_price = {}
for row in item_prices:
    if row[5] is None:
        current_price[row[1]] = row[2]

# product_categories (unchanged shape)
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
insert("product_categories", ["category_id", "category_name", "parent_category_id"], categories)
N_CATEGORIES = cat_id - 1

item_category_xref = [(i, i, random.randint(1, N_CATEGORIES)) for i in range(1, N_ITEMS + 1)]
insert("item_category_xref", ["item_category_xref_id", "item_id", "category_id"], item_category_xref)

# item_variant + item_identifier
item_variants = []
item_identifiers = []
variant_id = 1
identifier_id = 1
item_variant_ids = {iid: [] for iid in range(1, N_ITEMS + 1)}
for item_id in range(1, N_ITEMS + 1):
    for color in random.sample(["Black", "White", "Blue", "Red", "Green"], random.choice([1, 2, 2, 3])):
        item_variants.append((variant_id, item_id, f"Color: {color}", round(random.uniform(-5, 15), 2)))
        item_variant_ids[item_id].append(variant_id)
        sku = f"BC-{item_id:04d}-{color[:3].upper()}"
        item_identifiers.append((identifier_id, variant_id, "sku", sku))
        identifier_id += 1
        variant_id += 1
insert("item_variant", ["item_variant_id", "item_id", "variant_attribute", "price_adjustment"], item_variants)
insert("item_identifier", ["item_identifier_id", "item_variant_id", "identifier_type", "identifier_value"], item_identifiers)
N_VARIANTS = variant_id - 1

# suppliers / item_suppliers
N_SUPPLIERS = 20
suppliers = [(i, fake.company()[:99], fake.company_email()[:99], fake.country()[:59]) for i in range(1, N_SUPPLIERS + 1)]
insert("suppliers", ["supplier_id", "supplier_name", "contact_email", "country"], suppliers)

item_suppliers = [(i, random.randint(1, N_ITEMS), random.randint(1, N_SUPPLIERS), round(random.uniform(3, 150), 2))
                  for i in range(1, 221)]
insert("item_suppliers", ["item_supplier_id", "item_id", "supplier_id", "cost_price"], item_suppliers)

# warehouses / inventory
warehouse_data = [("North DC", "Columbus", "United States"), ("West DC", "Reno", "United States"),
                   ("South DC", "Dallas", "United States"), ("East DC", "Allentown", "United States")]
insert("warehouses", ["warehouse_id", "warehouse_name", "city", "country"],
       [(i + 1, n, c, co) for i, (n, c, co) in enumerate(warehouse_data)])
N_WAREHOUSES = len(warehouse_data)

inventory = []
inv_id = 1
for vid in range(1, N_VARIANTS + 1):
    for wid in random.sample(range(1, N_WAREHOUSES + 1), random.choice([1, 1, 2])):
        inventory.append((inv_id, vid, wid, random.randint(0, 500), random.randint(10, 50)))
        inv_id += 1
insert("inventory", ["inventory_id", "item_variant_id", "warehouse_id", "quantity_on_hand", "reorder_level"], inventory)

# carriers / discounts
carrier_names = ["ParcelSwift", "MetroExpress", "NationalFreight", "QuickShip", "BlueArrow"]
insert("carriers", ["carrier_id", "carrier_name", "contact_phone"],
       [(i + 1, n, fake.phone_number()[:29]) for i, n in enumerate(carrier_names)])
N_CARRIERS = len(carrier_names)

N_DISCOUNTS_TARGET = int(15 * HISTORY_SCALE)
discounts = []
for i in range(1, N_DISCOUNTS_TARGET + 1):
    start = rand_date(START_DATE, NOW - timedelta(days=30))
    discounts.append((i, f"SAVE{random.randint(10, 40)}-{i}", random.choice(["Seasonal", "Loyalty", "Clearance"]) + " discount",
                       round(random.uniform(5, 30), 2), start, start + timedelta(days=random.randint(14, 90))))
insert("discounts", ["discount_id", "code", "description", "discount_pct", "valid_from", "valid_to"], discounts)
N_DISCOUNTS = len(discounts)

# --- Orders / items / payments / etc. (account_id instead of customer_id) --
N_ORDERS = int(600 * HISTORY_SCALE)
orders = []
order_account = {}
for i in range(1, N_ORDERS + 1):
    account_id = random.randint(1, N_ACCOUNTS)
    addr_id = random.choice(account_addr_ids[account_id])
    odate = rand_dt(START_DATE, NOW)
    status = random.choices(["completed", "shipped", "processing", "cancelled"], weights=[70, 15, 10, 5])[0]
    orders.append((i, account_id, addr_id, odate, status))
    order_account[i] = (account_id, odate)
insert("orders", ["order_id", "account_id", "shipping_party_address_id", "order_date", "status"], orders)

order_items = []
oi_id = 1
order_totals = {}
for oid in range(1, N_ORDERS + 1):
    total = 0
    for _ in range(random.choice([1, 1, 2, 2, 3, 4])):
        vid = random.randint(1, N_VARIANTS)
        item_id = next(iid for iid, vs in item_variant_ids.items() if vid in vs)
        price = float(current_price.get(item_id, 19.99))
        qty = random.randint(1, 3)
        order_items.append((oi_id, oid, vid, qty, price))
        total += price * qty
        oi_id += 1
    order_totals[oid] = round(total, 2)
insert("order_items", ["order_item_id", "order_id", "item_variant_id", "quantity", "unit_price"], order_items)

discounted_orders = random.sample(range(1, N_ORDERS + 1), N_ORDERS // 4)
insert("order_discounts", ["order_discount_id", "order_id", "discount_id"],
       [(i, oid, random.randint(1, N_DISCOUNTS)) for i, oid in enumerate(discounted_orders, start=1)])

payments = []
for oid in range(1, N_ORDERS + 1):
    account_id, odate = order_account[oid]
    status = "refunded" if random.random() < 0.05 else "completed"
    payments.append((oid, oid, odate + timedelta(minutes=random.randint(1, 30)), order_totals[oid],
                      random.choice(["credit_card", "paypal", "bank_transfer"]), status))
insert("payments", ["payment_id", "order_id", "payment_date", "amount", "payment_method", "status"], payments)

refunds = []
refund_id = 1
for pid, row in enumerate(payments, start=1):
    if row[5] == "refunded":
        refunds.append((refund_id, pid, row[2] + timedelta(days=random.randint(1, 10)), row[3],
                         random.choice(["damaged item", "wrong size", "changed mind", "late delivery"])))
        refund_id += 1
insert("refunds", ["refund_id", "payment_id", "refund_date", "amount", "reason"], refunds)

invoices = []
for oid in range(1, N_ORDERS + 1):
    account_id, odate = order_account[oid]
    inv_date = odate.date()
    invoices.append((oid, oid, inv_date, inv_date + timedelta(days=30), order_totals[oid],
                      random.choice(["paid", "paid", "paid", "open", "overdue"])))
insert("invoices", ["invoice_id", "order_id", "invoice_date", "due_date", "total_amount", "status"], invoices)

shipments = []
sid = 1
for oid in range(1, N_ORDERS + 1):
    if orders[oid - 1][4] == "cancelled":
        continue
    account_id, odate = order_account[oid]
    ship_date = odate + timedelta(days=random.randint(1, 3))
    delivered = ship_date + timedelta(days=random.randint(2, 7)) if random.random() > 0.1 else None
    shipments.append((sid, oid, random.randint(1, N_CARRIERS), ship_date, delivered,
                       fake.bothify(text="1Z#########").upper()))
    sid += 1
insert("shipments", ["shipment_id", "order_id", "carrier_id", "shipped_date", "delivered_date", "tracking_number"], shipments)

# subscriptions
plans = [("Starter", 19.00, "monthly"), ("Growth", 49.00, "monthly"), ("Scale", 149.00, "monthly"),
         ("Starter Annual", 190.00, "annual"), ("Growth Annual", 490.00, "annual")]
insert("subscription_plans", ["plan_id", "plan_name", "monthly_price", "billing_interval"],
       [(i + 1, n, p, b) for i, (n, p, b) in enumerate(plans)])
N_PLANS = len(plans)

N_SUBS = int(140 * HISTORY_SCALE)
subscriptions = []
sub_ids = []
for i in range(1, N_SUBS + 1):
    account_id = random.randint(1, N_ACCOUNTS)
    start = rand_date(START_DATE, NOW - timedelta(days=30))
    status = random.choices(["active", "cancelled", "trialing"], weights=[70, 20, 10])[0]
    end = None if status == "active" else start + timedelta(days=random.randint(30, 500))
    subscriptions.append((i, account_id, random.randint(1, N_PLANS), start, end, status))
    sub_ids.append(i)
insert("subscriptions", ["subscription_id", "account_id", "plan_id", "start_date", "end_date", "status"], subscriptions)

insert("subscription_events", ["event_id", "subscription_id", "event_type", "event_date"],
       [(i, random.choice(sub_ids), random.choice(["created", "upgraded", "downgraded", "renewed", "cancelled"]),
         rand_dt(START_DATE, NOW)) for i in range(1, int(300 * HISTORY_SCALE) + 1)])

# support / marketing
N_TICKETS = int(130 * HISTORY_SCALE)
tickets = [(i, random.randint(1, N_ACCOUNTS), random.randint(1, N_EMPLOYEES), fake.sentence(nb_words=6)[:149],
            random.choice(["open", "closed", "pending"]), random.choice(["low", "medium", "high"]),
            rand_dt(START_DATE, NOW)) for i in range(1, N_TICKETS + 1)]
insert("support_tickets", ["ticket_id", "account_id", "assigned_employee_id", "subject", "status", "priority", "created_at"], tickets)

insert("ticket_messages", ["message_id", "ticket_id", "sender_type", "message_text", "sent_at"],
       [(i, random.randint(1, N_TICKETS), random.choice(["customer", "agent"]), fake.sentence(nb_words=12)[:499],
         rand_dt(START_DATE, NOW)) for i in range(1, int(350 * HISTORY_SCALE) + 1)])

N_CAMPAIGNS = int(18 * HISTORY_SCALE)
campaigns = []
for i in range(1, N_CAMPAIGNS + 1):
    start = rand_date(START_DATE, NOW - timedelta(days=60))
    campaigns.append((i, f"{fake.bs().title()[:80]} Campaign", random.choice(["email", "social", "search", "referral"]),
                       start, start + timedelta(days=random.randint(14, 60)), round(random.uniform(500, 20000), 2)))
insert("marketing_campaigns", ["campaign_id", "campaign_name", "channel", "start_date", "end_date", "budget"], campaigns)

insert("campaign_events", ["campaign_event_id", "campaign_id", "account_id", "event_type", "event_date"],
       [(i, random.randint(1, N_CAMPAIGNS), random.randint(1, N_ACCOUNTS),
         random.choice(["impression", "click", "signup", "purchase"]), rand_dt(START_DATE, NOW))
        for i in range(1, int(450 * HISTORY_SCALE) + 1)])

insert("reviews", ["review_id", "item_id", "account_id", "rating", "review_text", "created_at"],
       [(i, random.randint(1, N_ITEMS), random.randint(1, N_ACCOUNTS),
         random.choices([1, 2, 3, 4, 5], weights=[3, 5, 12, 35, 45])[0],
         fake.sentence(nb_words=15)[:499], rand_dt(START_DATE, NOW)) for i in range(1, int(300 * HISTORY_SCALE) + 1)])

con.close()
print(f"Wrote {DB_PATH}")
