"""FastAPI app: serves the host and player pages and wires the WebSocket
messages between phones, the host screen and the game engine (app/game.py).
"""

import asyncio
import io
import os
import sqlite3
import uuid
from pathlib import Path

import qrcode
from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import agent, game
from app.connections import manager
from app.constants import DEMO_GAME_ID
from app.db import get_connection, init_db
from app.nickname_filter import contains_blocked_word

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
PRESENTER_PIN = os.environ.get("PRESENTER_PIN", "")


def _pin_ok(pin: str) -> bool:
    """No PIN configured means no gate (handy for local dev); set
    PRESENTER_PIN before deploying anywhere the host screen is reachable
    by more than just the presenter."""
    return not PRESENTER_PIN or pin == PRESENTER_PIN


app = FastAPI()
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def asset_version() -> str:
    """Newest modified time across static/, added to every CSS and JS link
    (?v=...) so browsers fetch fresh copies whenever a file changes instead
    of showing a stale cached one."""
    files = (BASE_DIR / "static").rglob("*")
    return str(int(max(f.stat().st_mtime for f in files if f.is_file())))


templates.env.globals["asset_version"] = asset_version


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO game (id, stage) VALUES (?, 'lobby')",
            (DEMO_GAME_ID,),
        )
        conn.commit()
    finally:
        conn.close()


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/play")


@app.get("/host", response_class=HTMLResponse)
def host_page(request: Request, pin: str = ""):
    if not _pin_ok(pin):
        return templates.TemplateResponse(
            "host_login.html", {"request": request, "wrong": bool(pin)}
        )
    conn = get_connection()
    try:
        players = conn.execute(
            "SELECT id, nickname FROM player WHERE game_id = ? AND removed = 0 ORDER BY joined_at",
            (DEMO_GAME_ID,),
        ).fetchall()
        mode = conn.execute("SELECT mode FROM game WHERE id = ?", (DEMO_GAME_ID,)).fetchone()["mode"]
    finally:
        conn.close()
    join_url = str(request.base_url) + "play"
    return templates.TemplateResponse(
        "host.html",
        {
            "request": request,
            "mode": mode,
            "players": [{"id": p["id"], "nickname": p["nickname"]} for p in players],
            "pin": pin,
            "join_url": join_url,
        },
    )


@app.get("/qr.png")
def qr_code(request: Request):
    """Rendered large (and with a tight quiet zone) because the host screen
    shows it at 400px+ on a projector and the back row still has to scan it."""
    join_url = str(request.base_url) + "play"
    qr = qrcode.QRCode(box_size=20, border=2)
    qr.add_data(join_url)
    img = qr.make_image(fill_color="#14182B", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


@app.get("/play", response_class=HTMLResponse)
def player_page(request: Request):
    return templates.TemplateResponse("player.html", {"request": request})


@app.websocket("/ws/host")
async def ws_host(websocket: WebSocket):
    pin = websocket.query_params.get("pin", "")
    if not _pin_ok(pin):
        await websocket.close(code=4403)
        return
    await manager.connect_host(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "host_control":
                action = data.get("action")
                if action == "start":
                    await game.handle_start(DEMO_GAME_ID)
                elif action == "next":
                    # Backgrounded: handle_next can run the (slow) difficulty
                    # check or the wrap-up, which itself waits for a later
                    # approval_decision message on this same connection. If
                    # we awaited it here, that message could never be read.
                    asyncio.create_task(game.handle_next(DEMO_GAME_ID))
                elif action == "research":
                    topic = (data.get("topic") or "").strip()
                    if topic:
                        asyncio.create_task(agent.research_topic(DEMO_GAME_ID, topic))
                elif action == "approval_decision":
                    decision = data.get("decision")
                    await game.handle_approval_decision(DEMO_GAME_ID, decision)
                elif action == "switch_mode":
                    await game.handle_switch_mode(DEMO_GAME_ID)
                elif action == "safe_mode":
                    await game.handle_safe_mode(DEMO_GAME_ID)
                elif action == "pause":
                    await game.handle_pause(DEMO_GAME_ID)
                elif action == "resume":
                    await game.handle_resume(DEMO_GAME_ID)
                elif action == "skip":
                    await game.handle_skip(DEMO_GAME_ID)
                elif action == "remove_player":
                    player_id = data.get("player_id")
                    if player_id:
                        await game.handle_remove_player(DEMO_GAME_ID, player_id)
    except WebSocketDisconnect:
        manager.disconnect_host(websocket)


@app.websocket("/ws/player")
async def ws_player(websocket: WebSocket):
    await manager.connect_player(websocket)
    player_id = None
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "join":
                player_id = await handle_join(
                    websocket, data.get("nickname", ""), data.get("device_token")
                )
            elif data.get("type") == "submit_answer" and player_id:
                await game.handle_submit_answer(
                    DEMO_GAME_ID,
                    player_id,
                    data.get("question_id"),
                    data.get("chosen_index"),
                )
    except WebSocketDisconnect:
        manager.disconnect_player(websocket)


async def handle_join(websocket: WebSocket, nickname: str, device_token: str | None) -> str | None:
    if device_token:
        conn = get_connection()
        try:
            existing = conn.execute(
                "SELECT id, nickname, score FROM player WHERE game_id = ? AND device_token = ? AND removed = 0",
                (DEMO_GAME_ID, device_token),
            ).fetchone()
        finally:
            conn.close()
        if existing is not None:
            manager.register_player(existing["id"], websocket)
            await manager.send_to_socket(
                websocket,
                {
                    "type": "joined",
                    "nickname": existing["nickname"],
                    "device_token": device_token,
                    "reconnected": True,
                    "score": existing["score"],
                    "mode": game.get_mode(DEMO_GAME_ID),
                },
            )
            return existing["id"]
        if not nickname:
            # Stored token doesn't match any player (e.g. the game was reset).
            # Tell the client to fall back to the normal join form.
            await manager.send_to_socket(
                websocket,
                {"type": "join_error", "message": "Your session expired, please rejoin.", "forget_token": True},
            )
            return None

    nickname = nickname.strip()
    if not (2 <= len(nickname) <= 16):
        await manager.send_to_socket(
            websocket, {"type": "join_error", "message": "Nickname must be 2-16 characters."}
        )
        return None
    if contains_blocked_word(nickname):
        await manager.send_to_socket(
            websocket, {"type": "join_error", "message": "That nickname isn't allowed, please pick another."}
        )
        return None

    player_id = str(uuid.uuid4())
    device_token = str(uuid.uuid4())

    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO player (id, game_id, nickname, device_token) VALUES (?, ?, ?, ?)",
            (player_id, DEMO_GAME_ID, nickname, device_token),
        )
        conn.commit()
        player_count = conn.execute(
            "SELECT COUNT(*) AS n FROM player WHERE game_id = ? AND removed = 0",
            (DEMO_GAME_ID,),
        ).fetchone()["n"]
    except sqlite3.IntegrityError:
        await manager.send_to_socket(
            websocket, {"type": "join_error", "message": "That nickname is taken."}
        )
        return None
    finally:
        conn.close()

    manager.register_player(player_id, websocket)

    await manager.send_to_socket(
        websocket,
        {"type": "joined", "nickname": nickname, "device_token": device_token, "mode": game.get_mode(DEMO_GAME_ID)},
    )
    await manager.broadcast_to_host(
        {
            "type": "player_joined",
            "player_id": player_id,
            "nickname": nickname,
            "player_count": player_count,
        }
    )
    return player_id
