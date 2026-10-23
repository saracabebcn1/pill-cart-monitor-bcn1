import os, psycopg2, psycopg2.extras
from flask import Flask, jsonify, request, render_template

app = Flask(__name__)
DB = os.environ.get("DATABASE_URL", "")

def get_conn():
    return psycopg2.connect(DB, sslmode="require")

def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS spill_requests (
                    id SERIAL PRIMARY KEY,
                    cart_id TEXT NOT NULL,
                    zone TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    notes TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            conn.commit()

try:
    init_db()
except Exception as e:
    print("DB init error:", e)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/requests")
def get_requests():
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, cart_id, zone, status, notes,
                           created_at AT TIME ZONE 'UTC' AS created_at,
                           updated_at AT TIME ZONE 'UTC' AS updated_at
                    FROM spill_requests
                    WHERE status != 'done'
                    ORDER BY created_at DESC
                """)
                rows = cur.fetchall()
                result = []
                for r in rows:
                    result.append({
                        "id": r["id"], "cart_id": r["cart_id"],
                        "zone": r["zone"], "status": r["status"],
                        "notes": r["notes"],
                        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                        "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
                    })
                return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/request", methods=["POST"])
def create_request():
    data = request.json
    cart_id = data.get("cart_id", "").strip()
    zone = data.get("zone", "").strip()
    if not cart_id or not zone:
        return jsonify({"error": "Faltan datos"}), 400
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT id FROM spill_requests WHERE cart_id=%s AND status!='done'", (cart_id,))
                if cur.fetchone():
                    return jsonify({"error": "Este carro ya tiene una solicitud activa"}), 409
                cur.execute("INSERT INTO spill_requests (cart_id, zone) VALUES (%s, %s) RETURNING id", (cart_id, zone))
                new_id = cur.fetchone()["id"]
                conn.commit()
                return jsonify({"id": new_id, "message": "Solicitud creada"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/request/<int:req_id>/status", methods=["POST"])
def update_status(req_id):
    data = request.json
    status = data.get("status", "")
    notes = data.get("notes", "")
    if status not in ("pending", "in_progress", "done"):
        return jsonify({"error": "Estado no valido"}), 400
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE spill_requests SET status=%s, notes=%s, updated_at=NOW() WHERE id=%s", (status, notes, req_id))
                conn.commit()
                return jsonify({"message": "Actualizado"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/announcement")
def get_announcement():
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM site_config WHERE key='announcement'")
                row = cur.fetchone()
                return jsonify({"message": row[0] if row and row[0] else ""})
    except Exception as e:
        return jsonify({"message": ""}), 200

@app.route("/api/announcement", methods=["POST"])
def set_announcement():
    data = request.json
    msg = data.get("message", "").strip()[:280]
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE site_config SET value=%s, updated_at=NOW() WHERE key='announcement'", (msg,))
                conn.commit()
                return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/wt-auth", methods=["POST"])
def wt_auth():
    data = request.json
    pwd = data.get("password", "")
    correct = os.environ.get("WT_PASSWORD", "waste2026")
    if pwd == correct:
        return jsonify({"ok": True})
    return jsonify({"ok": False}), 401

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=10000)
