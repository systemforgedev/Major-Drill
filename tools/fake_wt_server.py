"""A pretend War Thunder map server on port 8111, for testing live mode
without the game. It moves a 'Player' marker in a circle and posts a kill
feed line now and then. Usage: python tools/fake_wt_server.py [seconds]"""
import io
import json
import math
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

START = time.time()
LENGTH = float(sys.argv[1]) if len(sys.argv) > 1 else 120


def _map_png():
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (512, 512), (52, 66, 48))
    d = ImageDraw.Draw(img)
    for i in range(0, 512, 64):
        d.line([(i, 0), (i, 512)], fill=(80, 90, 70))
        d.line([(0, i), (512, i)], fill=(80, 90, 70))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


MAP = _map_png()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, ctype="application/json"):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        t = time.time() - START
        live = t < LENGTH
        if self.path.startswith("/map_info.json"):
            return self._send({"valid": live, "grid_steps": [200, 200], "map_min": [-2048, -2048], "map_max": [2048, 2048]})
        if self.path.startswith("/map_obj.json"):
            objs = [{"type": "ground_model", "icon": "MediumTank", "x": 0.2, "y": 0.8}]
            if live and not (20 < t % 45 < 26):  # "dies" for a few seconds every 45 s
                objs.append({"type": "ground_model", "icon": "Player",
                             "x": 0.5 + 0.3 * math.cos(t / 10), "y": 0.5 + 0.3 * math.sin(t / 10), "dx": 0, "dy": 1})
            return self._send(objs)
        if self.path.startswith("/hudmsg"):
            n = int(t // 7)
            dmg = [{"id": i + 1, "msg": ("Tester (T-34) destroyed Enemy (Pz.IV)" if i % 2 else "Enemy (Tiger) destroyed Tester (T-34)"),
                    "time": i * 7} for i in range(n)]
            last = int(self.path.split("lastDmg=")[-1]) if "lastDmg=" in self.path else 0
            return self._send({"events": [], "damage": [d for d in dmg if d["id"] > last]})
        if self.path.startswith("/map.img"):
            return self._send(MAP, "image/png")
        self.send_response(404)
        self.end_headers()


if __name__ == "__main__":
    print(f"fake War Thunder map server on http://127.0.0.1:8111 for {LENGTH:.0f}s")
    ThreadingHTTPServer(("127.0.0.1", 8111), H).serve_forever()
