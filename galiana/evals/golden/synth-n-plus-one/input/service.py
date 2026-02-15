"""User order service with N+1 query pattern."""

import sqlite3

def get_connection():
    return sqlite3.connect("app.db")

def get_all_users_with_orders():
    """Fetch all users and their orders."""
    conn = get_connection()
    cursor = conn.cursor()

    # First query: get all users
    cursor.execute("SELECT id, name, email FROM users")
    users = cursor.fetchall()

    result = []
    for user_id, name, email in users:
        # BUG: N+1 — separate query per user instead of JOIN
        cursor.execute("SELECT id, product, amount FROM orders WHERE user_id = ?", (user_id,))
        orders = cursor.fetchall()
        result.append({
            "id": user_id,
            "name": name,
            "email": email,
            "orders": [{"id": o[0], "product": o[1], "amount": o[2]} for o in orders],
        })

    conn.close()
    return result

def get_user_stats():
    """Get per-user statistics."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, name FROM users")
    users = cursor.fetchall()

    stats = []
    for user_id, name in users:
        # BUG: Another N+1 — could use GROUP BY aggregate
        cursor.execute("SELECT COUNT(*) FROM orders WHERE user_id = ?", (user_id,))
        count = cursor.fetchone()[0]
        cursor.execute("SELECT SUM(amount) FROM orders WHERE user_id = ?", (user_id,))
        total = cursor.fetchone()[0] or 0
        stats.append({"name": name, "order_count": count, "total_spent": total})

    conn.close()
    return stats
