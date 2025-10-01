from fastmcp import FastMCP
import os
import aiosqlite
import sqlite3
import json
import tempfile

# -------------------- CONFIG --------------------
# Use temporary directory which should be writable
TEMP_DIR = tempfile.gettempdir()
DB_PATH = os.path.join(TEMP_DIR, "expenses.db")
CATEGORIES_PATH = os.path.join(os.path.dirname(__file__), "categories.json")

print(f"Database path: {DB_PATH}")

# Initialize MCP server
mcp = FastMCP("ExpenseTracker")

# -------------------- DB INIT --------------------
def init_db():
    try:
        with sqlite3.connect(DB_PATH) as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("""
                CREATE TABLE IF NOT EXISTS expenses(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    amount REAL NOT NULL,
                    category TEXT NOT NULL,
                    subcategory TEXT DEFAULT '',
                    note TEXT DEFAULT ''
                )
            """)
            print("✅ Database initialized:", DB_PATH)
    except Exception as e:
        print("❌ Database init error:", e)
        raise

init_db()

# -------------------- TOOLS --------------------
@mcp.tool()
async def add_expense(date, amount, category, subcategory="", note=""):
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            cur = await c.execute(
                "INSERT INTO expenses(date, amount, category, subcategory, note) VALUES (?,?,?,?,?)",
                (date, amount, category, subcategory, note)
            )
            expense_id = cur.lastrowid
            await c.commit()
            return {"status": "ok", "id": expense_id}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@mcp.tool()
async def list_expenses(start_date, end_date):
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            cur = await c.execute(
                """SELECT id, date, amount, category, subcategory, note
                   FROM expenses
                   WHERE date BETWEEN ? AND ?
                   ORDER BY date DESC, id DESC""",
                (start_date, end_date)
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in await cur.fetchall()]
    except Exception as e:
        return {"status": "error", "message": str(e)}

@mcp.tool()
async def summarize(start_date, end_date, category=None):
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            query = """SELECT category, SUM(amount) AS total_amount, COUNT(*) as count
                       FROM expenses
                       WHERE date BETWEEN ? AND ?"""
            params = [start_date, end_date]
            if category:
                query += " AND category = ?"
                params.append(category)
            query += " GROUP BY category ORDER BY total_amount DESC"
            cur = await c.execute(query, params)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in await cur.fetchall()]
    except Exception as e:
        return {"status": "error", "message": str(e)}

@mcp.tool()
async def edit_expense(expense_id, date=None, amount=None, category=None, subcategory=None, note=None):
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            fields, params = [], []
            if date: fields.append("date = ?"); params.append(date)
            if amount: fields.append("amount = ?"); params.append(amount)
            if category: fields.append("category = ?"); params.append(category)
            if subcategory: fields.append("subcategory = ?"); params.append(subcategory)
            if note: fields.append("note = ?"); params.append(note)

            if not fields:
                return {"status": "error", "message": "No fields provided"}

            params.append(expense_id)
            cur = await c.execute(f"UPDATE expenses SET {', '.join(fields)} WHERE id = ?", params)
            await c.commit()
            return {"status": "ok", "rows_updated": cur.rowcount}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@mcp.tool()
async def delete_expense(expense_id):
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            cur = await c.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
            await c.commit()
            return {"status": "ok", "rows_deleted": cur.rowcount}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@mcp.tool()
async def search_expenses(keyword):
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            cur = await c.execute(
                """SELECT id, date, amount, category, subcategory, note
                   FROM expenses
                   WHERE note LIKE ? OR category LIKE ? OR subcategory LIKE ?
                   ORDER BY date DESC""",
                (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%")
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in await cur.fetchall()]
    except Exception as e:
        return {"status": "error", "message": str(e)}

@mcp.tool()
async def monthly_report(year):
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            cur = await c.execute(
                """SELECT strftime('%m', date) AS month,
                          SUM(amount) as total_amount,
                          COUNT(*) as count
                   FROM expenses
                   WHERE strftime('%Y', date) = ?
                   GROUP BY month
                   ORDER BY month ASC""",
                (str(year),)
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in await cur.fetchall()]
    except Exception as e:
        return {"status": "error", "message": str(e)}

@mcp.resource("expense:///categories", mime_type="application/json")
def categories():
    default_categories = {
        "categories": [
            "Food & Dining", "Transportation", "Shopping", "Entertainment",
            "Bills & Utilities", "Healthcare", "Travel", "Education",
            "Business", "Other"
        ]
    }
    try:
        if not os.path.exists(CATEGORIES_PATH):
            with open(CATEGORIES_PATH, "w", encoding="utf-8") as f:
                json.dump(default_categories, f, indent=2)
        with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return json.dumps({"error": str(e)})

# -------------------- START SERVER --------------------
if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)
