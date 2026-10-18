
BEGIN;

-- 1. Create 1,000 restaurant owners.
INSERT INTO users (name, email, phone, password_hash, role)
SELECT
    'Load Owner ' || n,
    'load_owner_' || n || '@example.test',
    '880' || LPAD(n::text, 7, '0'),
    'benchmark_placeholder',
    'OWNER'
FROM generate_series(1, 1000) AS s(n)
ON CONFLICT DO NOTHING;

-- 2. Create 10,000 benchmark customers.
INSERT INTO users (name, email, phone, password_hash, role)
SELECT
    'Load Customer ' || n,
    'load_customer_' || n || '@example.test',
    '881' || LPAD(n::text, 7, '0'),
    'benchmark_placeholder',
    'CUSTOMER'
FROM generate_series(1, 10000) AS s(n)
ON CONFLICT DO NOTHING;

-- 3. Create 1,000 restaurants.
INSERT INTO restaurants (
    owner_id, name, description, address, city
)
SELECT
    u.id,
    'Load Test Restaurant ' || n,
    'Restaurant generated for performance testing',
    'Test Address ' || n,
    CASE n % 4
        WHEN 0 THEN 'Pune'
        WHEN 1 THEN 'Mumbai'
        WHEN 2 THEN 'Nashik'
        ELSE 'Nagpur'
    END
FROM generate_series(1, 1000) AS s(n)
JOIN users u
    ON u.email = 'load_owner_' || n || '@example.test'
WHERE NOT EXISTS (
    SELECT 1
    FROM restaurants r
    WHERE r.name = 'Load Test Restaurant ' || n
);

-- 4. Create 100 menu items for each benchmark restaurant.
INSERT INTO menu_items (
    restaurant_id, name, description, price, category
)
SELECT
    r.id,
    'Load Menu Item ' || r.id || '-' || n,
    'Generated menu item for performance testing',
    (50 + ((n * 17) % 451))::numeric(10,2),
    CASE n % 5
        WHEN 0 THEN 'Biryani'
        WHEN 1 THEN 'Pizza'
        WHEN 2 THEN 'Burgers'
        WHEN 3 THEN 'South Indian'
        ELSE 'Desserts'
    END
FROM restaurants r
CROSS JOIN generate_series(1, 100) AS s(n)
WHERE r.name LIKE 'Load Test Restaurant %'
AND NOT EXISTS (
    SELECT 1
    FROM menu_items m
    WHERE m.restaurant_id = r.id
      AND m.name = 'Load Menu Item ' || r.id || '-' || n
);

-- 5. Create one address for each benchmark customer.
INSERT INTO addresses (
    user_id, address_line, city, state, pincode, is_default
)
SELECT
    u.id,
    'Benchmark Address ' || n,
    'Pune',
    'Maharashtra',
    '411001',
    TRUE
FROM generate_series(1, 10000) AS s(n)
JOIN users u
    ON u.email = 'load_customer_' || n || '@example.test'
WHERE NOT EXISTS (
    SELECT 1
    FROM addresses a
    WHERE a.user_id = u.id
      AND a.address_line = 'Benchmark Address ' || n
);

COMMIT;

ANALYZE users;
ANALYZE addresses;
ANALYZE restaurants;
ANALYZE menu_items;
