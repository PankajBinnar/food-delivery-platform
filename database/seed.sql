
INSERT INTO users (name, email, phone, password_hash, role)
VALUES
    ('Rahul Sharma', 'rahul@example.com', '9000000001', 'demo_hash_1', 'CUSTOMER'),
    ('Amit Patil', 'amit@example.com', '9000000002', 'demo_hash_2', 'OWNER')
ON CONFLICT (email) DO NOTHING;

INSERT INTO addresses (
    user_id, address_line, city, state, pincode, is_default
)
SELECT
    id, 'Flat 101, Example Apartments', 'Pune',
    'Maharashtra', '411001', TRUE
FROM users
WHERE email = 'rahul@example.com'
ON CONFLICT DO NOTHING;

INSERT INTO restaurants (
    owner_id, name, description, address, city
)
SELECT
    id, 'Spicy Bites', 'Indian food, biryani and snacks',
    'FC Road, Pune', 'Pune'
FROM users
WHERE email = 'amit@example.com'
AND NOT EXISTS (
    SELECT 1 FROM restaurants WHERE name = 'Spicy Bites'
);

INSERT INTO menu_items (
    restaurant_id, name, description, price, category
)
SELECT r.id, v.name, v.description, v.price, v.category
FROM restaurants r
CROSS JOIN (
    VALUES
        ('Paneer Biryani', 'Aromatic rice with paneer', 220.00, 'Biryani'),
        ('Veg Burger', 'Burger with vegetable patty', 120.00, 'Burgers'),
        ('Masala Dosa', 'Crispy dosa with potato masala', 100.00, 'South Indian')
) AS v(name, description, price, category)
WHERE r.name = 'Spicy Bites'
AND NOT EXISTS (
    SELECT 1 FROM menu_items m
    WHERE m.restaurant_id = r.id AND m.name = v.name
);
