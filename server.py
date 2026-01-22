from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3

DB = "lilazul.db"


def init_db():
    con = sqlite3.connect(DB)
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS finished_books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            date TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS crochet (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            status TEXT NOT NULL
        )
    """)

    con.commit()
    con.close()


def db():
    return sqlite3.connect(DB)


app = FastAPI()

# CORS: permite que tu web (Netlify) y tu localhost puedan llamar a la API
app.add_middleware(
    CORSMiddleware,
allow_origins=[
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "https://luxury-begonia-2136b4.netlify.app",
    "https://magnificent-panda-edbec6.netlify.app",
],
 
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"ok": True, "msg": "Lilazul API online 💜"}


init_db()


class CurrentBook(BaseModel):
    title: str


class FinishedBook(BaseModel):
    title: str
    date: str


class CrochetItem(BaseModel):
    name: str
    status: str


# ========= CURRENT BOOK =========
@app.get("/current-book")
def get_current_book():
    con = db()
    cur = con.cursor()
    cur.execute("SELECT value FROM state WHERE key='current_book'")
    row = cur.fetchone()
    con.close()
    return {"title": row[0] if row else ""}


@app.post("/current-book")
def set_current_book(payload: CurrentBook):
    con = db()
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO state(key,value)
        VALUES('current_book', ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """,
        (payload.title,),
    )
    con.commit()
    con.close()
    return {"ok": True}


# ========= FINISHED BOOKS =========
@app.get("/finished-books")
def list_finished_books():
    con = db()
    cur = con.cursor()
    cur.execute("SELECT id, title, date FROM finished_books ORDER BY id DESC")
    rows = cur.fetchall()
    con.close()
    return [{"id": r[0], "title": r[1], "date": r[2]} for r in rows]


@app.post("/finished-books")
def add_finished_book(payload: FinishedBook):
    con = db()
    cur = con.cursor()
    cur.execute(
        "INSERT INTO finished_books(title, date) VALUES(?, ?)",
        (payload.title, payload.date),
    )
    con.commit()
    con.close()
    return {"ok": True}


@app.delete("/finished-books/{book_id}")
def delete_finished_book(book_id: int):
    con = db()
    cur = con.cursor()
    cur.execute("DELETE FROM finished_books WHERE id=?", (book_id,))
    con.commit()
    con.close()
    return {"ok": True}


# ========= CROCHET =========
@app.get("/crochet")
def list_crochet():
    con = db()
    cur = con.cursor()
    cur.execute("SELECT id, name, status FROM crochet ORDER BY id DESC")
    rows = cur.fetchall()
    con.close()
    return [{"id": r[0], "name": r[1], "status": r[2]} for r in rows]


@app.post("/crochet")
def add_crochet(payload: CrochetItem):
    con = db()
    cur = con.cursor()
    cur.execute(
        "INSERT INTO crochet(name, status) VALUES(?, ?)",
        (payload.name, payload.status),
    )
    con.commit()
    con.close()
    return {"ok": True}


@app.patch("/crochet/{item_id}/toggle")
def toggle_crochet(item_id: int):
    con = db()
    cur = con.cursor()
    cur.execute("SELECT status FROM crochet WHERE id=?", (item_id,))
    row = cur.fetchone()

    if not row:
        con.close()
        return {"ok": False}

    new_status = "terminado" if row[0] != "terminado" else "en progreso"
    cur.execute("UPDATE crochet SET status=? WHERE id=?", (new_status, item_id))
    con.commit()
    con.close()
    return {"ok": True, "status": new_status}


@app.delete("/crochet/{item_id}")
def delete_crochet(item_id: int):
    con = db()
    cur = con.cursor()
    cur.execute("DELETE FROM crochet WHERE id=?", (item_id,))
    con.commit()
    con.close()
    return {"ok": True}
