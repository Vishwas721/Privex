import ctypes
from queue import Empty, Queue
import threading


class _NoOpOverlayManager:
    """No-op overlay manager used for non-Windows platforms or setup failures."""

    def start(self) -> None:
        return

    def set_boxes(self, boxes: list[tuple[int, int, int, int]]) -> None:
        return

    def clear(self) -> None:
        return


class WindowsRedactionOverlayManager:
    """Windows click-through transparent overlay that renders black redaction rectangles."""

    GWL_EXSTYLE = -20
    WS_EX_LAYERED = 0x00080000
    WS_EX_TRANSPARENT = 0x00000020
    WS_EX_TOOLWINDOW = 0x00000080

    def __init__(self) -> None:
        self._commands: Queue[tuple[str, list[tuple[int, int, int, int]]]] = Queue()
        self._thread: threading.Thread | None = None
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._thread = threading.Thread(target=self._run_tk_loop, daemon=True)
        self._thread.start()
        self._started = True

    def set_boxes(self, boxes: list[tuple[int, int, int, int]]) -> None:
        if not self._started:
            return
        print(f"[Overlay] Received command to draw {len(boxes)} boxes.")
        self._commands.put(("set", boxes))

    def clear(self) -> None:
        self.set_boxes([])

    def _apply_click_through_style(self, hwnd: int) -> None:
        user32 = ctypes.windll.user32
        ex_style = user32.GetWindowLongW(hwnd, self.GWL_EXSTYLE)
        ex_style |= self.WS_EX_LAYERED | self.WS_EX_TRANSPARENT | self.WS_EX_TOOLWINDOW
        user32.SetWindowLongW(hwnd, self.GWL_EXSTYLE, ex_style)

    def _run_tk_loop(self) -> None:
        try:
            import tkinter as tk

            root = tk.Tk()
            root.title("Privex Redaction Overlay")
            root.overrideredirect(True)
            root.attributes("-topmost", True)

            # Transparent color-key background so only drawn rectangles are visible.
            transparent_key = "#00ff00"
            screen_w = root.winfo_screenwidth()
            screen_h = root.winfo_screenheight()
            root.geometry(f"{screen_w}x{screen_h}+0+0")
            root.configure(bg=transparent_key)
            root.wm_attributes("-transparentcolor", transparent_key)

            canvas = tk.Canvas(
                root,
                bg=transparent_key,
                highlightthickness=0,
                borderwidth=0,
            )
            canvas.pack(fill="both", expand=True)

            # 🛑 NEW: Force Tkinter to finish drawing and register with the Windows OS first!
            root.update_idletasks()
            root.update()

            # Safely get the true OS-level Window Handle (HWND)
            hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
            if not hwnd:  # Fallback if overrideredirect causes GetParent to return 0
                hwnd = int(root.winfo_id())

            # NOW it is safe to apply the click-through hack
            self._apply_click_through_style(hwnd)
            current_boxes: list[tuple[int, int, int, int]] = []

            def redraw() -> None:
                print(f"[Overlay] Redrawing Canvas with {len(current_boxes)} rectangles.")
                canvas.delete("all")
                for x1, y1, x2, y2 in current_boxes:
                    canvas.create_rectangle(x1, y1, x2, y2, fill="black", outline="black")

            def pump_commands() -> None:
                nonlocal current_boxes
                changed = False
                while True:
                    try:
                        command, payload = self._commands.get_nowait()
                    except Empty:
                        break

                    if command == "set":
                        current_boxes = payload
                        changed = True

                if changed:
                    redraw()

                root.after(33, pump_commands)

            pump_commands()
            root.mainloop()
        except Exception as exc:
            print(f"[frame-worker] overlay initialization failed: {exc}")


def _get_primary_screen_size() -> tuple[int, int]:
    """Return the native primary monitor size on Windows."""
    user32 = ctypes.windll.user32
    return int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))


def _scale_overlay_boxes(
    boxes: list[tuple[int, int, int, int]],
    screen_width: int,
    screen_height: int,
    inference_width: int,
    inference_height: int,
) -> list[tuple[int, int, int, int]]:
    """Scale YOLO coordinates from inference pixels to native screen pixels."""
    if inference_width <= 0 or inference_height <= 0:
        return boxes

    scale_x = screen_width / inference_width
    scale_y = screen_height / inference_height

    scaled_boxes: list[tuple[int, int, int, int]] = []
    for x1, y1, x2, y2 in boxes:
        scaled_boxes.append(
            (
                int(round(x1 * scale_x)),
                int(round(y1 * scale_y)),
                int(round(x2 * scale_x)),
                int(round(y2 * scale_y)),
            )
        )

    return scaled_boxes