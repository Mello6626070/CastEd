import cv2
import numpy as np
import mss
import threading
import time
import uuid
import socket
import os
import shutil
import subprocess
try:
    import simpleaudio as sa
except ImportError:
    sa = None
from flask import Flask, Response, request
from waitress import serve
import tkinter as tk
from tkinter import ttk, filedialog
from PIL import ImageGrab
from plyer import notification

app = Flask(__name__)

latest_frame = None
frame_lock = threading.Lock()
active_clients = {}
clients_lock = threading.Lock()
streaming_active = False
current_gui = None
is_muted = False


def play_sound():
    if is_muted:
        return
    if os.name == "nt":
        try:
            import winsound
            winsound.PlaySound("join.wav", winsound.SND_FILENAME | winsound.SND_ASYNC)
            return
        except Exception:
            pass
    for player in ("pw-play", "paplay", "aplay", "afplay"):
        if shutil.which(player):
            try:
                subprocess.Popen([player, "join.wav"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except Exception:
                pass
    if sa:
        try:
            wav_obj = sa.WaveObject.from_wave_file("join.wav")
            wav_obj.play()
        except Exception as e:
            print(f"Audio Error: {e}")


def capture_loop():
    global latest_frame
    with mss.mss() as sct:
        monitor = sct.monitors[0]

        while True:
            start_time = time.time()
            if streaming_active:
                frame = None
                try:
                    sct_img = sct.grab(monitor)
                    img = np.array(sct_img)
                    frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                except Exception:
                    try:
                        cap = ImageGrab.grab()
                        if cap:
                            img = np.array(cap)
                            frame = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
                    except:
                        frame = None

                if frame is not None:
                    h, w = frame.shape[:2]
                    if w > 1280:
                        new_w = 1280
                        new_h = int((new_w / w) * h)
                        frame = cv2.resize(
                            frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR
                        )

                    ok, buffer = cv2.imencode(
                        ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 30]
                    )
                    if ok:
                        with frame_lock:
                            latest_frame = buffer.tobytes()

                elapsed = time.time() - start_time
                time.sleep(max(0, 0.033 - elapsed))
            else:
                with frame_lock:
                    latest_frame = None
                time.sleep(0.5)


@app.route("/")
def index():
    name = request.args.get("name")
    if not name:
        return """
        <body style="background:#1e1e2e; color:#cdd6f4; font-family:sans-serif; text-align:center; padding-top:100px;">
            <h1 style="color:#f5c2e7; font-size: 3em;">CastEDU</h1>
            <form action="/" method="get">
                <input type="text" name="name" placeholder="Enter Your Name" required
                       style="padding:15px; border-radius:8px; border:none; width:280px; background:#313244; color:white;">
                <br><br>
                <button type="submit" style="padding:15px 30px; background:#a6e3a1; border:none; border-radius:8px; cursor:pointer; font-weight:bold;">JOIN</button>
            </form>
        </body>
        """
    return f"""
    <body style="background:#1e1e2e; color:#cdd6f4; font-family:sans-serif; text-align:center; margin:0;">
        <img src="/stream?name={name}" style="max-width:95vw; max-height:85vh; margin-top:15px; border:2px solid #313244;">
    </body>
    """


@app.route("/stream")
def stream():
    client_id = str(uuid.uuid4())[:8]
    client_ip = request.remote_addr
    client_name = request.args.get("name", "Guest")

    with clients_lock:
        active_clients[client_id] = {"ip": client_ip, "name": client_name}

    if current_gui:
        current_gui.log_message(f"[+] {client_name} joined.")
        threading.Thread(target=play_sound, daemon=True).start()
        if notification and hasattr(notification, "notify"):
            pass

    return Response(
        mjpeg_streamer(client_id), mimetype="multipart/x-mixed-replace; boundary=frame"
    )


def mjpeg_streamer(client_id):
    try:
        while True:
            with frame_lock:
                frame = latest_frame
            if frame and streaming_active:
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")
            time.sleep(0.04)
    finally:
        with clients_lock:
            if client_id in active_clients:
                user = active_clients.pop(client_id)
                if current_gui:
                    current_gui.log_message(f"[-] {user['name']} left.")
                    threading.Thread(target=play_sound, daemon=True).start()
                    if notification and hasattr(notification, "notify"):
                        pass


class CastEdGUI:
    def __init__(self, root):
        self.root = root
        root.title("CastEDU")
        root.geometry("420x720")
        root.configure(bg="#1E1E2E")
        self.c = {
            "bg": "#1E1E2E",
            "fg": "#CDD6F4",
            "acc": "#F5C2E7",
            "list": "#313244",
            "on": "#A6E3A1",
            "off": "#F38BA8",
        }

        tk.Label(
            root,
            text="CastEd",
            font=("Segoe UI", 32, "bold"),
            bg=self.c["bg"],
            fg=self.c["acc"],
        ).pack(pady=20)

        self.btn_toggle = tk.Button(
            root,
            text="START STREAM",
            font=("Segoe UI", 12, "bold"),
            bg=self.c["on"],
            fg=self.c["bg"],
            relief="flat",
            command=self.toggle_stream,
        )
        self.btn_toggle.pack(fill="x", padx=40, pady=10)

        self.btn_mute = tk.Button(
            root,
            text="SOUND ON",
            font=("Segoe UI", 10),
            bg=self.c["on"],
            fg=self.c["bg"],
            relief="flat",
            command=self.toggle_mute,
        )
        self.btn_mute.pack(fill="x", padx=40, pady=5)

        self.ip_lbl = tk.Label(
            root,
            text=f"URL: http://{self.get_ip()}:5000 IP: {self.get_ip()}",
            bg=self.c["bg"],
            fg=self.c["fg"],
        )
        self.ip_lbl.pack()

        self.u_list = tk.Listbox(
            root,
            bg=self.c["list"],
            fg=self.c["fg"],
            borderwidth=0,
            height=5,
            highlightthickness=0,
        )
        self.u_list.pack(fill="x", padx=20, pady=20)

        self.log_box = tk.Text(
            root,
            bg=self.c["list"],
            fg=self.c["fg"],
            font=("Consolas", 9),
            height=10,
            state="disabled",
            borderwidth=0,
        )
        self.log_box.pack(fill="both", expand=True, padx=20, pady=5)

        tk.Button(
            root,
            text="Launch File",
            bg=self.c["acc"],
            relief="flat",
            pady=5,
            command=self.open_file,
        ).pack(fill="x", padx=20, pady=20)

        self.update_ui()

    def toggle_stream(self):
        global streaming_active
        streaming_active = not streaming_active
        self.btn_toggle.config(
            text="STOP STREAM" if streaming_active else "START STREAM",
            bg=self.c["off"] if streaming_active else self.c["on"],
        )
        self.log_message("Stream " + ("Started" if streaming_active else "Paused"))

    def toggle_mute(self):
        global is_muted
        is_muted = not is_muted
        self.btn_mute.config(
            text="SOUND OFF" if is_muted else "SOUND ON",
            bg=self.c["off"] if is_muted else self.c["on"],
        )

    def log_message(self, msg):
        self.log_box.config(state="normal")
        self.log_box.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        self.log_box.see(tk.END)
        self.log_box.config(state="disabled")

    def open_file(self):
        path = filedialog.askopenfilename()
        if path:
            if os.name == "nt":
                os.startfile(path)
            else:
                subprocess.call(("xdg-open", path))

    def update_ui(self):
        self.u_list.delete(0, tk.END)
        with clients_lock:
            for d in active_clients.values():
                self.u_list.insert(tk.END, f"{d['name']} ({d['ip']})")
        self.root.after(2000, self.update_ui)

    def get_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        except:
            return "127.0.0.1"


def start_flask():
    play_sound()
    app.run(host="0.0.0.0", port=5000, threaded=True, debug=False)


if __name__ == "__main__":
    threading.Thread(target=capture_loop, daemon=True).start()

    threading.Thread(target=start_flask, daemon=True).start()

    root = tk.Tk()
    current_gui = CastEdGUI(root)
    root.mainloop()
