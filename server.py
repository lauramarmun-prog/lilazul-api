import os
import json
from typing import Any, Dict, Optional, List
from uuid import uuid4

import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from supabase import create_client, Client


# =======================
# Supabase
# =======================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")

sb: Optional[Client] = None
if SUPABASE_URL and SUPABASE_KEY:
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)


def _db() -> Client:
    if sb is None:
        # Esto te dirá CLARITO en Swagger si faltan env vars
        raise HTTPException(status_code=500, detail="Supabase not configured (missing SUPABASE_URL / SUPABASE_*_KEY)")
    return sb


# =======================
# Render Postgres (state + crochet)
# =======================
DATABASE_URL = os.getenv("DATABASE_URL")


def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL no está configurada")
    return psycopg.connect(DATABASE_URL)


def init_tables():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS state (
                    key TEXT PRIMARY KEY,
                    value JSONB NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS crochet (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    notes TEXT,
                    status TEXT NOT NULL
                )
            """)
        conn.commit()


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


# =======================
# FastAPI + CORS
# =======================
app = FastAPI()

ALLOWED_ORIGINS = [
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "http://localhost:5173",
    "http://localhost:3000",
    "https://magnificent-panda-edbec6.netlify.app",
    "https://luxury-begonia-2136b4.netlify.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_tables()


@app.get("/ping")
def ping():
    return {"ok": True, "msg": "pong 💜"}


@app.get("/marker")
def marker():
    return {"marker": "SERVER_PY_NEW_123"}


@app.get("/")
def root():
    return {"ok": True, "msg": "Lilazul API online 💜"}


# =======================
# Current book
# =======================
class CurrentBook(BaseModel):
    title: str


@app.get("/current-book")
def get_current_book():
    return get_state("current_book", {})


@app.post("/current-book")
def set_current_book(payload: CurrentBook):
    data = payload.model_dump()
    set_state("current_book", data)
    return data


# =======================
# Finished books
# =======================
class FinishedBook(BaseModel):
    id: Optional[str] = None
    title: str
    date: str


@app.get("/finished-books")
def list_finished_books():
    return get_state("finished_books", [])


@app.post("/finished-books")
def add_finished_book(payload: FinishedBook):
    books = get_state("finished_books", [])
    item = payload.model_dump()
    if not item.get("id"):
        item["id"] = str(uuid4())
    books.insert(0, item)
    set_state("finished_books", books)
    return books


@app.delete("/finished-books/{book_id}")
def delete_finished_book(book_id: str):
    books = get_state("finished_books", [])
    new_books = [b for b in books if str(b.get("id")) != str(book_id)]
    if len(new_books) == len(books):
        raise HTTPException(status_code=404, detail="Book not found")
    set_state("finished_books", new_books)
    return {"ok": True}


# =======================
# Crochet
# =======================
class CrochetCreate(BaseModel):
    title: str
    notes: Optional[str] = ""
    status: Optional[str] = "wip"  # wip/done


class CrochetItem(CrochetCreate):
    id: str


@app.get("/crochet", response_model=List[CrochetItem])
def list_crochet():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, title, notes, status FROM crochet ORDER BY id DESC")
            rows = cur.fetchall()
    return [CrochetItem(id=r[0], title=r[1], notes=r[2] or "", status=r[3]) for r in rows]


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
    return CrochetItem(id=item_id, title=payload.title, notes=payload.notes or "", status=payload.status or "wip")


@app.patch("/crochet/{item_id}/toggle", response_model=CrochetItem)
def toggle_crochet(item_id: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT title, notes, status FROM crochet WHERE id = %s", (item_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Crochet item not found")
            new_status = "done" if row[2] != "done" else "wip"
            cur.execute("UPDATE crochet SET status = %s WHERE id = %s", (new_status, item_id))
        conn.commit()
    return CrochetItem(id=item_id, title=row[0], notes=row[1] or "", status=new_status)


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


# =======================
# Cake of the month (Supabase)
# =======================
class CakeIn(BaseModel):
    month: str  # "YYYY-MM"
    name: str = ""
    note: str = ""
    photo_url: str = ""
    recipe: str = ""   

@app.delete("/cakes/{cake_id}")
def cake_delete(cake_id: str):
    res = sb.table("cakes").delete().eq("id", cake_id).execute()
    # Si supabase devuelve data vacía, puede que no existiera
    if not getattr(res, "data", None):
        raise HTTPException(status_code=404, detail="Cake not found")
    return {"ok": True}

@app.get("/cake")
def cake_get(month: Optional[str] = None) -> Dict[str, Any]:
    try:
        q = _db().table("cakes").select("id,month,name,note,photo_url")

        if month:
            res = q.eq("month", month).limit(1).execute()
            data = res.data or []
            return {"ok": True, "cake": (data[0] if data else None)}
        else:
            res = q.order("month", desc=True).limit(1).execute()
            data = res.data or []
            return {"ok": True, "cake": (data[0] if data else None)}

    except Exception as e:
        # Esto hará que Swagger te muestre el error REAL (permissions, table missing, etc.)
        raise HTTPException(status_code=500, detail=f"/cake GET failed: {e}")

@app.get("/cakes")
def cakes_list(limit: int = 50) -> Dict[str, Any]:
    """
    Historial de tartas (más recientes primero).
    """
    try:
        res = (
            _db()
            .table("cakes")
            .select("id,month,name,note,photo_url,recipe,created_at,updated_at")
            .order("month", desc=True)
            .limit(limit)
            .execute()
        )
        return {"ok": True, "items": res.data or []}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.put("/cake")
def cake_put(payload: CakeIn) -> Dict[str, Any]:
    try:
        res = _db().table("cakes").upsert(
            {
                "month": payload.month,
                "name": payload.name or "",
                "note": payload.note or "",
                "photo_url": payload.photo_url or "",
                "recipe": payload.recipe or "",   # NUEVO
            },
            on_conflict="month",
        ).execute()

        data = res.data or []
        if data:
            return {"ok": True, "cake": data[0]}

        read = (
            _db()
            .table("cakes")
            .select("id,month,name,note,photo_url,recipe")
            .eq("month", payload.month)
            .limit(1)
            .execute()
        )
        rows = read.data or []
        return {"ok": True, "cake": (rows[0] if rows else None)}

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
# =======================
# Mood (Supabase)
# =======================


@app.get("/moods")
async def get_moods():
    url = _sb_rest_url("mood?select=owner,mood,updated_at")
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(url, headers=_sb_headers())
    if r.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Supabase error: {r.text}")

    rows = r.json()
    out = {"lau": "", "geppie": "", "lau_updated_at": None, "geppie_updated_at": None}

    for row in rows:
        owner = (row.get("owner") or "").lower()
        if owner in ("lau", "geppie"):
            out[owner] = row.get("mood") or ""
            out[f"{owner}_updated_at"] = row.get("updated_at")

    return out

@app.put("/moods/lau")
async def set_lau_mood(payload: MoodUpdate):
    mood = (payload.mood or "").strip()

    # update row
    url = _sb_rest_url("mood?owner=eq.lau")
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.patch(
            url,
            headers={**_sb_headers(), "Prefer": "return=representation"},
            json={"mood": mood},
        )

    if r.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Supabase error: {r.text}")

    return {"ok": True, "owner": "lau", "mood": mood}

@app.put("/moods/geppie")
async def set_geppie_mood(payload: MoodUpdate):
    mood = (payload.mood or "").strip()

    url = _sb_rest_url("mood?owner=eq.geppie")
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.patch(
            url,
            headers={**_sb_headers(), "Prefer": "return=representation"},
            json={"mood": mood},
        )

    if r.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Supabase error: {r.text}")

    return {"ok": True, "owner": "geppie", "mood": mood}


