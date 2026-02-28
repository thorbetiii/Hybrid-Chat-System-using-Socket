import socket
import threading
import time
import json
from protocol import send_json, recv_lines

HOST = "0.0.0.0"
PORT = 5000

# In-memory "DB"
users = {}  # username -> {"password": str, "online": bool, "ip": str, "p2p_port": int, "last_seen": float}
lock = threading.Lock()

HEARTBEAT_TIMEOUT = 20  # seconds

def cleanup_thread():
    while True:
        time.sleep(5)
        now = time.time()
        with lock:
            for u, info in users.items():
                if info.get("online") and now - info.get("last_seen", 0) > HEARTBEAT_TIMEOUT:
                    info["online"] = False
                    info["ip"] = None
                    info["p2p_port"] = None

def handle_client(conn, addr):
    buffer = b""
    authed_user = None
    try:
        conn.settimeout(60)
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            lines, buffer = recv_lines(buffer, chunk)
            for line in lines:
                try:
                    msg = json.loads(line.decode("utf-8"))
                except Exception:
                    send_json(conn, {"type": "ERR", "message": "Invalid JSON"})
                    continue

                mtype = msg.get("type")

                if mtype == "REGISTER":
                    username = msg.get("username")
                    password = msg.get("password")
                    if not username or not password:
                        send_json(conn, {"type": "REGISTER_RES", "ok": False, "message": "Missing fields"})
                        continue
                    with lock:
                        if username in users:
                            send_json(conn, {"type": "REGISTER_RES", "ok": False, "message": "User exists"})
                        else:
                            users[username] = {
                                "password": password,
                                "online": False,
                                "ip": None,
                                "p2p_port": None,
                                "last_seen": 0.0
                            }
                            send_json(conn, {"type": "REGISTER_RES", "ok": True, "message": "Registered"})

                elif mtype == "LOGIN":
                    username = msg.get("username")
                    password = msg.get("password")
                    p2p_port = msg.get("p2p_port")
                    if not username or not password or not p2p_port:
                        send_json(conn, {"type": "LOGIN_RES", "ok": False, "message": "Missing fields"})
                        continue

                    with lock:
                        info = users.get(username)
                        if not info or info["password"] != password:
                            send_json(conn, {"type": "LOGIN_RES", "ok": False, "message": "Invalid credentials"})
                        else:
                            info["online"] = True
                            # IP get from TCP connection, avoid fake client
                            info["ip"] = addr[0]
                            info["p2p_port"] = int(p2p_port)
                            info["last_seen"] = time.time()
                            authed_user = username
                            send_json(conn, {"type": "LOGIN_RES", "ok": True, "message": "Logged in", "your_ip": addr[0]})

                elif mtype == "HEARTBEAT":
                    if not authed_user:
                        send_json(conn, {"type": "ERR", "message": "Not logged in"})
                        continue
                    with lock:
                        users[authed_user]["last_seen"] = time.time()
                    send_json(conn, {"type": "HEARTBEAT_RES", "ok": True})

                elif mtype == "LIST":
                    with lock:
                        online = []
                        for u, info in users.items():
                            if info.get("online"):
                                online.append({"username": u, "ip": info.get("ip"), "p2p_port": info.get("p2p_port")})
                    send_json(conn, {"type": "LIST_RES", "online": online})

                elif mtype == "LOOKUP":
                    target = msg.get("username")
                    with lock:
                        info = users.get(target)
                        if info and info.get("online"):
                            send_json(conn, {"type": "LOOKUP_RES", "ok": True, "username": target, "ip": info["ip"], "p2p_port": info["p2p_port"]})
                        else:
                            send_json(conn, {"type": "LOOKUP_RES", "ok": False, "message": "User offline/not found"})

                elif mtype == "LOGOUT":
                    if authed_user:
                        with lock:
                            users[authed_user]["online"] = False
                            users[authed_user]["ip"] = None
                            users[authed_user]["p2p_port"] = None
                    send_json(conn, {"type": "LOGOUT_RES", "ok": True})
                    return

                else:
                    send_json(conn, {"type": "ERR", "message": f"Unknown type: {mtype}"})

    except Exception:
        pass
    finally:
        if authed_user:
            with lock:
                if authed_user in users:
                    users[authed_user]["online"] = False
                    users[authed_user]["ip"] = None
                    users[authed_user]["p2p_port"] = None
        try:
            conn.close()
        except Exception:
            pass

def main():
    threading.Thread(target=cleanup_thread, daemon=True).start()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, PORT))
    s.listen(100)
    print(f"[SERVER] Listening on {HOST}:{PORT}")
    while True:
        conn, addr = s.accept()
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

if __name__ == "__main__":
    main()
