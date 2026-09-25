"""Tracks live WebSocket connections and broadcasts messages to them."""

import json

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self.host_connections: list[WebSocket] = []
        self.player_sockets: dict[str, WebSocket] = {}

    async def connect_host(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.host_connections.append(websocket)

    async def connect_player(self, websocket: WebSocket) -> None:
        await websocket.accept()

    def disconnect_host(self, websocket: WebSocket) -> None:
        if websocket in self.host_connections:
            self.host_connections.remove(websocket)

    def disconnect_player(self, websocket: WebSocket) -> None:
        stale = [pid for pid, ws in self.player_sockets.items() if ws is websocket]
        for pid in stale:
            del self.player_sockets[pid]

    def register_player(self, player_id: str, websocket: WebSocket) -> None:
        self.player_sockets[player_id] = websocket

    async def kick_player(self, player_id: str) -> None:
        """Removes a player's connection so they stop receiving broadcasts
        (question_live, etc.) and closes their socket."""
        websocket = self.player_sockets.pop(player_id, None)
        if websocket is None:
            return
        try:
            await websocket.send_text(json.dumps({"type": "removed"}))
            await websocket.close()
        except Exception:
            pass

    async def send_to_socket(self, websocket: WebSocket, message: dict) -> None:
        await websocket.send_text(json.dumps(message))

    async def send_to_player_id(self, player_id: str, message: dict) -> None:
        websocket = self.player_sockets.get(player_id)
        if websocket is None:
            return
        try:
            await websocket.send_text(json.dumps(message))
        except Exception:
            self.disconnect_player(websocket)

    async def broadcast_to_players(self, message: dict) -> None:
        payload = json.dumps(message)
        for websocket in list(self.player_sockets.values()):
            try:
                await websocket.send_text(payload)
            except Exception:
                self.disconnect_player(websocket)

    async def broadcast_to_host(self, message: dict) -> None:
        payload = json.dumps(message)
        for connection in list(self.host_connections):
            try:
                await connection.send_text(payload)
            except Exception:
                self.disconnect_host(connection)


manager = ConnectionManager()
