import tkinter as tk
import mss
import mss.tools

start_x = start_y = 0
rect = None


def on_mouse_down(event):
    global start_x, start_y, rect
    start_x, start_y = event.x, event.y
    rect = canvas.create_rectangle(start_x, start_y, start_x, start_y, outline="red")


def on_mouse_drag(event):
    canvas.coords(rect, start_x, start_y, event.x, event.y)


def on_mouse_up(event):
    x1, y1 = start_x, start_y
    x2, y2 = event.x, event.y

    # normalize coordinates
    left = min(x1, x2)
    top = min(y1, y2)
    width = abs(x2 - x1)
    height = abs(y2 - y1)

    root.destroy()

    with mss.mss() as sct:
        monitor = {"top": top, "left": left, "width": width, "height": height}
        img = sct.grab(monitor)
        mss.tools.to_png(img.rgb, img.size, output="screenshot_with_mouse.png")

    print("Saved as snip.png")


# --- fullscreen transparent overlay ---
root = tk.Tk()
root.attributes("-fullscreen", True)
root.attributes("-alpha", 0.3)  # semi-transparent
root.configure(bg="black")

canvas = tk.Canvas(root, cursor="cross", bg="black")
canvas.pack(fill=tk.BOTH, expand=True)

canvas.bind("<ButtonPress-1>", on_mouse_down)
canvas.bind("<B1-Motion>", on_mouse_drag)
canvas.bind("<ButtonRelease-1>", on_mouse_up)

root.mainloop()