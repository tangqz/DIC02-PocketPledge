"""Vision Debugger — watches latest_vision_input.jpg and displays it at
native resolution inside a scrollable tkinter window.

Controls:
  - Mouse-wheel / trackpad: scroll vertically
  - Escape / close window: quit
"""

import os
import time
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_PATH = os.path.join(SCRIPT_DIR, "..", "latest_vision_input.jpg")
IMAGE_PATH = os.path.abspath(IMAGE_PATH)

POLL_MS = 200  # check file every 200ms
MAX_WIN_W = 1200
MAX_WIN_H = 800


class VisionDebugger:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Vision Debugger")
        self.root.configure(bg="#1e1e1e")

        # Canvas + scrollbar
        self.canvas = tk.Canvas(self.root, bg="#1e1e1e", highlightthickness=0)
        self.vbar = ttk.Scrollbar(self.root, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vbar.set)

        self.vbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", lambda e: self.canvas.yview_scroll(-3, "units"))
        self.canvas.bind_all("<Button-5>", lambda e: self.canvas.yview_scroll(3, "units"))
        self.root.bind("<Escape>", lambda e: self.root.destroy())

        self._image_id = None
        self._photo: ImageTk.PhotoImage | None = None
        self._last_mtime: float = 0

        self.root.after(POLL_MS, self._poll)

    def _on_mousewheel(self, event: tk.Event) -> None:
        # Windows: event.delta is ±120 per notch
        self.canvas.yview_scroll(int(-event.delta / 120) * 3, "units")

    def _poll(self) -> None:
        try:
            if os.path.exists(IMAGE_PATH):
                mtime = os.path.getmtime(IMAGE_PATH)
                if mtime != self._last_mtime:
                    self._load_image()
                    self._last_mtime = mtime
        except Exception as exc:
            print(f"[Vision Debugger] error: {exc}")
        self.root.after(POLL_MS, self._poll)

    def _load_image(self) -> None:
        try:
            pil_img = Image.open(IMAGE_PATH)
        except Exception as exc:
            print(f"[Vision Debugger] failed to open image: {exc}")
            return

        img_w, img_h = pil_img.size
        print(f"[Vision Debugger] loaded image: {img_w}x{img_h}")

        self._photo = ImageTk.PhotoImage(pil_img)

        if self._image_id is not None:
            self.canvas.delete(self._image_id)
        self._image_id = self.canvas.create_image(0, 0, anchor=tk.NW, image=self._photo)
        self.canvas.configure(scrollregion=(0, 0, img_w, img_h))

        # Resize window to fit image width (capped), full height (capped)
        win_w = min(img_w + 20, MAX_WIN_W)  # +20 for scrollbar
        win_h = min(img_h, MAX_WIN_H)
        self.root.geometry(f"{win_w}x{win_h}")

    def run(self) -> None:
        print(f"Watching {IMAGE_PATH} for changes...")
        self.root.mainloop()


if __name__ == "__main__":
    VisionDebugger().run()
