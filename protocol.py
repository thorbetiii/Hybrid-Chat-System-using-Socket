import json

def send_json(sock, obj):
    data = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
    sock.sendall(data)

def recv_lines(buffer, chunk):
    buffer += chunk
    lines = []
    while b"\n" in buffer:
        line, buffer = buffer.split(b"\n", 1)
        if line.strip():
            lines.append(line)
    return lines, buffer
