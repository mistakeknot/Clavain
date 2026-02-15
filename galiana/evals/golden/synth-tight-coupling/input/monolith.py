"""Order processing monolith with tight coupling."""

import json
import smtplib
import sqlite3
from email.mime.text import MIMEText

def process_order(request_body: bytes, db_path: str = "orders.db") -> dict:
    """Process an incoming order request.

    This function does everything: parse HTTP, validate, persist, notify, log.
    """
    # Parse request
    try:
        data = json.loads(request_body)
    except json.JSONDecodeError:
        return {"error": "invalid JSON", "status": 400}

    user_id = data.get("user_id")
    items = data.get("items", [])
    shipping_address = data.get("shipping_address")

    # Validate
    if not user_id or not items:
        return {"error": "missing required fields", "status": 400}

    # Calculate totals (business logic mixed with persistence)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    total = 0
    for item in items:
        cursor.execute("SELECT price, stock FROM products WHERE id = ?", (item["product_id"],))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return {"error": f"product {item['product_id']} not found", "status": 404}
        price, stock = row
        if stock < item["quantity"]:
            conn.close()
            return {"error": f"insufficient stock for {item['product_id']}", "status": 409}
        total += price * item["quantity"]

    # Persist order (database access interleaved with business logic)
    cursor.execute(
        "INSERT INTO orders (user_id, total, address, status) VALUES (?, ?, ?, ?)",
        (user_id, total, shipping_address, "pending")
    )
    order_id = cursor.lastrowid

    for item in items:
        cursor.execute(
            "INSERT INTO order_items (order_id, product_id, quantity) VALUES (?, ?, ?)",
            (order_id, item["product_id"], item["quantity"])
        )
        cursor.execute(
            "UPDATE products SET stock = stock - ? WHERE id = ?",
            (item["quantity"], item["product_id"])
        )

    conn.commit()
    conn.close()

    # Send email notification (I/O mixed with business logic)
    try:
        msg = MIMEText(f"Order #{order_id} confirmed. Total: ${total:.2f}")
        msg["Subject"] = f"Order Confirmation #{order_id}"
        msg["From"] = "orders@shop.com"
        msg["To"] = f"user-{user_id}@shop.com"

        with smtplib.SMTP("localhost", 587) as server:
            server.send_message(msg)
    except Exception:
        pass  # Silently swallow email errors

    # Log to file (yet another responsibility)
    with open("/var/log/orders.log", "a") as f:
        f.write(f"ORDER {order_id} user={user_id} total={total}\n")

    return {"order_id": order_id, "total": total, "status": "confirmed"}
