import threading
from collections.abc import Callable

import pystray
from PIL import Image, ImageDraw, ImageFont


def _build_icon_image() -> Image.Image:
    """Generate a simple in-memory 64x64 shield-themed icon."""
    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Shield base
    draw.rounded_rectangle((8, 4, 56, 50), radius=12, fill=(20, 90, 190, 255))
    draw.polygon([(12, 44), (52, 44), (32, 60)], fill=(20, 90, 190, 255))

    # Border and center mark
    draw.rounded_rectangle((10, 6, 54, 46), radius=10, outline=(240, 245, 255, 255), width=2)
    draw.polygon([(14, 43), (50, 43), (32, 56)], outline=(240, 245, 255, 255), fill=(20, 90, 190, 255))

    # Center letter
    font = ImageFont.load_default()
    draw.text((26, 20), "P", fill=(255, 255, 255, 255), font=font)
    return image


def run_system_tray(
    shutdown_event: threading.Event,
    on_quit: Callable[[], None] | None = None,
) -> None:
    """Run the tray icon loop on the calling thread until quit/shutdown."""
    icon = pystray.Icon("privex-firewall", _build_icon_image(), "Privex Firewall")

    def _quit_action(icon_obj: pystray.Icon, _item: pystray.MenuItem) -> None:
        shutdown_event.set()
        if on_quit is not None:
            on_quit()
        icon_obj.stop()

    icon.menu = pystray.Menu(
        pystray.MenuItem("Privex Firewall: Active", None, enabled=False),
        pystray.MenuItem("Quit", _quit_action),
    )

    # Ensure tray closes if an external shutdown is triggered.
    def _external_shutdown_watcher() -> None:
        shutdown_event.wait()
        icon.stop()

    watcher = threading.Thread(target=_external_shutdown_watcher, name="tray-shutdown-watcher", daemon=True)
    watcher.start()
    icon.run()