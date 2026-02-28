import socket
import threading
import time
import json
from protocol import send_json, recv_lines

SERVER_IP = None
SERVER_PORT = 5000

class Client:
    def __init__(self):
        self.server_sock = None
        self.server_buffer = b""
        self.username = None
        self.p2p_listener = None
        self.p2p_port = None
        self.running = True

    # ---------- P2P ----------
    def start_p2p_listener(self, port):
        self.p2p_port = port
        self.p2p_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.p2p_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.p2p_listener.bind(("0.0.0.0", port))
        self.p2p_listener.listen(50)
        threading.Thread(target=self._p2p_accept_loop, daemon=True).start()
        print(f"[P2P] Listening on 0.0.0.0:{port}")

    def _p2p_accept_loop(self):
        while self.running:
            try:
                conn, addr = self.p2p_listener.accept()
                threading.Thread(target=self._handle_peer, args=(conn, addr), daemon=True).start()
            except Exception:
                break

    def _handle_peer(self, conn, addr):
        buffer = b""
        try:
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                lines, buffer = recv_lines(buffer, chunk)
                for line in lines:
                    msg = json.loads(line.decode("utf-8"))
                    if msg.get("type") == "CHAT":
                        frm = msg.get("from")
                        text = msg.get("text")
                        print(f"\n[CHAT] {frm}@{addr[0]}: {text}\n> ", end="")
                        send_json(conn, {"type": "ACK", "ok": True})
        except Exception:
            pass
        finally:
            try: conn.close()
            except: pass

    def p2p_send(self, peer_ip, peer_port, to_user, text):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        try:
            s.connect((peer_ip, peer_port))
            send_json(s, {"type": "CHAT", "from": self.username, "to": to_user, "text": text, "ts": time.time()})
            # wait ack (optional)
            chunk = s.recv(4096)
            # ignore parse if you want
            return True
        except Exception:
            return False
        finally:
            try: s.close()
            except: pass

    # ---------- Server ----------
    def connect_server(self, ip, port):
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.connect((ip, port))
        print(f"[SERVER] Connected to {ip}:{port}")

    def server_recv_one(self):
        while True:
            chunk = self.server_sock.recv(4096)
            if not chunk:
                raise RuntimeError("Server disconnected")
            lines, self.server_buffer = recv_lines(self.server_buffer, chunk)
            if lines:
                return json.loads(lines[0].decode("utf-8"))

    def heartbeat_loop(self):
        while self.running and self.username:
            try:
                send_json(self.server_sock, {"type": "HEARTBEAT"})
                _ = self.server_recv_one()
            except Exception:
                pass
            time.sleep(5)

    # ---------- Commands ----------
    def register(self, username, password):
        send_json(self.server_sock, {"type": "REGISTER", "username": username, "password": password})
        return self.server_recv_one()

    def login(self, username, password):
        send_json(self.server_sock, {"type": "LOGIN", "username": username, "password": password, "p2p_port": self.p2p_port})
        res = self.server_recv_one()
        if res.get("ok"):
            self.username = username
            threading.Thread(target=self.heartbeat_loop, daemon=True).start()
        return res

    def list_online(self):
        send_json(self.server_sock, {"type": "LIST"})
        return self.server_recv_one()

    def lookup(self, username):
        send_json(self.server_sock, {"type": "LOOKUP", "username": username})
        return self.server_recv_one()

    def logout(self):
        send_json(self.server_sock, {"type": "LOGOUT"})
        return self.server_recv_one()

def main():
    global SERVER_IP
    SERVER_IP = input("Server IP: ").strip()
    p2p_port = int(input("Your P2P listen port (e.g., 6001): ").strip())

    c = Client()
    c.start_p2p_listener(p2p_port)
    c.connect_server(SERVER_IP, SERVER_PORT)

    print("\nCommands:")
    print("  reg <user> <pass>")
    print("  login <user> <pass>")
    print("  list")
    print("  chat <user> <message...>")
    print("  logout")
    print("  quit\n")

    while True:
        try:
            cmd = input("> ").strip()
        except EOFError:
            break
        if not cmd:
            continue

        parts = cmd.split()
        op = parts[0].lower()

        if op == "reg" and len(parts) >= 3:
            res = c.register(parts[1], parts[2])
            print(res)

        elif op == "login" and len(parts) >= 3:
            res = c.login(parts[1], parts[2])
            print(res)

        elif op == "list":
            res = c.list_online()
            print(res)

        elif op == "chat" and len(parts) >= 3:
            to_user = parts[1]
            text = " ".join(parts[2:])
            res = c.lookup(to_user)
            if not res.get("ok"):
                print(res)
                continue
            ok = c.p2p_send(res["ip"], int(res["p2p_port"]), to_user, text)
            if not ok:
                print("[P2P] Cannot connect peer (firewall/NAT). (Optional) implement relay via server.")
            else:
                print("[P2P] Sent.")

        elif op == "logout":
            print(c.logout())

        elif op == "quit":
            c.running = False
            try:
                c.logout()
            except Exception:
                pass
            break

        else:
            print("Unknown command.")

if __name__ == "__main__":
    main()
# ip: 10.133.115.196