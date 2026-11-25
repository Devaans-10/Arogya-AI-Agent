import sqlite3
import json
from config import Config

def get_db_connection():
    conn = sqlite3.connect(Config.DATABASE)
    conn.row_factory = sqlite3.Row
    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    import os
    conn = get_db_connection()
    schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schema.sql')
    with open(schema_path, 'r') as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()

# --- PROFILE CRUD OPERATIONS ---

def get_profiles():
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM profiles ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_profile(profile_id):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def create_profile(name, age, gender, height_cm, weight_kg, activity_level, diet_type, allergies,
                   target_calories=2000, target_protein=60, target_carbs=250, target_fat=65):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO profiles (name, age, gender, height_cm, weight_kg, activity_level, diet_type, allergies,
                              target_calories, target_protein, target_carbs, target_fat)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, age, gender, height_cm, weight_kg, activity_level, diet_type, allergies,
          target_calories, target_protein, target_carbs, target_fat))
    profile_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return profile_id

def update_profile(profile_id, name, age, gender, height_cm, weight_kg, activity_level, diet_type, allergies,
                   target_calories, target_protein, target_carbs, target_fat):
    conn = get_db_connection()
    conn.execute("""
        UPDATE profiles
        SET name = ?, age = ?, gender = ?, height_cm = ?, weight_kg = ?, activity_level = ?,
            diet_type = ?, allergies = ?, target_calories = ?, target_protein = ?, target_carbs = ?, target_fat = ?
        WHERE id = ?
    """, (name, age, gender, height_cm, weight_kg, activity_level, diet_type, allergies,
          target_calories, target_protein, target_carbs, target_fat, profile_id))
    conn.commit()
    conn.close()
    return True

def delete_profile(profile_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
    conn.commit()
    conn.close()
    return True

# --- CHAT HISTORY OPERATIONS ---

def get_chat_history(profile_id, limit=30):
    conn = get_db_connection()
    rows = conn.execute("""
        SELECT role, message, timestamp FROM chat_history
        WHERE profile_id = ?
        ORDER BY id ASC
    """, (profile_id,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]

def add_chat_message(profile_id, role, message):
    conn = get_db_connection()
    conn.execute("""
        INSERT INTO chat_history (profile_id, role, message)
        VALUES (?, ?, ?)
    """, (profile_id, role, message))
    conn.commit()
    conn.close()

def clear_chat_history(profile_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM chat_history WHERE profile_id = ?", (profile_id,))
    conn.commit()
    conn.close()

# --- MEAL PLANS OPERATIONS ---

def get_meal_plans(profile_id):
    conn = get_db_connection()
    rows = conn.execute("""
        SELECT id, goal, duration, plan_data, created_at FROM meal_plans
        WHERE profile_id = ?
        ORDER BY id DESC
    """, (profile_id,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]

def add_meal_plan(profile_id, goal, duration, plan_data):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO meal_plans (profile_id, goal, duration, plan_data)
        VALUES (?, ?, ?, ?)
    """, (profile_id, goal, duration, plan_data))
    plan_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return plan_id

# --- NUTRITION LOGS OPERATIONS ---

def get_nutrition_logs(profile_id, limit=7):
    conn = get_db_connection()
    rows = conn.execute("""
        SELECT date, calories, protein, carbs, fat FROM nutrition_logs
        WHERE profile_id = ?
        ORDER BY date DESC
        LIMIT ?
    """, (profile_id, limit)).fetchall()
    conn.close()
    # Reverse to return in chronological order
    return [dict(row) for row in reversed(rows)]

def add_nutrition_log(profile_id, calories, protein, carbs, fat, date):
    conn = get_db_connection()
    try:
        conn.execute("""
            INSERT INTO nutrition_logs (profile_id, calories, protein, carbs, fat, date)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(profile_id, date) DO UPDATE SET
                calories = excluded.calories,
                protein = excluded.protein,
                carbs = excluded.carbs,
                fat = excluded.fat
        """, (profile_id, calories, protein, carbs, fat, date))
        conn.commit()
        success = True
    except sqlite3.Error:
        success = False
    finally:
        conn.close()
    return success

# --- SUBSCRIPTION & BILLING OPERATIONS ---

def get_owner_subscription(owner_id):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM subscriptions WHERE owner_id = ?", (owner_id,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return {
        'owner_id': owner_id,
        'stripe_customer_id': None,
        'stripe_subscription_id': None,
        'status': 'free',
        'current_period_end': None
    }

def upsert_subscription(owner_id, stripe_customer_id=None, stripe_subscription_id=None, status='active', current_period_end=None):
    conn = get_db_connection()
    existing = conn.execute("SELECT id, stripe_customer_id, stripe_subscription_id FROM subscriptions WHERE owner_id = ?", (owner_id,)).fetchone()
    if existing:
        cust_id = stripe_customer_id if stripe_customer_id else existing['stripe_customer_id']
        sub_id = stripe_subscription_id if stripe_subscription_id else existing['stripe_subscription_id']
        conn.execute("""
            UPDATE subscriptions
            SET stripe_customer_id = ?, stripe_subscription_id = ?, status = ?, current_period_end = ?, updated_at = CURRENT_TIMESTAMP
            WHERE owner_id = ?
        """, (cust_id, sub_id, status, current_period_end, owner_id))
    else:
        conn.execute("""
            INSERT INTO subscriptions (owner_id, stripe_customer_id, stripe_subscription_id, status, current_period_end)
            VALUES (?, ?, ?, ?, ?)
        """, (owner_id, stripe_customer_id, stripe_subscription_id, status, current_period_end))
    conn.commit()
    conn.close()
    return True

def get_subscription_by_customer(stripe_customer_id):
    if not stripe_customer_id:
        return None
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM subscriptions WHERE stripe_customer_id = ?", (stripe_customer_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_subscription_by_sub_id(stripe_subscription_id):
    if not stripe_subscription_id:
        return None
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM subscriptions WHERE stripe_subscription_id = ?", (stripe_subscription_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def update_subscription_status(status, stripe_customer_id=None, stripe_subscription_id=None, current_period_end=None):
    conn = get_db_connection()
    if stripe_subscription_id:
        if current_period_end:
            conn.execute("""
                UPDATE subscriptions
                SET status = ?, current_period_end = ?, updated_at = CURRENT_TIMESTAMP
                WHERE stripe_subscription_id = ?
            """, (status, current_period_end, stripe_subscription_id))
        else:
            conn.execute("""
                UPDATE subscriptions
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE stripe_subscription_id = ?
            """, (status, stripe_subscription_id))
    elif stripe_customer_id:
        if current_period_end:
            conn.execute("""
                UPDATE subscriptions
                SET status = ?, current_period_end = ?, updated_at = CURRENT_TIMESTAMP
                WHERE stripe_customer_id = ?
            """, (status, current_period_end, stripe_customer_id))
        else:
            conn.execute("""
                UPDATE subscriptions
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE stripe_customer_id = ?
            """, (status, stripe_customer_id))
    conn.commit()
    conn.close()
    return True

def is_subscription_active(owner_id):
    sub = get_owner_subscription(owner_id)
    return sub.get('status') in ('active', 'trialing')

# --- CHAT USAGE & QUOTA OPERATIONS ---

def get_daily_chat_usage(owner_id, date_str=None):
    from datetime import datetime
    if not date_str:
        date_str = datetime.today().strftime('%Y-%m-%d')
    conn = get_db_connection()
    row = conn.execute("SELECT count FROM chat_usage WHERE owner_id = ? AND date = ?", (owner_id, date_str)).fetchone()
    conn.close()
    return row['count'] if row else 0

def increment_daily_chat_usage(owner_id, date_str=None):
    from datetime import datetime
    if not date_str:
        date_str = datetime.today().strftime('%Y-%m-%d')
    conn = get_db_connection()
    conn.execute("""
        INSERT INTO chat_usage (owner_id, date, count)
        VALUES (?, ?, 1)
        ON CONFLICT(owner_id, date) DO UPDATE SET count = count + 1
    """, (owner_id, date_str))
    conn.commit()
    conn.close()
    return True

def check_chat_quota(owner_id, free_limit=None):
    """
    Returns (allowed: bool, remaining: int, is_paid: bool, total_limit: int)
    """
    if is_subscription_active(owner_id):
        return True, -1, True, -1
    
    limit = free_limit if free_limit is not None else Config.FREE_DAILY_CHAT_LIMIT
    usage = get_daily_chat_usage(owner_id)
    remaining = max(0, limit - usage)
    allowed = usage < limit
    return allowed, remaining, False, limit

# --- WEBHOOK IDEMPOTENCY OPERATIONS ---

def is_event_processed(event_id):
    conn = get_db_connection()
    row = conn.execute("SELECT id FROM webhook_events WHERE event_id = ?", (event_id,)).fetchone()
    conn.close()
    return row is not None

def record_processed_event(event_id, event_type):
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO webhook_events (event_id, event_type) VALUES (?, ?)", (event_id, event_type))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    finally:
        conn.close()
    return True

