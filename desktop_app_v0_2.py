import csv
import html
import math
import os
import tkinter as tk
from dataclasses import dataclass
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageDraw, ImageFont, ImageTk


APP_VERSION = "0.2"
EXPORT_DPI = 600
FIGURE_SIZES = {
    "Single column (89 mm)": (89, 64),
    "Double column (183 mm)": (183, 110),
}
CHART_TYPES = ["EIS Nyquist", "Long Cycling", "Voltage-Capacity", "dQ/dV", "Rate Performance", "CV", "GITT"]
COLORS = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#F0E442", "#000000"]


@dataclass
class Series:
    name: str
    points: list
    color: str
    dashed: bool = False


class ElectrochemicalData:
    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        self.kind = "generic"
        self.headers = []
        self.rows = []
        self.cycles = []
        self.steps = []
        self.records = []
        self._parse()

    def _parse(self):
        rows = read_rows(self.path)
        if not rows:
            return
        if chi_header_index(rows) is not None:
            self.kind = "chi_eis"
            self._parse_chi(rows)
        elif is_land_like(rows):
            self.kind = "land_like"
            self._parse_land(rows)
        else:
            self.headers = unique_headers(rows[0])
            self.rows = [row_dict(self.headers, row) for row in rows[1:]]

    def _parse_chi(self, rows):
        start = chi_header_index(rows)
        self.headers = unique_headers(rows[start])
        self.rows = []
        for row in rows[start + 1:]:
            item = row_dict(self.headers, row)
            if is_number(to_float(item.get(self.headers[0]))) and is_number(to_float(item.get(self.headers[1]))):
                self.rows.append(item)

    def _parse_land(self, rows):
        cycle_headers = unique_headers(rows[0])
        step_headers = unique_headers(rows[1][1:])
        point_headers = unique_headers(rows[2][2:])
        cycle = None
        step = None
        for row in rows[3:]:
            padded = row + [""] * 14
            if padded[0].strip():
                cycle = parse_int(padded[0])
                item = row_dict(cycle_headers, padded)
                item["循环号"] = cycle
                self.cycles.append(item)
            elif padded[1].strip():
                item = row_dict(step_headers, padded[1:])
                step = parse_int(item.get("工步号"))
                item["循环号"] = cycle
                item["工步号"] = step
                self.steps.append(item)
            elif padded[2].strip():
                item = row_dict(point_headers, padded[2:])
                item["循环号"] = cycle
                item["工步号"] = step
                item["工步类型"] = find_step_type(self.steps, cycle, step)
                self.records.append(item)
        self.rows = self.records
        self.headers = sorted({key for row in self.cycles + self.steps + self.records for key in row})

    def summary(self):
        if self.kind == "chi_eis":
            return f"{self.name}: CHI EIS data, {len(self.rows)} points"
        if self.kind == "land_like":
            return f"{self.name}: {len(self.cycles)} cycles, {len(self.steps)} steps, {len(self.records)} data points"
        return f"{self.name}: {len(self.rows)} rows, {len(self.headers)} columns"


class RasterPlot:
    def __init__(self, width=980, height=640):
        self.width = width
        self.height = height
        self.scale = max(width / 980, 1)
        self.image = Image.new("RGB", (width, height), "white")
        self.draw = ImageDraw.Draw(self.image)
        self.font = load_font(round(14 * self.scale))
        self.small = load_font(round(12 * self.scale))
        self.title = load_font(round(18 * self.scale))
        self.axis_w = max(1, round(1.1 * self.scale))
        self.line_w = max(2, round(1.6 * self.scale))
        self.mark_r = max(3, round(3 * self.scale))

    def render(self, title, x_label, y_label, series, y2_series=None, y2_label="", equal_aspect=False):
        y2_series = y2_series or []
        self.image = Image.new("RGB", (self.width, self.height), "white")
        self.draw = ImageDraw.Draw(self.image)
        margin = {
            "left": 78 * self.scale,
            "right": (92 if y2_series else 34) * self.scale,
            "top": 58 * self.scale,
            "bottom": 78 * self.scale,
        }
        plot = (margin["left"], margin["top"], self.width - margin["right"], self.height - margin["bottom"])
        points = [point for item in series for point in item.points]
        if not points:
            self.text_center((self.width / 2, self.height / 2), "No valid data", self.title)
            return self.image
        xdom = pad_domain(extent([p[0] for p in points]))
        ydom = pad_domain(extent([p[1] for p in points]))
        if equal_aspect:
            xdom, ydom = equalize_domains(xdom, ydom)
        y2dom = None
        if y2_series:
            y2dom = pad_domain(extent([p[1] for s in y2_series for p in s.points]))
        sx, sy = scales(plot, xdom, ydom)
        sy2 = scales(plot, xdom, y2dom)[1] if y2dom else None
        self.text_center((self.width / 2, 28 * self.scale), title, self.title)
        self.axes(plot, xdom, ydom, sx, sy, x_label, y_label)
        if y2dom:
            self.right_axis(plot, y2dom, sy2, y2_label)
        for item in series:
            self.series(item, sx, sy)
        for item in y2_series:
            self.series(item, sx, sy2)
        self.legend(series + y2_series)
        return self.image

    def axes(self, plot, xdom, ydom, sx, sy, x_label, y_label):
        left, top, right, bottom = plot
        self.draw.rectangle((left, top, right, bottom), outline="#000000", width=self.axis_w)
        tick_len = max(5, round(7 * self.scale))
        for tick in ticks(xdom):
            x = sx(tick)
            self.draw.line((x, bottom, x, bottom - tick_len), fill="#000000", width=self.axis_w)
            self.draw.line((x, top, x, top + tick_len * 0.7), fill="#000000", width=self.axis_w)
            self.text_center((x, bottom + 22 * self.scale), fmt(tick), self.small)
        for tick in ticks(ydom):
            y = sy(tick)
            self.draw.line((left, y, left + tick_len, y), fill="#000000", width=self.axis_w)
            self.draw.line((right, y, right - tick_len * 0.7, y), fill="#000000", width=self.axis_w)
            self.text_right((left - 9 * self.scale, y - 7 * self.scale), fmt(tick), self.small)
        self.text_center(((left + right) / 2, bottom + 52 * self.scale), x_label, self.font)
        self.rotated_text((22 * self.scale, (top + bottom) / 2), y_label, self.font)

    def right_axis(self, plot, domain, sy, label):
        _left, top, right, bottom = plot
        self.draw.line((right, top, right, bottom), fill="#000000", width=self.axis_w)
        for tick in ticks(domain):
            y = sy(tick)
            self.draw.line((right, y, right - 7 * self.scale, y), fill="#000000", width=self.axis_w)
            self.draw.text((right + 9 * self.scale, y - 7 * self.scale), fmt(tick), fill="#000000", font=self.small)
        self.rotated_text((self.width - 24 * self.scale, (top + bottom) / 2), label, self.font, clockwise=True)

    def series(self, item, sx, sy):
        pts = [(sx(x), sy(y)) for x, y in item.points if is_number(x) and is_number(y)]
        if len(pts) < 2:
            return
        if item.dashed:
            dashed_line(self.draw, pts, item.color, self.line_w, 8 * self.scale, 6 * self.scale)
        else:
            self.draw.line(pts, fill=item.color, width=self.line_w, joint="curve")
        step = max(len(pts) // 34, 1)
        for i, (x, y) in enumerate(pts):
            if i % step == 0 or i == len(pts) - 1:
                r = self.mark_r
                self.draw.ellipse((x - r, y - r, x + r, y + r), fill="#ffffff", outline=item.color, width=self.line_w)

    def legend(self, series):
        x = self.width - 218 * self.scale
        y = 62 * self.scale
        for i, item in enumerate(series[:9]):
            yy = y + i * 21 * self.scale
            self.draw.line((x, yy, x + 26 * self.scale, yy), fill=item.color, width=self.line_w)
            self.draw.ellipse((x + 10 * self.scale, yy - 3 * self.scale, x + 16 * self.scale, yy + 3 * self.scale), fill="#ffffff", outline=item.color, width=self.line_w)
            self.draw.text((x + 34 * self.scale, yy - 8 * self.scale), item.name[:22], fill="#000000", font=self.small)

    def text_center(self, xy, text, font):
        box = self.draw.textbbox((0, 0), text, font=font)
        self.draw.text((xy[0] - (box[2] - box[0]) / 2, xy[1] - (box[3] - box[1]) / 2), text, fill="#000000", font=font)

    def text_right(self, xy, text, font):
        box = self.draw.textbbox((0, 0), text, font=font)
        self.draw.text((xy[0] - (box[2] - box[0]), xy[1]), text, fill="#000000", font=font)

    def rotated_text(self, xy, text, font, clockwise=False):
        box = self.draw.textbbox((0, 0), text, font=font)
        label = Image.new("RGBA", (box[2] - box[0] + 8, box[3] - box[1] + 8), (255, 255, 255, 0))
        ImageDraw.Draw(label).text((4, 4), text, font=font, fill="#000000")
        rot = label.rotate(-90 if clockwise else 90, expand=True)
        self.image.paste(rot, (int(xy[0] - rot.width / 2), int(xy[1] - rot.height / 2)), rot)


class SvgPlot:
    def __init__(self, width_mm, height_mm):
        self.width_mm = width_mm
        self.height_mm = height_mm
        self.width = width_mm * 3.7795275591
        self.height = height_mm * 3.7795275591
        self.el = []

    def render(self, title, x_label, y_label, series, y2_series=None, y2_label="", equal_aspect=False):
        y2_series = y2_series or []
        self.el = []
        plot = (52, 26, self.width - (52 if y2_series else 20), self.height - 44)
        points = [p for s in series for p in s.points]
        if not points:
            self.text(self.width / 2, self.height / 2, "No valid data", 8, "middle")
            return self.doc()
        xdom = pad_domain(extent([p[0] for p in points]))
        ydom = pad_domain(extent([p[1] for p in points]))
        if equal_aspect:
            xdom, ydom = equalize_domains(xdom, ydom)
        y2dom = pad_domain(extent([p[1] for s in y2_series for p in s.points])) if y2_series else None
        sx, sy = scales(plot, xdom, ydom)
        sy2 = scales(plot, xdom, y2dom)[1] if y2dom else None
        self.text(self.width / 2, 13, title, 7.5, "middle", "bold")
        self.axes(plot, xdom, ydom, sx, sy, x_label, y_label)
        if y2dom:
            self.right_axis(plot, y2dom, sy2, y2_label)
        for item in series:
            self.series(item, sx, sy)
        for item in y2_series:
            self.series(item, sx, sy2)
        self.legend(series + y2_series, plot[2] - 72, plot[1] + 7)
        return self.doc()

    def axes(self, plot, xdom, ydom, sx, sy, x_label, y_label):
        l, t, r, b = plot
        self.rect(l, t, r - l, b - t)
        for v in ticks(xdom):
            x = sx(v)
            self.line(x, b, x, b - 4)
            self.line(x, t, x, t + 3)
            self.text(x, b + 12, fmt(v), 6, "middle")
        for v in ticks(ydom):
            y = sy(v)
            self.line(l, y, l + 4, y)
            self.line(r, y, r - 3, y)
            self.text(l - 5, y + 2, fmt(v), 6, "end")
        self.text((l + r) / 2, b + 30, x_label, 7, "middle")
        self.text(12, (t + b) / 2, y_label, 7, "middle", rotate=-90)

    def right_axis(self, plot, domain, sy, label):
        _l, t, r, b = plot
        self.line(r, t, r, b)
        for v in ticks(domain):
            y = sy(v)
            self.line(r, y, r - 4, y)
            self.text(r + 5, y + 2, fmt(v), 6)
        self.text(self.width - 10, (t + b) / 2, label, 7, "middle", rotate=90)

    def series(self, item, sx, sy):
        pts = [(sx(x), sy(y)) for x, y in item.points if is_number(x) and is_number(y)]
        if len(pts) < 2:
            return
        d = " ".join(f"{'M' if i == 0 else 'L'} {x:.2f} {y:.2f}" for i, (x, y) in enumerate(pts))
        dash = ' stroke-dasharray="4 3"' if item.dashed else ""
        self.el.append(f'<path d="{d}" fill="none" stroke="{item.color}" stroke-width="1.15" stroke-linejoin="round" stroke-linecap="round"{dash}/>')
        step = max(len(pts) // 34, 1)
        for i, (x, y) in enumerate(pts):
            if i % step == 0 or i == len(pts) - 1:
                self.circle(x, y, 1.8, item.color)

    def legend(self, series, x, y):
        for i, item in enumerate(series[:9]):
            yy = y + i * 8
            self.line(x, yy, x + 12, yy, item.color, 1.15)
            self.circle(x + 6, yy, 1.6, item.color)
            self.text(x + 16, yy + 2.3, item.name[:22], 6)

    def line(self, x1, y1, x2, y2, color="#000000", width=0.8):
        self.el.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="{color}" stroke-width="{width}"/>')

    def rect(self, x, y, w, h):
        self.el.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" fill="none" stroke="#000000" stroke-width="0.8"/>')

    def circle(self, x, y, r, color):
        self.el.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r:.2f}" fill="#ffffff" stroke="{color}" stroke-width="1"/>')

    def text(self, x, y, text, size, anchor="start", weight="normal", rotate=None):
        rot = f' transform="rotate({rotate} {x:.2f} {y:.2f})"' if rotate is not None else ""
        self.el.append(f'<text x="{x:.2f}" y="{y:.2f}" font-family="Arial, Helvetica, sans-serif" font-size="{size}" font-weight="{weight}" fill="#000000" text-anchor="{anchor}"{rot}>{html.escape(str(text))}</text>')

    def doc(self):
        body = "\n  ".join(self.el)
        return f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width_mm}mm" height="{self.height_mm}mm" viewBox="0 0 {self.width:.2f} {self.height:.2f}">\n  <rect width="100%" height="100%" fill="#ffffff"/>\n  {body}\n</svg>\n'


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Electrochemical Plotting Tool v{APP_VERSION}")
        self.geometry("1220x760")
        self.minsize(980, 640)
        self.data = None
        self.current_image = None
        self.current_photo = None
        self.chart_type = tk.StringVar(value="EIS Nyquist")
        self.figure_size = tk.StringVar(value="Single column (89 mm)")
        self.output_path = tk.StringVar(value="")
        self.status = tk.StringVar(value="Select a data file to start.")
        self.build_ui()

    def build_ui(self):
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        side = ttk.Frame(self, padding=16)
        side.grid(row=0, column=0, sticky="ns")
        side.columnconfigure(0, weight=1)
        ttk.Label(side, text=f"Electrochemical Plotting Tool v{APP_VERSION}", font=("Segoe UI", 15, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(side, text="Local desktop plotting with Nature-style export.", wraplength=300).grid(row=1, column=0, sticky="w", pady=(4, 14))
        ttk.Button(side, text="Select data file", command=self.select_file).grid(row=2, column=0, sticky="ew", pady=4)
        ttk.Label(side, textvariable=self.status, wraplength=310).grid(row=3, column=0, sticky="w", pady=(4, 14))
        ttk.Label(side, text="Chart type").grid(row=4, column=0, sticky="w")
        ttk.Combobox(side, textvariable=self.chart_type, values=CHART_TYPES, state="readonly").grid(row=5, column=0, sticky="ew", pady=(4, 12))
        ttk.Label(side, text="Figure size").grid(row=6, column=0, sticky="w")
        ttk.Combobox(side, textvariable=self.figure_size, values=list(FIGURE_SIZES), state="readonly").grid(row=7, column=0, sticky="ew", pady=(4, 12))
        ttk.Button(side, text="Render", command=self.render).grid(row=8, column=0, sticky="ew", pady=4)
        ttk.Button(side, text="Export PNG (600 dpi)", command=self.export_png).grid(row=9, column=0, sticky="ew", pady=4)
        ttk.Button(side, text="Export SVG", command=self.export_svg).grid(row=10, column=0, sticky="ew", pady=4)
        self.info = tk.Text(side, width=38, height=18, wrap="word")
        self.info.grid(row=11, column=0, sticky="nsew", pady=(16, 0))
        self.info.insert("1.0", "Supported: EIS, long cycling, voltage-capacity, dQ/dV, rate, CV, GITT.\n")
        self.info.configure(state="disabled")
        main = ttk.Frame(self, padding=(0, 16, 16, 16))
        main.grid(row=0, column=1, sticky="nsew")
        main.rowconfigure(0, weight=1)
        main.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(main, bg="#ffffff", highlightthickness=1, highlightbackground="#d7dee8")
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.create_text(490, 310, text="Select a data file", fill="#657386", font=("Segoe UI", 18, "bold"))

    def select_file(self):
        path = filedialog.askopenfilename(title="Select electrochemical data", filetypes=[("Data files", "*.csv *.txt *.tsv *.dat"), ("All files", "*.*")])
        if not path:
            return
        try:
            self.data = ElectrochemicalData(path)
        except Exception as exc:
            messagebox.showerror("Import failed", str(exc))
            return
        self.status.set(self.data.summary())
        self.update_info()
        self.render()

    def render(self):
        if not self.data:
            return
        title, xl, yl, series, y2, y2l, eq = build_chart(self.data, self.chart_type.get())
        image = RasterPlot(max(self.canvas.winfo_width(), 900), max(self.canvas.winfo_height(), 560)).render(title, xl, yl, series, y2, y2l, eq)
        self.current_image = image
        self.current_photo = ImageTk.PhotoImage(image)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.current_photo, anchor="nw")

    def export_png(self):
        if not self.data:
            messagebox.showinfo("No chart", "Please select data first.")
            return
        path = filedialog.asksaveasfilename(title="Choose PNG output", defaultextension=".png", filetypes=[("PNG image", "*.png")], initialfile="electrochemical-plot.png")
        if not path:
            return
        wmm, hmm = FIGURE_SIZES[self.figure_size.get()]
        title, xl, yl, series, y2, y2l, eq = build_chart(self.data, self.chart_type.get())
        image = RasterPlot(round(wmm / 25.4 * EXPORT_DPI), round(hmm / 25.4 * EXPORT_DPI)).render(title, xl, yl, series, y2, y2l, eq)
        image.save(path, dpi=(EXPORT_DPI, EXPORT_DPI))
        messagebox.showinfo("Export complete", f"Saved to:\n{path}")

    def export_svg(self):
        if not self.data:
            messagebox.showinfo("No chart", "Please select data first.")
            return
        path = filedialog.asksaveasfilename(title="Choose SVG output", defaultextension=".svg", filetypes=[("SVG image", "*.svg")], initialfile="electrochemical-plot.svg")
        if not path:
            return
        wmm, hmm = FIGURE_SIZES[self.figure_size.get()]
        title, xl, yl, series, y2, y2l, eq = build_chart(self.data, self.chart_type.get())
        with open(path, "w", encoding="utf-8") as f:
            f.write(SvgPlot(wmm, hmm).render(title, xl, yl, series, y2, y2l, eq))
        messagebox.showinfo("Export complete", f"Saved to:\n{path}")

    def update_info(self):
        lines = [self.data.summary(), ""]
        if self.data.kind == "chi_eis":
            lines += ["Detected format: CHI EIS text", "EIS Nyquist uses Z' and -Z''.", "Exports: SVG or 600 dpi PNG, Nature-style."]
        elif self.data.kind == "land_like":
            lines += ["Detected format: hierarchical battery CSV", "Cycle, step and point tables extracted."]
        else:
            lines += ["Detected format: generic table", "Columns:"] + self.data.headers[:20]
        self.info.configure(state="normal")
        self.info.delete("1.0", "end")
        self.info.insert("1.0", "\n".join(lines))
        self.info.configure(state="disabled")


def build_chart(data, chart):
    return {
        "Long Cycling": build_long_cycling,
        "Voltage-Capacity": build_voltage_capacity,
        "dQ/dV": build_dqdv,
        "Rate Performance": build_rate,
        "CV": build_cv,
        "GITT": build_gitt,
    }.get(chart, build_eis)(data)


def build_eis(data):
    if data.kind == "chi_eis":
        xcol = eis_col(data.headers, "real")
        ycol = eis_col(data.headers, "imag")
        pts = []
        for row in data.rows:
            x, y = to_float(row.get(xcol)), to_float(row.get(ycol))
            if is_number(x) and is_number(y):
                pts.append((x, -y if y < 0 else y))
        return "EIS Nyquist Plot", "Z' (ohm)", "-Z'' (ohm)", [Series(data.name, pts, COLORS[0])], [], "", False
    return generic_xy(data, "EIS Nyquist Plot", ["zre", "z'", "real"], ["zim", "z''", "imag"], lambda y: -y if y < 0 else y, ("Z' (ohm)", "-Z'' (ohm)"))


def build_long_cycling(data):
    if data.kind == "land_like" and data.cycles:
        charge, discharge, ce = [], [], []
        for row in data.cycles:
            cycle = to_float(row.get("循环号"))
            chg = to_float(row.get("充电比容量(mAh/g)"))
            dis = to_float(row.get("放电比容量(mAh/g)"))
            eff = to_float(row.get("充放电效率(%)"))
            if is_number(cycle) and is_number(chg):
                charge.append((cycle, chg))
            if is_number(cycle) and is_number(dis):
                discharge.append((cycle, dis))
            if is_number(cycle) and is_number(eff):
                ce.append((cycle, eff))
        return "Long Cycling Performance", "Cycle number", "Specific capacity (mAh/g)", [Series("Charge", charge, COLORS[0]), Series("Discharge", discharge, COLORS[1])], [Series("Coulombic efficiency", ce, COLORS[2], True)] if ce else [], "Coulombic efficiency (%)", False
    return generic_xy(data, "Long Cycling", ["cycle", "循环"], ["capacity", "容量"])


def build_voltage_capacity(data):
    if data.kind == "land_like":
        series = []
        for i, (cycle, rows) in enumerate(group_by_cycle(data.records)[:8]):
            pts = valid([(to_float(r.get("比容量(mAh/g)")), to_float(r.get("电压(V)"))) for r in rows])
            if pts:
                series.append(Series(f"Cycle {cycle}", pts, COLORS[i % len(COLORS)]))
        return "Voltage-Capacity", "Specific capacity (mAh/g)", "Voltage (V)", series, [], "", False
    return generic_xy(data, "Voltage-Capacity", ["capacity", "容量"], ["voltage", "电压", "potential"])


def build_dqdv(data):
    _t, _x, _y, base, _y2, _y2l, _eq = build_voltage_capacity(data)
    series = [Series(s.name, smooth(derivative(s.points), 5), COLORS[i % len(COLORS)]) for i, s in enumerate(base) if derivative(s.points)]
    return "dQ/dV", "Voltage (V)", "dQ/dV (mAh/g/V)", series, [], "", False


def build_rate(data):
    _t, xl, yl, series, _y2, _y2l, _eq = build_long_cycling(data)
    dis = [s for s in series if "Discharge" in s.name]
    return "Rate Performance", xl, yl, dis or series, [], "", False


def build_cv(data):
    if data.kind == "land_like":
        series = []
        for i, (cycle, rows) in enumerate(group_by_cycle(data.records)[:8]):
            pts = valid([(to_float(r.get("电压(V)")), to_float(r.get("电流(A)"))) for r in rows])
            if pts:
                series.append(Series(f"Cycle {cycle}", pts, COLORS[i % len(COLORS)]))
        return "Cyclic Voltammetry", "Potential (V)", "Current (A)", series, [], "", False
    return generic_xy(data, "Cyclic Voltammetry", ["potential", "voltage", "电压"], ["current", "电流"])


def build_gitt(data):
    if data.kind == "land_like":
        series = []
        for i, (cycle, rows) in enumerate(group_by_cycle(data.records)[:5]):
            pts = valid([(duration(r.get("总时间")) / 3600, to_float(r.get("电压(V)"))) for r in rows])
            if pts:
                series.append(Series(f"Cycle {cycle}", pts, COLORS[i % len(COLORS)]))
        return "GITT", "Time (h)", "Voltage (V)", series, [], "", False
    return generic_xy(data, "GITT", ["time", "时间"], ["voltage", "电压", "potential"])


def generic_xy(data, title, xh, yh, y_transform=None, labels=None):
    xcol, ycol = find_col(data.headers, xh), find_col(data.headers, yh)
    pts = []
    if xcol and ycol:
        for row in data.rows:
            x, y = to_float(row.get(xcol)), to_float(row.get(ycol))
            if y_transform and is_number(y):
                y = y_transform(y)
            if is_number(x) and is_number(y):
                pts.append((x, y))
    xl, yl = labels or (xcol or "X", ycol or "Y")
    return title, xl, yl, [Series("Data", pts, COLORS[0])], [], "", False


def read_rows(path):
    for enc in ["utf-8-sig", "gbk", "utf-16"]:
        try:
            with open(path, newline="", encoding=enc) as f:
                sample = f.read(4096)
                f.seek(0)
                delimiter = "\t" if sample.count("\t") > sample.count(",") else ","
                return [r for r in csv.reader(f, delimiter=delimiter) if any(c.strip() for c in r)]
        except UnicodeError:
            pass
    raise ValueError("Unable to read data file")


def is_land_like(rows):
    return len(rows) > 3 and "循环号" in rows[0][0] and "工步号" in rows[1][1] and "数据序号" in rows[2][2]


def chi_header_index(rows):
    for i, row in enumerate(rows):
        text = ",".join(row).lower()
        if "freq" in text and "z'" in text and 'z"' in text:
            return i
    return None


def unique_headers(headers):
    seen, out = {}, []
    for i, h in enumerate(headers):
        base = h.strip() or f"Column {i + 1}"
        seen[base] = seen.get(base, 0) + 1
        out.append(base if seen[base] == 1 else f"{base}_{seen[base]}")
    return out


def row_dict(headers, row):
    return {h: row[i].strip() if i < len(row) else "" for i, h in enumerate(headers)}


def find_step_type(steps, cycle, step):
    for item in reversed(steps):
        if item.get("循环号") == cycle and item.get("工步号") == step:
            return item.get("工步类型", "")
    return ""


def group_by_cycle(rows):
    groups = {}
    for row in rows:
        groups.setdefault(row.get("循环号"), []).append(row)
    return list(groups.items())


def eis_col(headers, part):
    for h in headers:
        low = h.lower()
        if part == "real" and ("z'" in low or "zre" in low or "real" in low):
            return h
        if part == "imag" and ('z"' in low or "z''" in low or "zim" in low or "imag" in low):
            return h
    return None


def find_col(headers, hints):
    normed = [(h, norm(h)) for h in headers]
    for hint in hints:
        key = norm(hint)
        for h, value in normed:
            if key in value:
                return h
    return None


def norm(value):
    value = str(value).lower()
    for token in [" ", "_", "-", "/", "(", ")", "[", "]", "'", '"']:
        value = value.replace(token, "")
    return value


def to_float(value):
    try:
        return float(str(value).strip().replace(",", ""))
    except (TypeError, ValueError):
        return math.nan


def parse_int(value):
    num = to_float(value)
    return int(num) if is_number(num) else None


def duration(value):
    parts = str(value or "").strip().split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(parts[0])
    except ValueError:
        return math.nan


def is_number(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def valid(points):
    return [(x, y) for x, y in points if is_number(x) and is_number(y)]


def extent(values):
    values = [v for v in values if is_number(v)]
    return (min(values), max(values)) if values else (0, 1)


def pad_domain(domain):
    lo, hi = domain
    if lo == hi:
        return lo - 1, hi + 1
    pad = (hi - lo) * 0.06
    return (0, hi + pad) if lo >= 0 and lo - pad < 0 else (lo - pad, hi + pad)


def equalize_domains(xdom, ydom):
    xs, ys = xdom[1] - xdom[0], ydom[1] - ydom[0]
    if xs > ys:
        extra = (xs - ys) / 2
        return xdom, (ydom[0] - extra, ydom[1] + extra)
    extra = (ys - xs) / 2
    return (xdom[0] - extra, xdom[1] + extra), ydom


def scales(plot, xdom, ydom):
    l, t, r, b = plot
    return (
        lambda x: l + (x - xdom[0]) / (xdom[1] - xdom[0]) * (r - l),
        lambda y: b - (y - ydom[0]) / (ydom[1] - ydom[0]) * (b - t),
    )


def ticks(domain, count=6):
    lo, hi = domain
    step = (hi - lo) / (count - 1)
    return [lo + i * step for i in range(count)]


def fmt(value):
    if abs(value) >= 1000 or (abs(value) < 0.01 and value != 0):
        return f"{value:.1e}"
    return f"{value:.3f}".rstrip("0").rstrip(".")


def derivative(points):
    out = []
    for (q1, v1), (q2, v2) in zip(points, points[1:]):
        dv = v2 - v1
        if abs(dv) > 1e-10:
            out.append(((v1 + v2) / 2, (q2 - q1) / dv))
    return out


def smooth(points, window):
    if len(points) < window:
        return points
    half, out = window // 2, []
    for i, point in enumerate(points):
        chunk = points[max(0, i - half): min(len(points), i + half + 1)]
        out.append((point[0], sum(p[1] for p in chunk) / len(chunk)))
    return out


def dashed_line(draw, pts, color, width, dash, gap):
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        length = math.hypot(x2 - x1, y2 - y1)
        if length == 0:
            continue
        dx, dy = (x2 - x1) / length, (y2 - y1) / length
        d = 0
        while d < length:
            end = min(d + dash, length)
            draw.line((x1 + dx * d, y1 + dy * d, x1 + dx * end, y1 + dy * end), fill=color, width=width)
            d += dash + gap


def load_font(size):
    for path in ["C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/msyh.ttc"]:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


if __name__ == "__main__":
    App().mainloop()
