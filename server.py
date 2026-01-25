from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any, Optional, List
import os
import json
import psycopg
from uuid import uuid4


# =========================
# CONFIG
# =========================
DATABASE_URL = os.getenv("DATABASE_URL")

ALLOWED_ORIGINS = [
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "https://magnificent-panda-edbec6.netlify.app",
    # opcional si tienes otro deploy viejo:
    "https://luxury-begonia-2136b4.netlify.app",
]

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
# DB helpers (Postgres / Supabase)
# =========================
def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL no está configurada")
    return psycopg.connect(DATABASE_URL)


def init_state_table():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS state (
                    key TEXT PRIMARY KEY,
                    value JSONB NOT NULL
                )
            """)
        conn.commit()


def init_crochet_table():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS crochet (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    notes TEXT,
                    status TEXT NOT NULL
                )
            """)
        conn.commit()


@app.on_event("startup")
def on_startup():
    """
    Importante: NO queremos que Render se caiga si la DB falla.
    Si falla, el server arranca igual y lo vemos en logs.
    """
    try:
        init_state_table()
    except Exception as e:
        print("⚠️ init_state_table failed:", e)

    try:
        init_crochet_table()
    except Exception as e:
        print("⚠️ init_crochet_table failed:", e)


def get_state(key: str, default: Any):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT value::text FROM state WHERE key = %s", (key,))
            row = cur.fetchone()
    if not row:
        return default
    return json.loads(row[0])


def set_state(key: str, value: Any):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO state (key, value)
                VALUES (%s, %s::jsonb)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                """,
                (key, json.dumps(value)),
            )
        conn.commit()


# =========================
# BASIC endpoints
# =========================
@app.get("/ping")
def ping():
    return {"ok": True, "msg": "pong 💜", "version": "2026-01-25"}

@app.get("/marker")
def marker():
    return {"marker": "SERVER_PY_NEW_123"}

@app.get("/")
def root():
    return {"ok": True, "msg": "Lilazul API online 💜"}


# =========================
# BOOKS (state table)
# =========================
@app.get("/current-book", response_model=dict)
def get_current_book():
    return get_state("current_book", {"title": ""})


@app.post("/current-book")
def api_set_current_book(payload: dict):
    set_state("current_book", payload)
    # devolvemos lo que guardamos (así lo ves en Swagger)
    return payload

@app.get("/finished-books")
def api_list_finished_books():
    return get_state("finished_books", [])

@app.post("/finished-books")
def api_add_finished_book(payload: dict):
    books = get_state("finished_books", [])
    books.insert(0, payload)
    set_state("finished_books", books)
    return books

@app.delete("/finished-books/{book_id}")
def api_delete_finished_book(book_id: str):
    books = get_state("finished_books", [])
    new_books = []
    removed = False

    for b in books:
        if str(b.get("id")) == str(book_id):
            removed = True
            continue
        new_books.append(b)

    if not removed:
        raise HTTPException(status_code=404, detail="Book not found")

    set_state("finished_books", new_books)
    return {"ok": True}


# =========================
# CROCHET (Postgres table)
# =========================
class CrochetCreate(BaseModel):
    title: str
    notes: Optional[str] = ""
    status: Optional[str] = "wip"  # "wip" o "done"

class CrochetItem(CrochetCreate):
    id: str


@app.get("/crochet", response_model=List[CrochetItem])
def list_crochet():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, title, notes, status FROM crochet ORDER BY id DESC")
            rows = cur.fetchall()

    return [
        CrochetItem(id=r[0], title=r[1], notes=r[2] or "", status=r[3])
        for r in rows
    ]


@app.post("/crochet", response_model=CrochetItem)
def add_crochet(payload: CrochetCreate):
    item_id = str(uuid4())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO crochet (id, title, notes, status) VALUES (%s, %s, %s, %s)",
                (item_id, payload.title, payload.notes or "", payload.status or "wip"),
            )
        conn.commit()

    return CrochetItem(
        id=item_id,
        title=payload.title,
        notes=payload.notes or "",
        status=payload.status or "wip",
    )


@app.patch("/crochet/{item_id}/toggle", response_model=CrochetItem)
def toggle_crochet(item_id: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT title, notes, status FROM crochet WHERE id = %s",
                (item_id,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Crochet item not found")

            title, notes, status = row
            new_status = "done" if status != "done" else "wip"

            cur.execute(
                "UPDATE crochet SET status = %s WHERE id = %s",
                (new_status, item_id),
            )
        conn.commit()

    return CrochetItem(
        id=item_id,
        title=title,
        notes=notes or "",
        status=new_status,
    )


@app.delete("/crochet/{item_id}")
def delete_crochet(item_id: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM crochet WHERE id = %s", (item_id,))
            deleted = cur.rowcount
        conn.commit()

    if deleted == 0:
        raise HTTPException(status_code=404, detail="Crochet item not found")

    return {"ok": True}



