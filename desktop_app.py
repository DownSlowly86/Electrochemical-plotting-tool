import csv
import math
import os
import tkinter as tk
from dataclasses import dataclass
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageDraw, ImageFont, ImageTk


CHART_TYPES = [
    "EIS Nyquist",
    "Long Cycling",
    "Voltage-Capacity",
    "dQ/dV",
    "Rate Performance",
    "CV",
    "GITT",
]


COLORS = [
    "#246b5f",
    "#b24b35",
    "#3b6ea8",
    "#9a6b20",
    "#6b5aa6",
    "#2f7f95",
    "#8d4a67",
    "#4f772d",
]


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
        rows = read_csv_rows(self.path)
        if not rows:
            return

        if looks_like_land_format(rows):
            self.kind = "land_like"
            self._parse_land_like(rows)
        else:
            self.kind = "generic"
            self.headers = make_unique_headers(rows[0])
            self.rows = [dict(zip(self.headers, row + [""] * len(self.headers))) for row in rows[1:]]

    def _parse_land_like(self, rows):
        cycle_headers = make_unique_headers(rows[0])
        step_headers = make_unique_headers(rows[1][1:])
        record_headers = make_unique_headers(rows[2][2:])

        current_cycle = None
        current_step = None
        for row in rows[3:]:
            padded = row + [""] * 14
            if padded[0].strip():
                current_cycle = parse_int(padded[0])
                item = row_to_dict(cycle_headers, padded)
                item["循环号"] = current_cycle
                self.cycles.append(item)
            elif padded[1].strip():
                item = row_to_dict(step_headers, padded[1:])
                current_step = parse_int(item.get("工步号"))
                item["循环号"] = current_cycle
                item["工步号"] = current_step
                self.steps.append(item)
            elif padded[2].strip():
                item = row_to_dict(record_headers, padded[2:])
                item["循环号"] = current_cycle
                item["工步号"] = current_step
                item["工步类型"] = find_step_type(self.steps, current_cycle, current_step)
                self.records.append(item)

        self.headers = sorted({key for row in self.cycles + self.steps + self.records for key in row})
        self.rows = self.records

    def summary(self):
        if self.kind == "land_like":
            return f"{self.name}: {len(self.cycles)} cycles, {len(self.steps)} steps, {len(self.records)} data points"
        return f"{self.name}: {len(self.rows)} rows, {len(self.headers)} columns"


class PlotCanvas:
    def __init__(self, width=980, height=640):
        self.width = width
        self.height = height
        self.image = Image.new("RGB", (width, height), "white")
        self.draw = ImageDraw.Draw(self.image)
        self.font = load_font(14)
        self.small_font = load_font(12)
        self.title_font = load_font(20)

    def render(self, title, x_label, y_label, series, y2_series=None, y2_label="", equal_aspect=False):
        y2_series = y2_series or []
        self.image = Image.new("RGB", (self.width, self.height), "white")
        self.draw = ImageDraw.Draw(self.image)

        margin = {"left": 78, "right": 92 if y2_series else 34, "top": 58, "bottom": 78}
        plot = (
            margin["left"],
            margin["top"],
            self.width - margin["right"],
            self.height - margin["bottom"],
        )
        left, top, right, bottom = plot

        points = [point for item in series for point in item.points]
        if not points:
            self._center_text("No valid data for this chart")
            return self.image

        x_domain = pad_domain(extent([point[0] for point in points]))
        y_domain = pad_domain(extent([point[1] for point in points]))
        if equal_aspect:
            x_domain, y_domain = equalize_domains(x_domain, y_domain)

        y2_domain = None
        if y2_series:
            y2_points = [point for item in y2_series for point in item.points]
            y2_domain = pad_domain(extent([point[1] for point in y2_points]))

        sx = lambda value: left + (value - x_domain[0]) / (x_domain[1] - x_domain[0]) * (right - left)
        sy = lambda value: bottom - (value - y_domain[0]) / (y_domain[1] - y_domain[0]) * (bottom - top)
        sy2 = None
        if y2_domain:
            sy2 = lambda value: bottom - (value - y2_domain[0]) / (y2_domain[1] - y2_domain[0]) * (bottom - top)

        self._text_center((self.width // 2, 28), title, self.title_font, "#182331")
        self._draw_axes(plot, x_domain, y_domain, sx, sy, x_label, y_label)
        if y2_domain:
            self._draw_right_axis(plot, y2_domain, sy2, y2_label)

        for item in series:
            self._draw_series(item, sx, sy)
        for item in y2_series:
            self._draw_series(item, sx, sy2)
        self._draw_legend(series + y2_series)
        return self.image

    def _draw_axes(self, plot, x_domain, y_domain, sx, sy, x_label, y_label):
        left, top, right, bottom = plot
        self.draw.line((left, bottom, right, bottom), fill="#7e8b9b", width=1)
        self.draw.line((left, top, left, bottom), fill="#7e8b9b", width=1)

        for tick in make_ticks(x_domain):
            x = sx(tick)
            self.draw.line((x, top, x, bottom), fill="#d8e0ea")
            self._text_center((x, bottom + 22), format_tick(tick), self.small_font, "#5e6b7b")

        for tick in make_ticks(y_domain):
            y = sy(tick)
            self.draw.line((left, y, right, y), fill="#d8e0ea")
            self._text_right((left - 9, y - 7), format_tick(tick), self.small_font, "#5e6b7b")

        self._text_center(((left + right) / 2, bottom + 52), x_label, self.font, "#354253")
        self._rotated_text((22, (top + bottom) / 2), y_label, self.font, "#354253")

    def _draw_right_axis(self, plot, domain, sy, label):
        left, top, right, bottom = plot
        self.draw.line((right, top, right, bottom), fill="#7e8b9b", width=1)
        for tick in make_ticks(domain):
            self.draw.text((right + 9, sy(tick) - 7), format_tick(tick), fill="#5e6b7b", font=self.small_font)
        self._rotated_text((self.width - 24, (top + bottom) / 2), label, self.font, "#354253", clockwise=True)

    def _draw_series(self, series, sx, sy):
        scaled = [(sx(x), sy(y)) for x, y in series.points if is_number(x) and is_number(y)]
        if len(scaled) < 2:
            return
        if series.dashed:
            draw_dashed_line(self.draw, scaled, series.color, width=2)
        else:
            self.draw.line(scaled, fill=series.color, width=2, joint="curve")

        step = max(len(scaled) // 34, 1)
        for index, (x, y) in enumerate(scaled):
            if index % step == 0 or index == len(scaled) - 1:
                self.draw.ellipse((x - 2.4, y - 2.4, x + 2.4, y + 2.4), fill=series.color)

    def _draw_legend(self, series):
        x = self.width - 218
        y = 62
        for index, item in enumerate(series[:9]):
            yy = y + index * 21
            self.draw.line((x, yy, x + 26, yy), fill=item.color, width=3)
            self.draw.text((x + 34, yy - 8), item.name[:22], fill="#354253", font=self.small_font)

    def _center_text(self, text):
        self._text_center((self.width / 2, self.height / 2), text, self.title_font, "#657386")

    def _text_center(self, xy, text, font, fill):
        box = self.draw.textbbox((0, 0), text, font=font)
        self.draw.text((xy[0] - (box[2] - box[0]) / 2, xy[1] - (box[3] - box[1]) / 2), text, fill=fill, font=font)

    def _text_right(self, xy, text, font, fill):
        box = self.draw.textbbox((0, 0), text, font=font)
        self.draw.text((xy[0] - (box[2] - box[0]), xy[1]), text, fill=fill, font=font)

    def _rotated_text(self, xy, text, font, fill, clockwise=False):
        box = self.draw.textbbox((0, 0), text, font=font)
        label = Image.new("RGBA", (box[2] - box[0] + 8, box[3] - box[1] + 8), (255, 255, 255, 0))
        label_draw = ImageDraw.Draw(label)
        label_draw.text((4, 4), text, font=font, fill=fill)
        rotated = label.rotate(-90 if clockwise else 90, expand=True)
        self.image.paste(rotated, (int(xy[0] - rotated.width / 2), int(xy[1] - rotated.height / 2)), rotated)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Electrochemical Plotting Tool")
        self.geometry("1220x760")
        self.minsize(980, 640)

        self.data = None
        self.current_image = None
        self.current_photo = None

        self.chart_type = tk.StringVar(value=CHART_TYPES[1])
        self.output_path = tk.StringVar(value="")
        self.status = tk.StringVar(value="Select a data file to start.")

        self._build_ui()

    def _build_ui(self):
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        side = ttk.Frame(self, padding=16)
        side.grid(row=0, column=0, sticky="ns")
        side.columnconfigure(0, weight=1)

        title = ttk.Label(side, text="Electrochemical Plotting Tool", font=("Segoe UI", 15, "bold"))
        title.grid(row=0, column=0, sticky="w", pady=(0, 4))
        subtitle = ttk.Label(side, text="Local desktop plotting for battery and electrochemical data.", wraplength=300)
        subtitle.grid(row=1, column=0, sticky="w", pady=(0, 14))

        ttk.Button(side, text="Select data file", command=self.select_file).grid(row=2, column=0, sticky="ew", pady=4)
        ttk.Label(side, textvariable=self.status, wraplength=310).grid(row=3, column=0, sticky="w", pady=(4, 14))

        ttk.Label(side, text="Chart type").grid(row=4, column=0, sticky="w")
        chart_box = ttk.Combobox(side, textvariable=self.chart_type, values=CHART_TYPES, state="readonly")
        chart_box.grid(row=5, column=0, sticky="ew", pady=(4, 12))
        chart_box.bind("<<ComboboxSelected>>", lambda _event: self.render())

        ttk.Button(side, text="Render", command=self.render).grid(row=6, column=0, sticky="ew", pady=4)
        ttk.Button(side, text="Choose output location", command=self.choose_output).grid(row=7, column=0, sticky="ew", pady=4)
        ttk.Button(side, text="Export PNG", command=self.export_png).grid(row=8, column=0, sticky="ew", pady=4)

        ttk.Separator(side).grid(row=9, column=0, sticky="ew", pady=16)
        self.info = tk.Text(side, width=38, height=17, wrap="word")
        self.info.grid(row=10, column=0, sticky="nsew")
        self.info.insert("1.0", "Supported charts:\n\n- EIS Nyquist\n- Long Cycling\n- Voltage-Capacity\n- dQ/dV\n- Rate Performance\n- CV\n- GITT\n")
        self.info.configure(state="disabled")

        main = ttk.Frame(self, padding=(0, 16, 16, 16))
        main.grid(row=0, column=1, sticky="nsew")
        main.rowconfigure(0, weight=1)
        main.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(main, bg="#ffffff", highlightthickness=1, highlightbackground="#d7dee8")
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.create_text(490, 310, text="Select a data file", fill="#657386", font=("Segoe UI", 18, "bold"))

    def select_file(self):
        path = filedialog.askopenfilename(
            title="Select electrochemical data",
            filetypes=[
                ("Data files", "*.csv *.txt *.tsv *.dat"),
                ("CSV files", "*.csv"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        try:
            self.data = ElectrochemicalData(path)
        except Exception as exc:
            messagebox.showerror("Import failed", str(exc))
            return
        self.status.set(self.data.summary())
        self._update_info()
        self.render()

    def choose_output(self):
        path = filedialog.asksaveasfilename(
            title="Choose output image",
            defaultextension=".png",
            filetypes=[("PNG image", "*.png")],
            initialfile="electrochemical-plot.png",
        )
        if path:
            self.output_path.set(path)

    def render(self):
        if not self.data:
            return
        width = max(self.canvas.winfo_width(), 900)
        height = max(self.canvas.winfo_height(), 560)
        plotter = PlotCanvas(width=width, height=height)
        title, x_label, y_label, series, y2_series, y2_label, equal_aspect = build_chart(self.data, self.chart_type.get())
        self.current_image = plotter.render(title, x_label, y_label, series, y2_series, y2_label, equal_aspect)
        self.current_photo = ImageTk.PhotoImage(self.current_image)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.current_photo, anchor="nw")

    def export_png(self):
        if not self.current_image:
            self.render()
        if not self.current_image:
            messagebox.showinfo("No chart", "Please select data and render a chart first.")
            return
        path = self.output_path.get()
        if not path:
            self.choose_output()
            path = self.output_path.get()
        if not path:
            return
        self.current_image.save(path)
        messagebox.showinfo("Export complete", f"Saved to:\n{path}")

    def _update_info(self):
        if not self.data:
            return
        lines = [self.data.summary(), ""]
        if self.data.kind == "land_like":
            lines.extend([
                "Detected format: hierarchical battery CSV",
                "",
                "Long Cycling uses cycle summary rows.",
                "Voltage-Capacity, dQ/dV, CV and GITT use point data rows.",
                "Rate Performance uses cycle summary rows unless rate labels are present.",
            ])
        else:
            lines.extend(["Detected format: generic table", "", "Columns:"])
            lines.extend(self.data.headers[:20])
        self.info.configure(state="normal")
        self.info.delete("1.0", "end")
        self.info.insert("1.0", "\n".join(lines))
        self.info.configure(state="disabled")


def build_chart(data, chart_type):
    if chart_type == "Long Cycling":
        return build_long_cycling(data)
    if chart_type == "Voltage-Capacity":
        return build_voltage_capacity(data)
    if chart_type == "dQ/dV":
        return build_dqdv(data)
    if chart_type == "Rate Performance":
        return build_rate(data)
    if chart_type == "CV":
        return build_cv(data)
    if chart_type == "GITT":
        return build_gitt(data)
    return build_eis(data)


def build_long_cycling(data):
    if data.kind == "land_like" and data.cycles:
        charge = []
        discharge = []
        ce = []
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
        return (
            "Long Cycling Performance",
            "Cycle number",
            "Specific capacity (mAh/g)",
            [Series("Charge", charge, COLORS[0]), Series("Discharge", discharge, COLORS[1])],
            [Series("Coulombic efficiency", ce, COLORS[2], dashed=True)] if ce else [],
            "Coulombic efficiency (%)",
            False,
        )
    return build_generic_xy(data, "Long Cycling", ["cycle", "循环"], ["capacity", "容量"])


def build_voltage_capacity(data):
    if data.kind == "land_like":
        groups = group_records_by_cycle(data.records)
        series = []
        for idx, (cycle, records) in enumerate(groups[:8]):
            points = [(to_float(row.get("比容量(mAh/g)")), to_float(row.get("电压(V)"))) for row in records]
            points = valid_points(points)
            if points:
                series.append(Series(f"Cycle {cycle}", points, COLORS[idx % len(COLORS)]))
        return ("Voltage-Capacity", "Specific capacity (mAh/g)", "Voltage (V)", series, [], "", False)
    return build_generic_xy(data, "Voltage-Capacity", ["capacity", "容量"], ["voltage", "电压", "potential"])


def build_dqdv(data):
    title, _x, _y, base_series, _y2, _y2label, _equal = build_voltage_capacity(data)
    series = []
    for idx, item in enumerate(base_series):
        points = derivative_points(item.points)
        if points:
            series.append(Series(item.name, smooth(points, 5), COLORS[idx % len(COLORS)]))
    return ("dQ/dV", "Voltage (V)", "dQ/dV (mAh/g/V)", series, [], "", False)


def build_rate(data):
    title, x_label, y_label, series, y2_series, y2_label, _equal = build_long_cycling(data)
    discharge = [item for item in series if "Discharge" in item.name]
    return ("Rate Performance", x_label, y_label, discharge or series, [], y2_label, False)


def build_cv(data):
    if data.kind == "land_like":
        groups = group_records_by_cycle(data.records)
        series = []
        for idx, (cycle, records) in enumerate(groups[:8]):
            points = [(to_float(row.get("电压(V)")), to_float(row.get("电流(A)"))) for row in records]
            points = valid_points(points)
            if points:
                series.append(Series(f"Cycle {cycle}", points, COLORS[idx % len(COLORS)]))
        return ("Cyclic Voltammetry", "Potential (V)", "Current (A)", series, [], "", False)
    return build_generic_xy(data, "Cyclic Voltammetry", ["potential", "voltage", "电压"], ["current", "电流"])


def build_gitt(data):
    if data.kind == "land_like":
        groups = group_records_by_cycle(data.records)
        series = []
        for idx, (cycle, records) in enumerate(groups[:5]):
            points = [(parse_duration(row.get("总时间")) / 3600, to_float(row.get("电压(V)"))) for row in records]
            points = valid_points(points)
            if points:
                series.append(Series(f"Cycle {cycle}", points, COLORS[idx % len(COLORS)]))
        return ("GITT", "Time (h)", "Voltage (V)", series, [], "", False)
    return build_generic_xy(data, "GITT", ["time", "时间"], ["voltage", "电压", "potential"])


def build_eis(data):
    return build_generic_xy(
        data,
        "EIS Nyquist Plot",
        ["zre", "z'", "real", "z real"],
        ["zim", "z''", "imag", "-zim"],
        y_transform=lambda value: -value if value < 0 else value,
        equal_aspect=True,
        labels=("Z' (ohm)", "-Z'' (ohm)"),
    )


def build_generic_xy(data, title, x_hints, y_hints, y_transform=None, equal_aspect=False, labels=None):
    x_col = find_column(data.headers, x_hints)
    y_col = find_column(data.headers, y_hints)
    points = []
    if x_col and y_col:
        for row in data.rows:
            x = to_float(row.get(x_col))
            y = to_float(row.get(y_col))
            if y_transform and is_number(y):
                y = y_transform(y)
            if is_number(x) and is_number(y):
                points.append((x, y))
    x_label, y_label = labels or (x_col or "X", y_col or "Y")
    return (title, x_label, y_label, [Series("Data", points, COLORS[0])], [], "", equal_aspect)


def read_csv_rows(path):
    encodings = ["utf-8-sig", "gbk", "utf-16"]
    last_error = None
    for encoding in encodings:
        try:
            with open(path, "r", newline="", encoding=encoding) as file:
                sample = file.read(4096)
                file.seek(0)
                delimiter = "\t" if sample.count("\t") > sample.count(",") else ","
                return [row for row in csv.reader(file, delimiter=delimiter) if any(cell.strip() for cell in row)]
        except UnicodeError as exc:
            last_error = exc
    raise last_error or ValueError("Unable to read data file")


def looks_like_land_format(rows):
    if len(rows) < 4:
        return False
    return "循环号" in rows[0][0] and len(rows[1]) > 2 and "工步号" in rows[1][1] and "数据序号" in rows[2][2]


def row_to_dict(headers, values):
    return {header: values[index].strip() if index < len(values) else "" for index, header in enumerate(headers)}


def make_unique_headers(headers):
    result = []
    counts = {}
    for index, header in enumerate(headers):
        base = header.strip() or f"Column {index + 1}"
        counts[base] = counts.get(base, 0) + 1
        result.append(base if counts[base] == 1 else f"{base}_{counts[base]}")
    return result


def find_step_type(steps, cycle, step):
    for item in reversed(steps):
        if item.get("循环号") == cycle and item.get("工步号") == step:
            return item.get("工步类型", "")
    return ""


def group_records_by_cycle(records):
    groups = {}
    for row in records:
        cycle = row.get("循环号")
        groups.setdefault(cycle, []).append(row)
    return [(cycle, rows) for cycle, rows in groups.items()]


def derivative_points(points):
    result = []
    for prev, cur in zip(points, points[1:]):
        q1, v1 = prev
        q2, v2 = cur
        dv = v2 - v1
        dq = q2 - q1
        if abs(dv) > 1e-10:
            result.append(((v1 + v2) / 2, dq / dv))
    return result


def smooth(points, window):
    if len(points) < window:
        return points
    result = []
    half = window // 2
    for index, point in enumerate(points):
        chunk = points[max(0, index - half): min(len(points), index + half + 1)]
        result.append((point[0], sum(item[1] for item in chunk) / len(chunk)))
    return result


def valid_points(points):
    return [(x, y) for x, y in points if is_number(x) and is_number(y)]


def find_column(headers, hints):
    normalized = [(header, normalize(header)) for header in headers]
    for hint in hints:
        key = normalize(hint)
        for header, value in normalized:
            if key in value:
                return header
    return None


def normalize(value):
    return str(value).lower().replace(" ", "").replace("_", "").replace("-", "")


def to_float(value):
    if value is None:
        return math.nan
    text = str(value).strip().replace(",", "")
    if not text:
        return math.nan
    try:
        return float(text)
    except ValueError:
        return math.nan


def parse_int(value):
    number = to_float(value)
    return int(number) if is_number(number) else None


def parse_duration(value):
    if value is None:
        return math.nan
    text = str(value).strip()
    if not text:
        return math.nan
    parts = text.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(text)
    except ValueError:
        return math.nan


def is_number(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def extent(values):
    valid = [value for value in values if is_number(value)]
    if not valid:
        return (0, 1)
    return (min(valid), max(valid))


def pad_domain(domain):
    lo, hi = domain
    if lo == hi:
        return (lo - 1, hi + 1)
    pad = (hi - lo) * 0.06
    return (lo - pad, hi + pad)


def equalize_domains(x_domain, y_domain):
    x_span = x_domain[1] - x_domain[0]
    y_span = y_domain[1] - y_domain[0]
    if x_span > y_span:
        extra = (x_span - y_span) / 2
        return x_domain, (y_domain[0] - extra, y_domain[1] + extra)
    extra = (y_span - x_span) / 2
    return (x_domain[0] - extra, x_domain[1] + extra), y_domain


def make_ticks(domain, count=6):
    lo, hi = domain
    step = (hi - lo) / (count - 1)
    return [lo + step * index for index in range(count)]


def format_tick(value):
    if abs(value) >= 1000 or (abs(value) < 0.01 and value != 0):
        return f"{value:.1e}"
    return f"{value:.3f}".rstrip("0").rstrip(".")


def draw_dashed_line(draw, points, fill, width=2, dash=8, gap=6):
    for start, end in zip(points, points[1:]):
        x1, y1 = start
        x2, y2 = end
        length = math.hypot(x2 - x1, y2 - y1)
        if length == 0:
            continue
        dx = (x2 - x1) / length
        dy = (y2 - y1) / length
        distance = 0
        while distance < length:
            dash_end = min(distance + dash, length)
            draw.line(
                (
                    x1 + dx * distance,
                    y1 + dy * distance,
                    x1 + dx * dash_end,
                    y1 + dy * dash_end,
                ),
                fill=fill,
                width=width,
            )
            distance += dash + gap


def load_font(size):
    candidates = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
