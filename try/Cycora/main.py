import calendar as calendar_module
import csv
import json
import shutil
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import date, datetime
from pathlib import Path
import webbrowser

import database as db
from cycle_engine import cycle_summary, parse_date, fmt_day
from health_library import ARTICLES

ROOT_DIR = Path(__file__).resolve().parent
ASSET_DIR = ROOT_DIR / "assets"
BURGUNDY = "#8E1733"
BURGUNDY_DARK = "#6F1027"
CRIMSON = "#B91E43"
PINK = "#F8E9ED"
BG = "#FBF8F8"
CARD = "#FFFFFF"
TEXT = "#281D21"
MUTED = "#786A6F"
BORDER = "#EADDE1"


def valid_iso_date(value, field_name):
    try:
        parsed = parse_date(value)
    except ValueError:
        raise ValueError(f"{field_name} must use YYYY-MM-DD (example: 2026-10-18).")
    if parsed > date.today():
        raise ValueError(f"{field_name} cannot be in the future.")
    if parsed.year < 1900:
        raise ValueError(f"{field_name} must be 1900 or later.")
    return parsed


class WheelColumn(tk.Frame):
    """A small mouse-wheel date column with a highlighted center value."""
    def __init__(self, parent, values, selected, width=110, on_change=None):
        super().__init__(parent, bg=CARD)
        self.values = list(values)
        self.index = self.values.index(selected) if selected in self.values else 0
        self.width = width
        self.on_change = on_change
        self.canvas = tk.Canvas(self, width=width, height=154, bg=CARD, highlightthickness=0)
        self.canvas.pack()
        self.canvas.bind('<MouseWheel>', self._mousewheel)
        self.canvas.bind('<Button-4>', lambda _e: self.move(-1))
        self.canvas.bind('<Button-5>', lambda _e: self.move(1))
        self.canvas.bind('<Button-1>', self._click_row)
        self.draw()

    def _mousewheel(self, event):
        self.move(-1 if event.delta > 0 else 1)

    def _click_row(self, event):
        offset = round((event.y - 77) / 28)
        if -2 <= offset <= 2:
            self.move(offset)

    def set_values(self, values, selected=None):
        self.values = list(values)
        if not self.values:
            self.index = 0
        elif selected in self.values:
            self.index = self.values.index(selected)
        else:
            self.index = min(self.index, len(self.values) - 1)
        self.draw()

    def move(self, amount):
        if not self.values:
            return
        self.index = max(0, min(len(self.values) - 1, self.index + amount))
        self.draw()
        if self.on_change:
            self.on_change()

    def get_value(self):
        return self.values[self.index] if self.values else None

    def draw(self):
        self.canvas.delete('all')
        if not self.values:
            return
        center = 77
        self.canvas.create_rectangle(5, center - 17, self.width - 5, center + 17,
                                     fill=PINK, outline=PINK)
        for offset in range(-2, 3):
            idx = self.index + offset
            if 0 <= idx < len(self.values):
                value = self.values[idx]
                color = BURGUNDY if offset == 0 else (MUTED if abs(offset) == 1 else '#B9AEB2')
                font = ('Segoe UI', 14, 'bold') if offset == 0 else ('Segoe UI', 11)
                self.canvas.create_text(self.width // 2, center + offset * 28,
                                        text=str(value), fill=color, font=font)
        self.canvas.configure(cursor='hand2')


class DateWheelPicker(tk.Frame):
    """Reusable wheel-style date picker with direct year selection."""
    MONTHS = ['January', 'February', 'March', 'April', 'May', 'June',
              'July', 'August', 'September', 'October', 'November', 'December']

    def __init__(self, parent, initial_date, on_select, allow_future=False,
                 title='Choose a date', subtitle='Scroll the wheels or select a year directly.'):
        super().__init__(parent, bg=BG)
        self.on_select = on_select
        self.allow_future = allow_future
        self.selected = initial_date
        self.max_year = date.today().year + (20 if allow_future else 0)
        self.min_year = 1900

        tk.Label(self, text=title, font=('Segoe UI', 17, 'bold'), fg=BURGUNDY, bg=BG).pack(anchor='w', padx=20, pady=(18, 4))
        tk.Label(self, text=subtitle, font=('Segoe UI', 9), fg=MUTED, bg=BG).pack(anchor='w', padx=20, pady=(0, 12))

        wheels = tk.Frame(self, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        wheels.pack(fill='x', padx=18, pady=4)
        for i, name in enumerate(('MONTH', 'DAY', 'YEAR')):
            tk.Label(wheels, text=name, font=('Segoe UI', 8, 'bold'), fg=MUTED, bg=CARD).grid(row=0, column=i, pady=(12, 0))
        self.month_wheel = WheelColumn(wheels, self.MONTHS, self.MONTHS[initial_date.month - 1], on_change=self._month_changed)
        self.month_wheel.grid(row=1, column=0, padx=4, pady=(0, 8))
        self.day_wheel = WheelColumn(wheels, list(range(1, calendar_module.monthrange(initial_date.year, initial_date.month)[1] + 1)), initial_date.day, width=78, on_change=self._day_changed)
        self.day_wheel.grid(row=1, column=1, padx=4, pady=(0, 8))
        self.year_wheel = WheelColumn(wheels, list(range(self.min_year, self.max_year + 1)), initial_date.year, on_change=self._year_changed)
        self.year_wheel.grid(row=1, column=2, padx=4, pady=(0, 8))

        quick = tk.Frame(self, bg=BG)
        quick.pack(fill='x', padx=20, pady=(8, 0))
        tk.Label(quick, text='Jump to year:', font=('Segoe UI', 9, 'bold'), fg=TEXT, bg=BG).pack(side='left')
        self.year_var = tk.StringVar(value=str(initial_date.year))
        self.year_combo = ttk.Combobox(quick, textvariable=self.year_var, state='normal', width=10,
                                       values=[str(y) for y in range(self.max_year, self.min_year - 1, -1)])
        self.year_combo.pack(side='left', padx=8)
        self.year_combo.bind('<<ComboboxSelected>>', self._quick_year)
        self.year_combo.bind('<Return>', self._quick_year)
        tk.Label(quick, text='Type a year or choose from the list.', font=('Segoe UI', 8), fg=MUTED, bg=BG).pack(side='left')

        buttons = tk.Frame(self, bg=BG)
        buttons.pack(fill='x', padx=20, pady=(14, 18))
        tk.Button(buttons, text='Cancel', command=self.winfo_toplevel().destroy,
                  relief='flat', bg='#F1EAEC', fg=TEXT, padx=16, pady=8).pack(side='right', padx=(8, 0))
        tk.Button(buttons, text='Use this date', command=self.confirm_date,
                  relief='flat', bg=BURGUNDY, fg='white', activebackground=BURGUNDY_DARK,
                  activeforeground='white', padx=16, pady=8).pack(side='right')

    def _date_parts(self):
        return self.year_wheel.get_value(), self.MONTHS.index(self.month_wheel.get_value()) + 1

    def _refresh_days(self):
        year, month = self._date_parts()
        max_day = calendar_module.monthrange(year, month)[1]
        current = min(self.day_wheel.get_value() or 1, max_day)
        self.day_wheel.set_values(list(range(1, max_day + 1)), current)
        self.year_var.set(str(year))

    def _month_changed(self): self._refresh_days()
    def _year_changed(self): self._refresh_days()
    def _day_changed(self): pass

    def _quick_year(self, _event=None):
        try:
            year = int(self.year_var.get().strip())
        except ValueError:
            self.year_var.set(str(self.year_wheel.get_value()))
            return
        if not self.min_year <= year <= self.max_year:
            messagebox.showwarning('Invalid year', f'Choose a year from {self.min_year} to {self.max_year}.', parent=self)
            self.year_var.set(str(self.year_wheel.get_value()))
            return
        self.year_wheel.set_values(list(range(self.min_year, self.max_year + 1)), year)
        self._refresh_days()

    def confirm_date(self):
        year, month = self._date_parts()
        day = self.day_wheel.get_value()
        try:
            chosen = date(year, month, day)
        except (ValueError, TypeError):
            messagebox.showerror('Invalid date', 'Please select a valid date.', parent=self)
            return
        if not self.allow_future and chosen > date.today():
            messagebox.showwarning('Future date', 'Choose today or an earlier date.', parent=self)
            return
        self.on_select(chosen)


class CycoraApp(tk.Tk):
    def __init__(self):
        super().__init__()
        db.init_db()
        self.title("Cycora — Your Cycle. Your Health. Your Space.")
        self.geometry("1240x820")
        self.minsize(1020, 700)
        self.configure(bg=BG)
        self.profile_id = None
        self.active_page = "Home"
        self.onboarding_answers = {}
        self.onboarding_steps = []
        self.onboarding_index = 0
        self._images = {}
        self._setup_style()
        self._load_logo()
        self._build_shell()
        profiles = db.list_profiles()
        if profiles:
            self.profile_id = profiles[0]["id"]
            self.show_page("Home")
        else:
            self.start_onboarding()

    def _setup_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TCombobox", padding=7, fieldbackground="white", background="white")
        style.configure("Treeview", rowheight=32, font=("Segoe UI", 10), background="white", fieldbackground="white")
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"), background="#F5E9EC", foreground=TEXT)
        style.map("Treeview", background=[("selected", "#F4DDE4")], foreground=[("selected", TEXT)])

    def _load_logo(self):
        for key, filename in [("wordmark", "cycora_wordmark_small.png"), ("square", "cycora_square_small.png")]:
            path = ASSET_DIR / filename
            if path.exists():
                try:
                    self._images[key] = tk.PhotoImage(file=str(path))
                except tk.TclError:
                    pass

    def _build_shell(self):
        self.shell = tk.Frame(self, bg=BG)
        self.shell.pack(fill="both", expand=True)
        self.sidebar = tk.Frame(self.shell, bg=CARD, width=220, highlightbackground=BORDER, highlightthickness=1)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        logo_wrap = tk.Frame(self.sidebar, bg=CARD, height=118)
        logo_wrap.pack(fill="x", padx=14, pady=(16, 8))
        if "wordmark" in self._images:
            tk.Label(logo_wrap, image=self._images["wordmark"], bg=CARD).pack(anchor="center", pady=8)
        else:
            tk.Label(logo_wrap, text="CYCORA", font=("Segoe UI", 23, "bold"), fg=BURGUNDY, bg=CARD).pack(anchor="w", pady=18)
        tk.Label(self.sidebar, text="YOUR CYCLE. YOUR SPACE.", font=("Segoe UI", 8, "bold"), fg=MUTED, bg=CARD).pack(anchor="w", padx=20, pady=(0, 18))
        self.nav_buttons = {}
        nav_items = [("Home", "⌂"), ("Calendar", "▦"), ("Period Tracker", "◷"), ("Symptoms", "♡"), ("Cycle Insights", "⌁"), ("Sex Tracker", "＋"), ("Pregnancy Tracker", "✧"), ("Learn & Explore", "◇"), ("Journal", "▤"), ("Profile & Settings", "○")]
        for label, symbol in nav_items:
            btn = tk.Button(self.sidebar, text=f"  {symbol}  {label}", anchor="w", relief="flat", bd=0,
                            font=("Segoe UI", 9), padx=10, pady=8, bg=CARD, fg=TEXT,
                            activebackground=PINK, activeforeground=BURGUNDY,
                            command=lambda page=label: self.show_page(page))
            btn.pack(fill="x", padx=7, pady=1)
            self.nav_buttons[label] = btn
        tk.Frame(self.sidebar, bg=BORDER, height=1).pack(fill="x", padx=16, pady=16)
        self.profile_button = tk.Button(self.sidebar, text="Switch account  ↔", relief="flat", bd=0,
                                        font=("Segoe UI", 9, "bold"), bg=PINK, fg=BURGUNDY,
                                        activebackground="#F0D3DC", command=self.switch_profile_dialog)
        self.profile_button.pack(fill="x", padx=14, pady=(0, 8))
        tk.Label(self.sidebar, text="LOCAL-FIRST • PRIVATE BY DESIGN", font=("Segoe UI", 7), fg=MUTED, bg=CARD).pack(side="bottom", pady=14)
        self.main_area = tk.Frame(self.shell, bg=BG)
        self.main_area.pack(side="left", fill="both", expand=True)
        self.topbar = tk.Frame(self.main_area, bg=BG)
        self.topbar.pack(fill="x", padx=28, pady=(20, 8))
        self.page_title = tk.Label(self.topbar, text="Welcome to Cycora", font=("Segoe UI", 22, "bold"), fg=TEXT, bg=BG)
        self.page_title.pack(side="left")
        self.top_profile = tk.Label(self.topbar, text="", font=("Segoe UI", 10, "bold"), fg=BURGUNDY, bg=PINK, padx=12, pady=8)
        self.top_profile.pack(side="right")
        self.content = tk.Frame(self.main_area, bg=BG)
        self.content.pack(fill="both", expand=True, padx=28, pady=(4, 24))

    def _clear_content(self):
        for child in self.content.winfo_children():
            child.destroy()

    def _header(self, title, subtitle=""):
        self.page_title.config(text=title)
        p = db.get_profile(self.profile_id) if self.profile_id else None
        self.top_profile.config(text=f"◉  {p['name']}" if p else "No profile selected")
        for name, btn in self.nav_buttons.items():
            btn.configure(bg=PINK if name == self.active_page else CARD, fg=BURGUNDY if name == self.active_page else TEXT)
        if subtitle:
            tk.Label(self.content, text=subtitle, font=("Segoe UI", 10), fg=MUTED, bg=BG, wraplength=850, justify="left").pack(anchor="w", pady=(0, 16))

    def _card(self, parent, title=None, padding=18):
        frame = tk.Frame(parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        frame.pack_propagate(True)
        if title:
            tk.Label(frame, text=title, font=("Segoe UI", 12, "bold"), fg=TEXT, bg=CARD).pack(anchor="w", padx=padding, pady=(padding, 8))
        return frame

    def _button(self, parent, text, command, primary=True):
        return tk.Button(parent, text=text, command=command, relief="flat", bd=0,
                         font=("Segoe UI", 10, "bold"), padx=16, pady=10,
                         bg=BURGUNDY if primary else PINK, fg="white" if primary else BURGUNDY,
                         activebackground=BURGUNDY_DARK if primary else "#F0D3DC",
                         activeforeground="white" if primary else BURGUNDY, cursor="hand2")

    def show_welcome(self):
        self.start_onboarding()

    def _show_onboarding_shell(self, visible):
        if visible:
            self.sidebar.pack_forget()
            self.topbar.pack_forget()
        else:
            if not self.sidebar.winfo_manager():
                self.sidebar.pack(side="left", fill="y", before=self.main_area)
            if not self.topbar.winfo_manager():
                self.topbar.pack(fill="x", padx=28, pady=(20, 8), before=self.content)

    def start_onboarding(self):
        self.onboarding_answers = {"privacy_policy": False, "health_data_consent": False, "goals": []}
        self.onboarding_steps = [
            {"key":"welcome", "title":"Welcome to Cycora", "desc":"Your cycle. Your health. Your space.", "kind":"welcome"},
            {"key":"privacy", "title":"Privacy first", "desc":"Your information is stored locally on this computer. Review the choices below.", "kind":"privacy"},
            {"key":"name", "title":"What should we call you?", "desc":"Use a name you are comfortable seeing on your dashboard.", "kind":"entry", "required":True, "placeholder":"Enter your name"},
            {"key":"birth_date", "title":"What's your birth date?", "desc":"Choose your month, day, and year. Cycora uses this to personalize age-related guidance.", "kind":"birthday", "required":True},
            {"key":"purpose", "title":"Who is this profile for?", "desc":"Each profile has its own separate records.", "kind":"choice", "options":["Myself","Partner","Mom","Sister","Daughter","Friend","Other"]},
            {"key":"purpose_custom", "title":"Name this profile purpose", "desc":"Give this profile purpose a short label.", "kind":"entry", "placeholder":"e.g. Family member"},
            {"key":"goals", "title":"What are your goals?", "desc":"Choose as many as you’d like. Your choices help personalize your Cycora space.", "kind":"multi", "options":["Get pregnant","Track my pregnancy","Track my period","Take charge of my well-being","Enhance my sex life","Manage my weight","Decode my discharge","Explore contraception"]},
            {"key":"feeling", "title":"How are you feeling?", "desc":"Choose the closest answer. Your selection will show a supportive note; there is no wrong answer.", "kind":"choice", "options":["Excited and ready to learn","A bit unsure or unprepared","Worried or stressed","Happy, nervous, and excited","Just exploring"]},
            {"key":"pregnancy_timing", "title":"How soon do you want to get pregnant?", "desc":"Only shown when you select Get pregnant. This helps personalize educational content, not predict fertility.", "kind":"choice", "options":["As soon as possible","No rush — I want to learn first","I'm supporting my partner or someone I care about","Prefer not to say"]},
            {"key":"trying_duration", "title":"How long have you been trying to get pregnant?", "desc":"Optional context. This answer cannot determine fertility or diagnose a problem.", "kind":"choice", "options":["Not trying yet","Less than 3 months","3–6 months","6–12 months","More than 12 months","Prefer not to say"]},
            {"key":"fertile_days", "title":"Do you try to conceive on your most fertile days?", "desc":"Calendar estimates cannot confirm ovulation and must not be used as contraception.", "kind":"choice", "options":["Yes, I track them","Sometimes","Not yet","I'm not sure"]},
            {"key":"period_regular", "title":"Are your periods regular?", "desc":"Choose what best describes your usual pattern. A change in your pattern can be worth discussing with a clinician.", "kind":"choice", "options":["Usually regular","Sometimes irregular","Often irregular","I don't know yet","My periods have not started","I do not get periods"]},
            {"key":"content_warning", "title":"A gentle content warning", "desc":"The next question is about trying to conceive and may feel personal. You can skip it. You are in control of what you share.", "kind":"warning"},
            {"key":"first_time_trying", "title":"Is this your first time trying to conceive?", "desc":"Optional context for people who selected Get pregnant.", "kind":"choice", "options":["Yes","No","Prefer not to say","Not applicable"]},
            {"key":"last_period", "title":"When was the first day of your last period?", "desc":"Pick the actual date from the calendar. If you do not know, you can skip it.", "kind":"date"},
            {"key":"contraception", "title":"Have you used birth control in the last 6 months?", "desc":"Some contraceptives can affect bleeding patterns. This question is optional.", "kind":"choice", "options":["Yes","No","Not sure","Prefer not to say"]},
            {"key":"conditions", "title":"Do you have any reproductive health conditions?", "desc":"Choose only what you are comfortable recording. This does not diagnose a condition.", "kind":"multi", "options":["PCOS","Endometriosis","Fibroids","Thyroid condition","Other condition","None known","Prefer not to say"]},
            {"key":"fertility_results", "title":"Your estimated fertile window", "desc":"A calendar estimate only—not a guarantee of pregnancy or ovulation.", "kind":"fertility_results"},
            {"key":"period_status", "title":"Your cycle status", "desc":"A rough estimate based on the last period date you entered.", "kind":"period_status"},
            {"key":"discharge", "title":"Did you know discharge can change through your cycle?", "desc":"Observations may help you learn your own pattern, but discharge alone cannot prove ovulation or pregnancy.", "kind":"choice", "options":["Yes, I want to learn about it","I sometimes notice changes","I have questions or concerns","Skip this topic"]},
            {"key":"height", "title":"How tall are you?", "desc":"Use the scroll controls to choose a measurement. This is optional and is not used to judge your health.", "kind":"height"},
            {"key":"weight", "title":"How much do you weigh?", "desc":"Use the scroll controls to choose a measurement. You can skip this if you do not want to record it.", "kind":"weight"},
            {"key":"cycle_experiences", "title":"Regarding your cycle, have you experienced any of these?", "desc":"Select any experiences you want to track. Persistent or concerning symptoms deserve individual medical advice.", "kind":"multi", "options":["Periods that are often late or missed","Bleeding between periods","Very heavy bleeding","Periods lasting longer than usual","Severe cramps","Symptoms that disrupt daily activities","None of these","Prefer not to say"]},
            {"key":"pain_types", "title":"Have you felt any of these types of pain?", "desc":"Select anything you have experienced. Severe or sudden pain may need urgent medical assessment.", "kind":"multi", "options":["Lower abdominal cramps","Pelvic pain","Lower back pain","Pain during sex","Pain when urinating or having a bowel movement","Headache or migraine","None of these","Prefer not to say"]},
            {"key":"hormone_signs", "title":"Have you noticed signs that may be worth discussing with a clinician?", "desc":"These signs can have many causes and do not prove a hormone problem.", "kind":"multi", "options":["New or persistent acne","New facial/body hair growth","Hair thinning","Unusual fatigue","Unexpected weight changes","Irregular or absent periods","None of these","Prefer not to say"]},
            {"key":"supplements", "title":"Do you take prenatal vitamins or supplements?", "desc":"Only shown for conception-related goals. Ask a qualified clinician or pharmacist what is suitable for you.", "kind":"choice", "options":["Prenatal vitamin","Other supplement","No","Not sure","Prefer not to say"]},
            {"key":"precheckup", "title":"Have you had a pre-pregnancy check-up?", "desc":"A healthcare professional can discuss medications, health history, and questions before pregnancy.", "kind":"choice", "options":["Yes","Not yet","I have an appointment planned","Not applicable","Prefer not to say"]},
            {"key":"partner_changes", "title":"Has your partner made changes to prepare for conception?", "desc":"Preparation can include reviewing health, medicines, habits, and questions with a healthcare professional. No pressure to answer.", "kind":"choice", "options":["Yes","Some changes","Not yet","I'm not tracking with a partner","Prefer not to say"]},
            {"key":"healthy_diet", "title":"Do you feel you have a varied, nourishing diet?", "desc":"This is not a test. Small, realistic habits matter more than perfection; ask a professional for personal nutrition advice.", "kind":"choice", "options":["Most days, yes","Sometimes","I'd like support with this","Not sure","Prefer not to say"]},
            {"key":"feeling_health", "title":"What else would you like to track?", "desc":"Choose optional topics to make your dashboard more useful.", "kind":"multi", "options":["Mood and energy","Sleep","Discharge observations","Medication or supplement notes","Hydration and meals","Questions for a clinician","None for now"]},
            {"key":"results", "title":"Your starting overview", "desc":"Your overview is based on what you chose to share. Dates are estimates, not guarantees.", "kind":"results"},
            {"key":"complete", "title":"Your Cycora space is ready", "desc":"Your profile and chosen goals will be saved locally on this computer.", "kind":"complete"},
        ]
        self.onboarding_index = 0
        self._show_onboarding_shell(True)
        self.render_onboarding_step()

    def render_onboarding_step(self):
        self._clear_content()
        step = self.onboarding_steps[self.onboarding_index]
        outer = tk.Frame(self.content, bg=BG)
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        onboard_scroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        center = tk.Frame(canvas, bg=BG)

        window_id = canvas.create_window(
            (0, 0),
            window=center,
            anchor="nw"
        )

        def update_canvas_width(event):
            canvas.itemconfigure(window_id, width=event.width)

        canvas.bind("<Configure>", update_canvas_width)

        center.bind(
            "<Configure>",
            lambda _e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )
        canvas.configure(yscrollcommand=onboard_scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        onboard_scroll.pack(side="right", fill="y")
        canvas.bind("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))
        # Each screen contains a batch of questions. Conditional questions remain in place
        # and are filtered according to the goals selected by the user.
        batch_groups = [
            ["welcome"], ["privacy"], ["name", "birth_date"], ["goals"],
            ["purpose", "purpose_custom", "feeling", "pregnancy_timing", "trying_duration", "fertile_days", "period_regular"],
            ["content_warning"],
            ["first_time_trying", "last_period", "contraception", "conditions", "fertility_results", "period_status", "discharge"],
            ["height", "weight"],
            ["cycle_experiences", "pain_types", "hormone_signs", "supplements", "precheckup", "partner_changes", "healthy_diet", "feeling_health"],
            ["results"], ["complete"]
        ]
        by_key = {item["key"]: item for item in self.onboarding_steps}
        self.onboarding_batches = []
        for group in batch_groups:
            items = [by_key[k] for k in group if k in by_key and (k == "purpose_custom" or not self._skip_this_onboarding_step(by_key[k]))]
            if items:
                self.onboarding_batches.append(items)
        batch_index = min(self.onboarding_index, len(self.onboarding_batches) - 1)
        batch = self.onboarding_batches[batch_index]
        first = batch[0]
        if first["key"] == "welcome":
            # The welcome screen uses the square logo only; the small wordmark is intentionally omitted.
            pass
        else:
            if "wordmark" in self._images:
                tk.Label(center, image=self._images["wordmark"], bg=BG).pack(pady=(2, 14))
            else:
                tk.Label(center, text="CYCORA", font=("Segoe UI", 26, "bold"), fg=BURGUNDY, bg=BG).pack(pady=(2, 14))
        progress = f"STEP {batch_index + 1} OF {len(self.onboarding_batches)}"
        tk.Label(center, text=progress, font=("Segoe UI", 10, "bold"), fg=CRIMSON, bg=BG).pack(pady=(0, 8))
        # Each batch has a single heading when it contains one question; otherwise each
        # question keeps its own title and description within a scrollable card.
        if len(batch) == 1:
            tk.Label(center, text=first["title"], font=("Segoe UI", 23 if first["key"] in ("welcome", "complete") else 20, "bold"), fg=TEXT, bg=BG, wraplength=720, justify="center").pack(pady=(0, 8))
            tk.Label(center, text=first["desc"], font=("Segoe UI", 12), fg=MUTED, bg=BG, wraplength=680, justify="center").pack(pady=(0, 18))
        self._onboard_fields = {}
        for field_step in batch:
            key, kind = field_step["key"], field_step["kind"]
            if len(batch) > 1:
                tk.Label(center, text=field_step["title"], font=("Segoe UI", 16, "bold"), fg=TEXT, bg=BG, wraplength=720, justify="center").pack(pady=(16, 5))
                tk.Label(center, text=field_step["desc"], font=("Segoe UI", 12), fg=MUTED, bg=BG, wraplength=680, justify="center").pack(pady=(0, 10))
            card = tk.Frame(center, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
            card.pack(fill="x", padx=26, pady=5)
            field_vars = self._render_onboarding_field(card, field_step)
            self._onboard_fields[key] = {"step": field_step, "vars": field_vars}
        # Keep legacy references for methods elsewhere that expect this attribute.
        self._onboard_vars = self._onboard_fields[first["key"]]["vars"]
        nav = tk.Frame(center, bg=BG)
        nav.pack(fill="x", padx=26, pady=18)
        if self.onboarding_index > 0:
            self._button(nav, "← Back", self.onboarding_back, False).pack(side="left")
        if all(item["kind"] not in ("welcome", "complete", "results", "fertility_results", "period_status", "warning") for item in batch) and not any(item["key"] in ("privacy", "name", "birth_date", "goals") for item in batch):
            self._button(nav, "Skip optional questions", self.onboarding_skip, False).pack(side="left", padx=8)
        button_text = "TRACK NOW!" if first["key"] == "welcome" else ("Create my profile" if first["key"] == "complete" else "Continue →")
        self._button(nav, button_text, self.onboarding_next).pack(side="right" if first["key"] != "welcome" else "top", anchor="center")

    def _render_onboarding_field(self, card, step):
        key, kind = step["key"], step["kind"]
        field_vars = {}
        if kind == "welcome":
            if "square" in self._images:
                tk.Label(card, image=self._images["square"], bg=CARD).pack(pady=(18, 4))
            tk.Label(card, text="A little more in tune with yourself.", font=("Segoe UI", 16, "bold"), fg=BURGUNDY, bg=CARD).pack(pady=(6, 4))
            tk.Label(card, text="Track periods, notice patterns, and explore clear reproductive health information—all in one calm, private space.", font=("Segoe UI", 10), fg=MUTED, bg=CARD, wraplength=560, justify="center").pack(padx=28, pady=(0, 18))
        elif kind == "privacy":
            field_vars.clear()
            for k, label in [("privacy_policy", "I agree to the Privacy Policy and Terms of Use."), ("health_data_consent", "I agree to Cycora processing the health information I choose to enter to provide tracking features.")]:
                var = tk.BooleanVar(value=bool(self.onboarding_answers.get(k)))
                field_vars[k] = var
                tk.Checkbutton(card, text=label, variable=var, bg=CARD, fg=TEXT, activebackground=CARD, wraplength=570, justify="left", font=("Segoe UI", 10), selectcolor=PINK).pack(anchor="w", padx=22, pady=12)
            self._button(card, "Read privacy summary & terms", self.show_privacy_details, False).pack(anchor="w", padx=22, pady=(0, 10))
            tk.Label(card, text="Local storage is not encryption. Anyone with access to your Windows account and app files may be able to view this data.", font=("Segoe UI", 9), fg=MUTED, bg=CARD, wraplength=570, justify="left").pack(anchor="w", padx=22, pady=(2, 16))
        elif kind in ("entry", "date", "birthday"):
            initial = str(self.onboarding_answers.get(key, ""))
            if kind == "birthday" and not initial:
                initial = date(date.today().year - 18, 1, 1).isoformat()
            var = tk.StringVar(value=initial)
            field_vars[key] = var
            fieldrow = tk.Frame(card, bg=CARD); fieldrow.pack(fill="x", padx=24, pady=24)
            entry = tk.Entry(fieldrow, textvariable=var, font=("Segoe UI", 12), relief="solid", bd=1, highlightthickness=1, highlightbackground=BORDER)
            entry.pack(side="left", fill="x", expand=True, ipady=9)
            if kind in ("date", "birthday"):
                self._button(fieldrow, "Choose date  ▦", lambda v=var: self.open_date_picker(v, allow_future=False, parent=self), False).pack(side="left", padx=(8,0))
                tk.Label(card, text="Use YYYY-MM-DD or choose a date from the calendar.", font=("Segoe UI", 9), fg=MUTED, bg=CARD).pack(anchor="w", padx=24, pady=(0,14))
            entry.focus_set()
        elif kind in ("height", "weight"):
            field_vars.clear()
            unit = tk.StringVar(value="cm" if kind == "height" else "kg")
            value = tk.DoubleVar(value=165 if kind == "height" else 60)
            field_vars.update({"unit":unit,"value":value})
            units = ["cm", "in"] if kind == "height" else ["kg", "lb"]
            combo = ttk.Combobox(card, textvariable=unit, values=units, state="readonly", width=8)
            combo.pack(pady=(18,6))
            def unit_changed(_event=None):
                old=unit.get()
                if kind == "height":
                    if old == "in": value.set(round(float(value.get())/2.54,1)); spin.configure(from_=35,to=87,increment=0.5)
                    else: value.set(round(float(value.get())*2.54)); spin.configure(from_=90,to=220,increment=1)
                else:
                    if old == "lb": value.set(round(float(value.get())*2.20462,1)); spin.configure(from_=44,to=350,increment=1)
                    else: value.set(round(float(value.get())/2.20462,1)); spin.configure(from_=20,to=160,increment=0.5)
            low, high, inc = (90,220,1) if kind == "height" else (20,160,0.5)
            spin = tk.Spinbox(card, from_=low, to=high, increment=inc, textvariable=value, font=("Segoe UI", 16), width=10, justify="center", wrap=True)
            spin.pack(pady=10, ipady=7)
            combo.bind("<<ComboboxSelected>>", unit_changed)
            tk.Label(card, text="Scroll or use the arrows to adjust. Choose Skip if you prefer not to answer.", font=("Segoe UI", 9), fg=MUTED, bg=CARD, wraplength=560).pack(padx=20,pady=(0,18))
        elif kind == "choice":
            var = tk.StringVar(value=str(self.onboarding_answers.get(key, "")))
            field_vars[key] = var
            for option in step["options"]:
                tk.Radiobutton(card, text=option, variable=var, value=option, bg=CARD, fg=TEXT, activebackground=CARD, selectcolor=PINK, font=("Segoe UI", 10), anchor="w", command=lambda k=key,v=var: self._show_choice_note(k,v.get(),note_label)).pack(fill="x", padx=20, pady=5)
            note_label = tk.Label(card, text="Choose an answer to see a helpful note.", font=("Segoe UI", 9), fg=BURGUNDY, bg=PINK, wraplength=560, justify="left", padx=12, pady=10)
            note_label.pack(fill="x", padx=18, pady=(10,16))
            if var.get(): self._show_choice_note(key,var.get(),note_label)
        elif kind == "multi":
            current = self.onboarding_answers.get(key, [])
            if not isinstance(current, list): current = []
            field_vars.clear()
            if key == "goals":
                # Keep references alive so Tkinter does not discard the original burgundy illustrations.
                self._goal_images = []
                goal_assets = {
                    "Get pregnant": "test.png",
                    "Track my pregnancy": "pregnancy.png",
                    "Track my period": "period.png",
                    "Take charge of my well-being": "charge.png",
                    "Enhance my sex life": "sex.png",
                    "Manage my weight": "weight.png",
                    "Decode my discharge": "discharge.png",
                    "Explore contraception": "contraception.png",
                }
                goal_grid = tk.Frame(card, bg=CARD)
                goal_grid.pack(fill="both", expand=True, padx=14, pady=(8, 16))
                for index, option in enumerate(step["options"]):
                    var = tk.BooleanVar(value=option in current)
                    field_vars[option] = var
                    tile = tk.Frame(goal_grid, bg="#FFF9FA", highlightbackground=BORDER, highlightthickness=1, padx=8, pady=7)
                    tile.grid(row=index // 2, column=index % 2, sticky="nsew", padx=5, pady=5)
                    asset_path = ASSET_DIR / "goals" / goal_assets[option]
                    try:
                        img = tk.PhotoImage(file=str(asset_path))
                        factor = max(1, (max(img.width(), img.height()) + 1) // 84)
                        if factor > 1: img = img.subsample(factor, factor)
                        self._goal_images.append(img)
                        tk.Label(tile, image=img, bg="#FFF9FA").pack(pady=(0, 3))
                    except (tk.TclError, OSError):
                        tk.Label(tile, text="◉", font=("Segoe UI", 22, "bold"), fg=BURGUNDY, bg="#FFF9FA").pack(pady=(0, 3))
                    tk.Checkbutton(tile, text=option, variable=var, bg="#FFF9FA", fg=TEXT,
                                   activebackground="#FFF9FA", selectcolor=PINK, font=("Segoe UI", 9, "bold"),
                                   wraplength=210, justify="center", anchor="center" ).pack(fill="x")
                for col in range(2): goal_grid.grid_columnconfigure(col, weight=1, uniform="goal")
            else:
                for option in step["options"]:
                    var = tk.BooleanVar(value=option in current)
                    field_vars[option] = var
                    tk.Checkbutton(card, text=option, variable=var, bg=CARD, fg=TEXT, activebackground=CARD, selectcolor=PINK, font=("Segoe UI", 12), anchor="w").pack(fill="x", padx=20, pady=4)
        elif kind == "warning":

            # Try loading the exclamation logo
            try:
                warning_logo = tk.PhotoImage(
                    file=str(ASSET_DIR / "goals" / "exclamation.png"))
                warning_logo = warning_logo.subsample(5, 5)
                

                warning_logo_label = tk.Label(
                    card,
                    image=warning_logo,
                    bg=CARD
                )
                warning_logo_label.image = warning_logo
                warning_logo_label.pack(pady=(8, 12))

            except (tk.TclError, FileNotFoundError) as e:
                print("Warning logo failed to load:", e)

            tk.Label(
                card,
                text="You are in control of what you share.",
                font=("Segoe UI", 14, "bold"),
                fg=BURGUNDY,
                bg=CARD
                ).pack(pady=(20, 8))

            # Warning message
            tk.Label(
                card,
                text=(
                    "Skip is always available for optional questions. "
                    "Cycora is a tracking and education tool, not a "
                    "fertility test or medical service."
                ),
                font=("Segoe UI", 10),
                fg=MUTED,
                bg=CARD,
                wraplength=560,
                justify="center"
            ).pack(padx=24, pady=(0, 20))
        elif kind in ("results", "fertility_results", "period_status"):
            last = self.onboarding_answers.get("last_period", "")
            if kind == "fertility_results":
                tk.Label(card, text="Your possible fertile window", font=("Segoe UI", 15, "bold"), fg=BURGUNDY, bg=CARD).pack(pady=(20,8))
                if last and last != "Skipped":
                    try:
                        start_date=parse_date(last)
                        window_start=start_date + __import__("datetime").timedelta(days=9)
                        window_end=start_date + __import__("datetime").timedelta(days=15)
                        msg=f"Using a simple 28-day cycle assumption, a possible fertile window could be around {window_start.strftime('%b %d')}–{window_end.strftime('%b %d, %Y')}. Actual ovulation may happen earlier or later."
                    except ValueError: msg="Add a valid last-period date to see a rough calendar estimate. This cannot confirm ovulation."
                else: msg="Add your last period date to see a rough calendar estimate. It cannot confirm ovulation or guarantee conception."
                tk.Label(card,text=msg,font=("Segoe UI",10),fg=TEXT,bg=CARD,wraplength=560,justify="center").pack(padx=24,pady=(0,12))
                tk.Label(card,text="Do not use this estimate as contraception. A healthcare professional can offer personalized preconception advice.",font=("Segoe UI",9),fg=MUTED,bg=CARD,wraplength=560,justify="center").pack(padx=24,pady=(0,18))
            elif kind == "period_status":
                tk.Label(card, text="Are you currently on your period?", font=("Segoe UI", 15, "bold"), fg=BURGUNDY, bg=CARD).pack(pady=(20,8))
                if last and last != "Skipped":
                    try:
                        start_date=parse_date(last); elapsed=(date.today()-start_date).days
                        if 0 <= elapsed <= 4: msg=f"Based on the date entered, you may be around day {elapsed+1} of your period if bleeding usually lasts about 5 days. Confirm this with your actual symptoms."
                        elif elapsed < 0: msg="The date entered is in the future. Please review it before relying on estimates."
                        else: msg="Based on a typical 5-day example, you may not currently be on your period. This is only a rough guess; record actual bleeding in the tracker."
                    except ValueError: msg="Enter a valid last-period date to view a rough estimate."
                else: msg="Cycora does not know your current period status yet. Record actual bleeding dates for a more useful overview."
                tk.Label(card,text=msg,font=("Segoe UI",10),fg=TEXT,bg=CARD,wraplength=560,justify="center").pack(padx=24,pady=(0,12))
                tk.Label(card,text="Possible symptoms include cramps, fatigue, bloating, headache, or mood changes. Rest, hydration, gentle movement, or a warm pack may help some people. There is no universal list of activities everyone must avoid; pause anything that worsens your symptoms or follow clinician advice.",font=("Segoe UI",9),fg=MUTED,bg=CARD,wraplength=560,justify="left").pack(padx=24,pady=(0,18))
            else:
                if last and last != "Skipped":
                    try:
                        next_estimate = parse_date(last) + __import__("datetime").timedelta(days=28)
                        result_text = f"Using a temporary 28-day default, your next period estimate is around {next_estimate.strftime('%B %d, %Y')}. This is only a starting estimate and may be inaccurate."
                    except (ValueError, TypeError):
                        result_text = "Once you log accurate period dates, Cycora can calculate a basic estimate from your recorded history."
                else:
                    result_text = "Log the first day of your next period to begin building your cycle history. Cycora needs recorded dates before it can show a personal estimate."
                tk.Label(card, text="Your personal starting point", font=("Segoe UI", 15, "bold"), fg=BURGUNDY, bg=CARD).pack(pady=(20, 8))
                tk.Label(card, text=result_text, font=("Segoe UI", 10), fg=TEXT, bg=CARD, wraplength=560, justify="center").pack(padx=24, pady=(0, 12))
                tk.Label(card, text="Fertile-window and ovulation estimates are uncertain and must not be used to prevent pregnancy.", font=("Segoe UI", 9), fg=MUTED, bg=CARD, wraplength=560, justify="center").pack(padx=24, pady=(0, 18))
        elif kind == "complete":
            tk.Label(card, text="✓", font=("Segoe UI", 34, "bold"), fg=BURGUNDY, bg=CARD).pack(pady=(18, 4))
            tk.Label(card, text="You're ready to TRACK NOW!", font=("Segoe UI", 17, "bold"), fg=BURGUNDY, bg=CARD).pack(pady=(0, 8))
            tk.Label(card, text="Your dashboard, calendar, symptom tracker, insights, journal, and learning library are ready to explore.", font=("Segoe UI", 10), fg=MUTED, bg=CARD, wraplength=560, justify="center").pack(padx=24, pady=(0, 20))
        return field_vars

    def _show_choice_note(self, key, value, label):
        notes = {
            "feeling": {
                "Excited and ready to learn":"That's a great starting point. Explore at your own pace and remember that every cycle is individual.",
                "A bit unsure or unprepared":"It's okay not to know everything yet. Start with one simple step: record dates and questions as they come up.",
                "Worried or stressed":"Take a breath—your answer is valid. Cycora is for learning, not judging. If a health concern is worrying you, a trusted person or clinician can help.",
                "Happy, nervous, and excited":"Mixed feelings are normal. You can skip any optional question and return when you're ready.",
                "Just exploring":"Welcome. You can browse the health library first and only track what feels useful."},
            "pregnancy_timing": {"As soon as possible":"Cycle estimates cannot guarantee conception. Consider a preconception conversation with a qualified healthcare professional.","No rush — I want to learn first":"Learning about cycles and general health is a useful first step; you do not need to have every answer today.","I'm supporting my partner or someone I care about":"Supportive listening and asking what help they want can be more useful than making assumptions."},
            "trying_duration": {"More than 12 months":"Consider discussing fertility questions with a healthcare professional. They can advise based on age, history, and individual circumstances.","6–12 months":"A clinician can help you understand whether an assessment is appropriate for your situation.","Not trying yet":"That's fine. You can use the app for general learning without tracking conception."},
            "fertile_days": {"Yes, I track them":"Tracking can help you learn patterns, but app predictions are estimates and do not confirm ovulation.","Not yet":"No problem. Cycora's Learn section explains cycle phases, but calendar estimates should not be used as contraception."},
            "period_regular": {"Often irregular":"If this is persistent, new, or concerning, consider noting dates and discussing the pattern with a clinician.","My periods have not started":"If you're concerned about puberty or development, a trusted adult and healthcare professional can offer individual guidance.","I do not get periods":"There can be many reasons. If this is unexpected or concerning, seek advice from a qualified clinician."},
            "discharge": {"I have questions or concerns":"Discharge can vary. Seek medical advice for strong odor, itching, pain, fever, or an unusual persistent change.","I sometimes notice changes":"Recording changes alongside dates may help you understand your own pattern, but appearance alone cannot diagnose anything."},
            "healthy_diet": {"I'd like support with this":"Aim for practical, nourishing habits rather than perfection. A registered dietitian or clinician can offer tailored guidance."},
            "precheckup": {"Not yet":"You can write down questions about medicines, health history, and supplements before an appointment."}
        }
        message = notes.get(key, {}).get(value, "Thanks for sharing. This answer helps tailor your experience; it is not a diagnosis or a judgement.")
        label.configure(text=message)

    def open_date_picker(self, variable, allow_future=False, parent=None):
        parent = parent or self
        try:
            selected = date.fromisoformat(variable.get().strip())
        except (ValueError, TypeError):
            selected = date.today()
        if not allow_future and selected > date.today():
            selected = date.today()

        win = tk.Toplevel(parent)
        win.title("Choose a date")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.transient(parent)
        try:
            win.grab_set()
        except tk.TclError:
            pass

        def save(chosen):
            variable.set(chosen.isoformat())
            win.destroy()

        picker = DateWheelPicker(win, initial_date=selected, on_select=save,
                                 allow_future=allow_future)
        picker.pack(fill="both", expand=True)
        win.update_idletasks()
        width = max(450, win.winfo_reqwidth())
        height = max(370, win.winfo_reqheight())
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - width) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - height) // 2)
        win.geometry(f"{width}x{height}+{x}+{y}")
        win.protocol("WM_DELETE_WINDOW", win.destroy)

    def show_privacy_details(self):
        win = tk.Toplevel(self); win.title("Cycora privacy summary & terms"); win.configure(bg=BG); win.geometry("650x570"); win.transient(self)
        tk.Label(win, text="Privacy summary & terms", font=("Segoe UI", 18, "bold"), fg=BURGUNDY, bg=BG).pack(anchor="w", padx=22, pady=(20, 10))
        body = tk.Text(win, wrap="word", font=("Segoe UI", 10), bg=CARD, fg=TEXT, relief="solid", bd=1, padx=14, pady=12)
        body.pack(fill="both", expand=True, padx=22, pady=(0, 14))
        policy = ("WHAT CYCORA STORES\nCycora saves the profile name, birth year, onboarding answers, period dates, symptoms, notes, and entries you choose to add. Records are linked to a local profile ID in the SQLite database inside the project folder.\n\n"
                  "WHERE DATA GOES\nThis version does not require Google sign-in and does not intentionally send records to an online account. Data stays in the local database unless you export or back up the file. Educational source links open in your web browser.\n\n"
                  "LIMITS OF PRIVACY\nThe database is not encrypted in this version. Anyone who can access your Windows account, project folder, backups, or exported files may be able to read the information. Do not use a shared or public computer for sensitive records. Profile names are not passwords.\n\n"
                  "YOUR CHOICES\nYou can skip optional questions, edit basic profile details, export your records, back up the database, or delete a profile and its linked records. Deletion from the active database does not erase copies in backups or exported files.\n\n"
                  "HEALTH LIMITATIONS\nCycora provides educational information and approximate cycle estimates. It does not diagnose conditions, confirm ovulation, guarantee conception, or prevent pregnancy. Seek a qualified healthcare professional for personal medical concerns.\n\n"
                  "TERMS OF USE\nUse Cycora for personal tracking and education, verify important health information with qualified sources, keep your device secure, and do not rely on predictions for medical decisions or contraception. This in-app summary describes the current local app; it is not a substitute for professional advice.")
        body.insert("1.0", policy); body.configure(state="disabled")
        self._button(win, "Close", win.destroy).pack(anchor="e", padx=22, pady=(0, 18))

    def _save_onboarding_current(self):
        fields = getattr(self, "_onboard_fields", {})
        if not fields:
            return True
        for key, field in fields.items():
            step = field["step"]
            kind = step["kind"]
            vars_ = field["vars"]
            if kind == "privacy":
                self.onboarding_answers.update({k: v.get() for k, v in vars_.items()})
                if not all(self.onboarding_answers.get(k) for k in ("privacy_policy", "health_data_consent")):
                    messagebox.showwarning("Consent required", "Please review and check both consent boxes to continue.", parent=self); return False
            elif kind in ("entry", "date", "birthday", "height", "weight"):
                if kind in ("height", "weight"):
                    try: raw=float(vars_["value"].get())
                    except (ValueError, tk.TclError):
                        messagebox.showwarning("Check measurement", "Choose a valid measurement.", parent=self); return False
                    unit=vars_["unit"].get()
                    if key == "height":
                        if (unit == "cm" and not 90 <= raw <= 220) or (unit == "in" and not 35 <= raw <= 87): messagebox.showwarning("Check height", "Choose a height within the available scale.", parent=self); return False
                    else:
                        if (unit == "kg" and not 20 <= raw <= 160) or (unit == "lb" and not 44 <= raw <= 350): messagebox.showwarning("Check weight", "Choose a weight within the available scale.", parent=self); return False
                    self.onboarding_answers[key] = {"value":raw,"unit":unit}
                    continue
                value = vars_[key].get().strip()
                if step.get("required") and not value:
                    messagebox.showwarning("Required information", "Please complete this field to continue.", parent=self); return False
                if key == "name" and (len(value) > 50 or any(ord(ch) < 32 for ch in value)):
                    messagebox.showwarning("Check the name", "Use a name of 50 characters or fewer.", parent=self); return False
                if key == "birth_date":
                    try: birthday = parse_date(value)
                    except ValueError:
                        messagebox.showwarning("Check birth date", "Choose a valid birth date from the calendar.", parent=self); return False
                    if birthday > date.today(): messagebox.showwarning("Check birth date", "Birth date cannot be in the future.", parent=self); return False
                    age = (date.today() - birthday).days / 365.2425
                    if age < 9:
                        messagebox.showwarning("Age guidance", "Cycora profile creation is available for users aged 9 and older. For a younger child with a health concern, involve a parent/guardian and a qualified healthcare professional.", parent=self); return False
                    self.onboarding_answers["birth_year"] = birthday.year
                    value = birthday.isoformat()
                if key == "last_period" and value:
                    try: valid_iso_date(value, "Last period start date")
                    except ValueError as exc:
                        messagebox.showwarning("Check date", str(exc), parent=self); return False
                self.onboarding_answers[key] = value
            elif kind == "choice":
                value = vars_[key].get()
                if value: self.onboarding_answers[key] = value
            elif kind == "multi":
                self.onboarding_answers[key] = [option for option, var in vars_.items() if var.get()]
        return True

    def onboarding_next(self):
        if not self._save_onboarding_current(): return
        batch = self.onboarding_batches[self.onboarding_index]
        if any(item["key"] == "goals" for item in batch):
            goals = self.onboarding_answers.get("goals", [])
            if not goals:
                messagebox.showinfo("Choose a goal", "Select at least one goal so Cycora can personalize your space.", parent=self); return
        if self.onboarding_index >= len(self.onboarding_batches) - 1:
            self.finish_onboarding(); return
        self.onboarding_index += 1
        self.render_onboarding_step()

    def _skip_this_onboarding_step(self, step):
        goals = self.onboarding_answers.get("goals", [])
        key = step["key"]
        conceive = "Get pregnant" in goals
        pregnancy = "Track my pregnancy" in goals
        period = "Track my period" in goals
        wellbeing = "Take charge of my well-being" in goals
        discharge = "Decode my discharge" in goals
        symptoms = "Understand my symptoms" in goals
        contraception = "Explore contraception" in goals
        if key == "purpose_custom" and self.onboarding_answers.get("purpose") != "Other": return True
        if key in {"pregnancy_timing","trying_duration","fertile_days","content_warning","first_time_trying","supplements","precheckup","partner_changes","healthy_diet"} and not conceive: return True
        if key in {"last_period","period_regular","contraception"} and not (period or conceive or pregnancy or contraception): return True
        if key == "fertility_results" and not conceive: return True
        if key == "period_status" and not (period or conceive or pregnancy): return True
        if key == "discharge" and not (discharge or conceive or wellbeing): return True
        if key in {"height","weight"} and not wellbeing: return True
        if key in {"cycle_experiences","pain_types","hormone_signs"} and not (symptoms or wellbeing or conceive or period): return True
        if key == "conditions" and not (conceive or pregnancy or symptoms or wellbeing): return True
        if key == "feeling_health" and not (wellbeing or symptoms): return True
        return False

    def onboarding_back(self):
        self._save_onboarding_current()
        if self.onboarding_index > 0:
            self.onboarding_index -= 1
            self.render_onboarding_step()

    def onboarding_skip(self):
        # Optional fields in the current batch are marked skipped without removing any question.
        for key, field in getattr(self, "_onboard_fields", {}).items():
            if key not in ("privacy", "name", "birth_date", "goals") and not field["step"].get("required"):
                self.onboarding_answers.setdefault(key, "Skipped")
        if self.onboarding_index < len(getattr(self, "onboarding_batches", [])) - 1:
            self.onboarding_index += 1
            self.render_onboarding_step()

    def finish_onboarding(self):
        try:
            name = str(self.onboarding_answers.get("name", "")).strip()
            birth_value = self.onboarding_answers.get("birth_date", "")
            year = parse_date(birth_value).year if birth_value and birth_value != "Skipped" else int(self.onboarding_answers.get("birth_year"))
            purpose = str(self.onboarding_answers.get("purpose", "Myself"))
            if purpose == "Other":
                custom = str(self.onboarding_answers.get("purpose_custom", "")).strip()
                purpose = custom[:40] if custom and custom != "Skipped" else "Other"
            self.profile_id = db.create_profile(name, year, purpose)
            db.save_profile_answers(self.profile_id, self.onboarding_answers)
            last_period = self.onboarding_answers.get("last_period")
            if last_period and last_period != "Skipped":
                try: db.add_period(self.profile_id, last_period, None, "Not recorded", "Added during onboarding")
                except sqlite3.IntegrityError: pass
            self._show_onboarding_shell(False)
            self.show_page("Home")
        except (ValueError, sqlite3.Error) as exc:
            messagebox.showerror("Could not create profile", f"Cycora could not save this profile. Please try again.\n{exc}", parent=self)

    def show_page(self, page):
        try: self.unbind_all("<MouseWheel>")
        except tk.TclError: pass
        if not self.profile_id:
            self.show_welcome()
            return
        self.active_page = page
        self._clear_content()
        if page == "Home": self.page_home()
        elif page == "Calendar": self.page_calendar()
        elif page in ("Track", "Period Tracker"): self.page_period_tracker()
        elif page == "Symptoms": self.page_symptoms()
        elif page == "Cycle Insights": self.page_insights()
        elif page == "Sex Tracker": self.page_sex_tracker()
        elif page == "Pregnancy Tracker": self.page_pregnancy_tracker()
        elif page in ("Learn", "Learn & Explore"): self.page_learn()
        elif page == "Journal": self.page_journal()
        elif page in ("Profile", "Profile & Settings"): self.page_profile()

    def page_home(self):
        profile = db.get_profile(self.profile_id)
        periods = db.list_periods(self.profile_id)
        summary = cycle_summary(periods)
        today = date.today()
        self._header(f"Hello, {profile['name']}.", "Your personal cycle overview. Log only what you know; predictions improve when you have more history.")
        row = tk.Frame(self.content, bg=BG)
        row.pack(fill="x", pady=(0, 14))
        metrics = [
            ("TODAY", today.strftime("%b %d"), "Daily check-in"),
            ("CYCLE LENGTH", f"{summary['average_cycle']} days", "Average / default estimate"),
            ("NEXT PERIOD", summary['next_period'].strftime("%b %d") if summary['next_period'] else "Not yet", "Estimated, not guaranteed"),
        ]
        for title, value, note in metrics:
            c = tk.Frame(row, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
            c.pack(side="left", fill="both", expand=True, padx=(0, 10))
            tk.Label(c, text=title, font=("Segoe UI", 8, "bold"), fg=MUTED, bg=CARD).pack(anchor="w", padx=16, pady=(16, 5))
            tk.Label(c, text=value, font=("Segoe UI", 19, "bold"), fg=BURGUNDY, bg=CARD).pack(anchor="w", padx=16)
            tk.Label(c, text=note, font=("Segoe UI", 8), fg=MUTED, bg=CARD).pack(anchor="w", padx=16, pady=(4, 16))
        symptom_card = tk.Frame(self.content, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        symptom_card.pack(fill="x", pady=(0, 14))
        tk.Label(symptom_card, text="How are you feeling today?", font=("Segoe UI", 13, "bold"), fg=TEXT, bg=CARD).pack(anchor="w", padx=18, pady=(14, 3))
        tk.Label(symptom_card, text="Tap an icon for a quick check-in. These are observations, not diagnoses.", font=("Segoe UI", 9), fg=MUTED, bg=CARD).pack(anchor="w", padx=18, pady=(0, 10))
        symptom_row = tk.Frame(symptom_card, bg=CARD); symptom_row.pack(fill="x", padx=12, pady=(0, 14))
        for label, asset in [("Cramps","cramps"),("Headache","headache"),("Bloating","bloating"),("Acne","acne"),("Fatigue","fatigue"),("Mood changes","mood_changes")]:
            tile=tk.Frame(symptom_row,bg="#FFF8FA",highlightbackground="#F0DDE3",highlightthickness=1); tile.pack(side="left",fill="both",expand=True,padx=3)
            path=ASSET_DIR/"symptoms"/f"{asset}.png"
            if path.exists():
                try:
                    im=tk.PhotoImage(file=str(path)); im=im.subsample(max(1,im.width()//44),max(1,im.height()//44)); self._images[f"home_{asset}"]=im
                    tk.Button(tile,image=im,text=label,compound="top",command=lambda x=label:self._quick_symptom(x),relief="flat",bd=0,bg="#FFF8FA",activebackground=PINK,fg=BURGUNDY,font=("Segoe UI",8,"bold"),wraplength=85,pady=7).pack(fill="both",expand=True)
                except tk.TclError: tk.Button(tile,text=label,command=lambda x=label:self._quick_symptom(x),bg="#FFF8FA",fg=BURGUNDY).pack(fill="both",expand=True)
        lower = tk.Frame(self.content, bg=BG)
        lower.pack(fill="both", expand=True)
        left = tk.Frame(lower, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))
        tk.Label(left, text="Your cycle at a glance", font=("Segoe UI", 13, "bold"), fg=TEXT, bg=CARD).pack(anchor="w", padx=18, pady=(18, 8))
        tk.Label(left, text=f"Last recorded period: {fmt_day(summary['last_start'])}", font=("Segoe UI", 10), fg=TEXT, bg=CARD).pack(anchor="w", padx=18, pady=5)
        tk.Label(left, text=f"Estimated ovulation: {fmt_day(summary['ovulation'])}", font=("Segoe UI", 10), fg=TEXT, bg=CARD).pack(anchor="w", padx=18, pady=5)
        tk.Label(left, text=f"Estimated fertile window: {fmt_day(summary['fertile_start'])} – {summary['fertile_end'].strftime('%b %d, %Y') if summary['fertile_end'] else 'Not enough data'}", font=("Segoe UI", 10), fg=TEXT, bg=CARD, wraplength=420, justify="left").pack(anchor="w", padx=18, pady=5)
        tk.Label(left, text=f"Based on {summary['cycles_counted']} recorded cycle interval(s). Calendar estimates cannot confirm ovulation or prevent pregnancy.", font=("Segoe UI", 9), fg=MUTED, bg=CARD, wraplength=430, justify="left").pack(anchor="w", padx=18, pady=(8, 18))
        right = tk.Frame(lower, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        right.pack(side="left", fill="both", expand=True)
        tk.Label(right, text="Quick actions", font=("Segoe UI", 13, "bold"), fg=TEXT, bg=CARD).pack(anchor="w", padx=18, pady=(18, 10))
        self._button(right, "＋  Log a period", lambda: self.show_page("Track")).pack(fill="x", padx=18, pady=5)
        self._button(right, "＋  Record symptoms", lambda: self.show_page("Symptoms"), False).pack(fill="x", padx=18, pady=5)
        self._button(right, "◇  Explore health library", lambda: self.show_page("Learn"), False).pack(fill="x", padx=18, pady=5)
        tk.Label(right, text="Your records belong to this profile only.", font=("Segoe UI", 9), fg=MUTED, bg=CARD, wraplength=280).pack(anchor="w", padx=18, pady=12)

    def _quick_symptom(self, symptom_name):
        self.show_page("Symptoms")
        self.after(100, lambda: getattr(self, "_active_symptom_var", tk.StringVar()).set(symptom_name))

    def page_calendar(self):
        self._header("Cycle calendar", "Recorded dates are solid burgundy. Predicted dates are lighter and are estimates only.")
        periods = db.list_periods(self.profile_id)
        summary = cycle_summary(periods)
        if not hasattr(self, "calendar_month"):
            today = date.today(); self.calendar_month = date(today.year, today.month, 1)
        month = self.calendar_month
        toolbar = tk.Frame(self.content, bg=BG); toolbar.pack(fill="x", pady=(0, 10))
        self._button(toolbar, "← Previous", lambda: self.change_calendar_month(-1), False).pack(side="left")
        tk.Label(toolbar, text=month.strftime("%B %Y"), font=("Segoe UI", 16, "bold"), fg=BURGUNDY, bg=BG).pack(side="left", expand=True)
        self._button(toolbar, "Next →", lambda: self.change_calendar_month(1), False).pack(side="right")
        calcard = self._card(self.content, "Your cycle at a glance")
        calcard.pack(fill="x", pady=(0, 12))
        grid = tk.Frame(calcard, bg=CARD); grid.pack(fill="x", padx=12, pady=(0, 14))
        weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for col, name in enumerate(weekdays):
            tk.Label(grid, text=name, font=("Segoe UI", 9, "bold"), fg=MUTED, bg=CARD).grid(row=0, column=col, sticky="nsew", padx=2, pady=4)
            grid.grid_columnconfigure(col, weight=1, uniform="day")
        recorded_starts = set()
        recorded_period_days = set()
        for item in periods:
            try:
                start_day=date.fromisoformat(item["start_date"]); recorded_starts.add(start_day)
                end_day=date.fromisoformat(item["end_date"]) if item["end_date"] else start_day
                cursor=start_day
                while cursor <= end_day:
                    recorded_period_days.add(cursor); cursor += __import__("datetime").timedelta(days=1)
            except (ValueError, TypeError): pass
        predicted = summary.get("next_period")
        month_days = calendar_module.monthcalendar(month.year, month.month)
        for row_idx, week in enumerate(month_days, start=1):
            for col, day_num in enumerate(week):
                if day_num == 0:
                    tk.Label(grid, text="", bg=CARD, height=2).grid(row=row_idx, column=col, sticky="nsew", padx=2, pady=2)
                    continue
                this_day = date(month.year, month.month, day_num)
                if this_day in recorded_starts:
                    bg, fg = BURGUNDY, "white"
                    label = f"{day_num}  •"
                elif this_day in recorded_period_days:
                    bg, fg = CRIMSON, "white"
                    label = str(day_num)
                elif predicted and this_day == predicted:
                    bg, fg = PINK, BURGUNDY
                    label = f"{day_num}  *"
                else:
                    bg, fg = "#FFFFFF", TEXT
                    label = str(day_num)
                tk.Label(grid, text=label, font=("Segoe UI", 10, "bold" if this_day in recorded_starts or (predicted and this_day == predicted) else "normal"), fg=fg, bg=bg, relief="flat", height=2, highlightbackground=BORDER, highlightthickness=1).grid(row=row_idx, column=col, sticky="nsew", padx=2, pady=2)
        legend = tk.Frame(calcard, bg=CARD); legend.pack(anchor="w", padx=18, pady=(0, 12))
        tk.Label(legend, text="● Period start", fg=BURGUNDY, bg=CARD, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 12))
        tk.Label(legend, text="● Recorded period days", fg=CRIMSON, bg=CARD, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 12))
        tk.Label(legend, text="* Estimated next period", fg=BURGUNDY, bg=CARD, font=("Segoe UI", 9)).pack(side="left", padx=(0,12))
        tk.Label(calcard, text="Color guide: dark burgundy = logged start date; crimson = logged bleeding days; pale pink = estimated date; white = no period record. Estimates may be wrong.", font=("Segoe UI",9), fg=MUTED, bg=CARD, wraplength=850, justify="left").pack(anchor="w",padx=18,pady=(0,12))
        history = self._card(self.content, "Recorded period history")
        history.pack(fill="both", expand=True)
        cols = ("start", "end", "flow", "notes")
        tree = ttk.Treeview(history, columns=cols, show="headings", height=5)
        for col, heading, width in [("start", "Start date", 130), ("end", "End date", 130), ("flow", "Flow", 120), ("notes", "Notes", 380)]:
            tree.heading(col, text=heading); tree.column(col, width=width, anchor="w")
        tree.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        for item in periods:
            tree.insert("", "end", iid=str(item["id"]), values=(item["start_date"], item["end_date"] or "Not recorded", item["flow"], item["notes"] or "—"))
        if not periods:
            tk.Label(history, text="No periods recorded yet. Use Period Tracker to add your first start date.", font=("Segoe UI", 9), fg=MUTED, bg=CARD).pack(anchor="w", padx=18, pady=(0, 12))

    def change_calendar_month(self, delta):
        current = self.calendar_month
        month_index = current.month - 1 + delta
        year = current.year + month_index // 12
        month = month_index % 12 + 1
        self.calendar_month = date(year, month, 1)
        self.show_page("Calendar")

    def page_track(self):
        self._header("Track your health", "Record a period, log symptoms, or write a private note. Dates are checked before saving.")
        columns = tk.Frame(self.content, bg=BG); columns.pack(fill="both", expand=True)
        period = tk.Frame(columns, bg=CARD, highlightbackground=BORDER, highlightthickness=1); period.pack(side="left", fill="both", expand=True, padx=(0, 10))
        tk.Label(period, text="Period record", font=("Segoe UI", 14, "bold"), fg=TEXT, bg=CARD).pack(anchor="w", padx=18, pady=(18, 4))
        tk.Label(period, text="Dates use YYYY-MM-DD.", font=("Segoe UI", 9), fg=MUTED, bg=CARD).pack(anchor="w", padx=18, pady=(0, 12))
        start_var = tk.StringVar(value=date.today().isoformat()); end_var = tk.StringVar(); flow_var = tk.StringVar(value="Not recorded")
        self._date_field(period, "Period start date *", start_var)
        self._date_field(period, "Period end date (optional)", end_var)
        self._combo_field(period, "Flow", flow_var, ["Not recorded", "Spotting", "Light", "Medium", "Heavy"])
        note_text = self._text_field(period, "Notes (optional)", height=3)
        def save_period():
            try:
                start = valid_iso_date(start_var.get(), "Start date")
                end = valid_iso_date(end_var.get(), "End date") if end_var.get().strip() else None
                if end and end < start: raise ValueError("End date cannot be earlier than the start date.")
                if end and (end - start).days > 14: raise ValueError("Please check the end date; a period record longer than 14 days may be an input error. If this is correct, consider seeking medical advice.")
                if start > date.today(): raise ValueError("A period start date cannot be in the future.")
                for existing in db.list_periods(self.profile_id):
                    old_start=date.fromisoformat(existing["start_date"]); old_end=date.fromisoformat(existing["end_date"]) if existing["end_date"] else old_start
                    new_end=end or start
                    if start <= old_end and new_end >= old_start: raise ValueError(f"This record overlaps an existing period starting {existing['start_date']}. Review your history first.")
                db.add_period(self.profile_id, start.isoformat(), end.isoformat() if end else None, flow_var.get(), note_text.get("1.0", "end"))
            except sqlite3.IntegrityError:
                messagebox.showerror("Duplicate record", "A period start date is already recorded for this profile. Review the calendar before adding it again."); return
            except ValueError as exc:
                messagebox.showerror("Check your entry", str(exc)); return
            messagebox.showinfo("Saved", "Period record saved to this profile."); self.show_page("Calendar")
        self._button(period, "Save period record", save_period).pack(anchor="w", padx=18, pady=18)

        symptoms = tk.Frame(columns, bg=CARD, highlightbackground=BORDER, highlightthickness=1); symptoms.pack(side="left", fill="both", expand=True)
        tk.Label(symptoms, text="Symptom check-in", font=("Segoe UI", 14, "bold"), fg=TEXT, bg=CARD).pack(anchor="w", padx=18, pady=(18, 4))
        tk.Label(symptoms, text="Record what you notice. This does not diagnose a condition.", font=("Segoe UI", 9), fg=MUTED, bg=CARD, wraplength=400, justify="left").pack(anchor="w", padx=18, pady=(0, 12))
        symptom_date = tk.StringVar(value=date.today().isoformat()); symptom_var = tk.StringVar(value="Cramps"); intensity_var = tk.StringVar(value="Mild")
        self._field(symptoms, "Date *", symptom_date)
        self._combo_field(symptoms, "Symptom *", symptom_var, ["Cramps", "Headache", "Bloating", "Acne", "Fatigue", "Mood changes", "Tender breasts", "Spotting", "Discharge observation", "Other"])
        self._combo_field(symptoms, "Intensity", intensity_var, ["Mild", "Moderate", "Severe"])
        symptom_notes = self._text_field(symptoms, "Notes (optional)", height=3)
        def save_symptom():
            try: log_date = valid_iso_date(symptom_date.get(), "Symptom date")
            except ValueError as exc: messagebox.showerror("Check your entry", str(exc)); return
            db.add_symptom(self.profile_id, log_date.isoformat(), symptom_var.get(), intensity_var.get(), symptom_notes.get("1.0", "end"))
            messagebox.showinfo("Saved", "Symptom check-in saved to this profile."); self.page_track()
        self._button(symptoms, "Save symptom check-in", save_symptom).pack(anchor="w", padx=18, pady=18)
        history = self._card(self.content, "Recent symptom entries")
        history.pack(fill="x", pady=(14, 0))
        recent = db.list_symptoms(self.profile_id, 4)
        if recent:
            for item in recent:
                tk.Label(history, text=f"{item['log_date']}  ·  {item['symptom']} ({item['intensity']})", font=("Segoe UI", 9), fg=TEXT, bg=CARD).pack(anchor="w", padx=18, pady=3)
        else:
            tk.Label(history, text="No symptoms logged yet.", font=("Segoe UI", 9), fg=MUTED, bg=CARD).pack(anchor="w", padx=18, pady=(0, 14))

    def _field(self, parent, label, variable):
        tk.Label(parent, text=label, font=("Segoe UI", 9, "bold"), fg=TEXT, bg=CARD).pack(anchor="w", padx=18, pady=(6, 4))
        entry = tk.Entry(parent, textvariable=variable, font=("Segoe UI", 10), relief="solid", bd=1, highlightthickness=1, highlightbackground=BORDER)
        entry.pack(fill="x", padx=18, ipady=7)
        return entry

    def _date_field(self, parent, label, variable):
        tk.Label(parent, text=label, font=("Segoe UI", 9, "bold"), fg=TEXT, bg=CARD).pack(anchor="w", padx=18, pady=(6,4))
        row=tk.Frame(parent,bg=CARD); row.pack(fill="x",padx=18)
        entry=tk.Entry(row,textvariable=variable,font=("Segoe UI",10),relief="solid",bd=1,highlightthickness=1,highlightbackground=BORDER)
        entry.pack(side="left",fill="x",expand=True,ipady=7)
        self._button(row,"▦",lambda v=variable:self.open_date_picker(v,allow_future=False,parent=self),False).pack(side="left",padx=(6,0))
        return entry

    def _combo_field(self, parent, label, variable, values):
        tk.Label(parent, text=label, font=("Segoe UI", 9, "bold"), fg=TEXT, bg=CARD).pack(anchor="w", padx=18, pady=(10, 4))
        combo = ttk.Combobox(parent, textvariable=variable, values=values, state="readonly", font=("Segoe UI", 10))
        combo.pack(fill="x", padx=18, ipady=4)
        return combo

    def _text_field(self, parent, label, height=3):
        tk.Label(parent, text=label, font=("Segoe UI", 9, "bold"), fg=TEXT, bg=CARD).pack(anchor="w", padx=18, pady=(10, 4))
        widget = tk.Text(parent, height=height, font=("Segoe UI", 10), relief="solid", bd=1, wrap="word", highlightthickness=1, highlightbackground=BORDER)
        widget.pack(fill="x", padx=18)
        return widget

    def page_learn(self):
        self._header("Learn & explore", "Browse menstrual and reproductive health topics. Search, scroll, and open trusted source links for more details.")
        search_var=tk.StringVar()
        search_row=tk.Frame(self.content,bg=BG); search_row.pack(fill="x",pady=(0,10))
        tk.Label(search_row,text="Search topics",font=("Segoe UI",10,"bold"),fg=TEXT,bg=BG).pack(side="left",padx=(0,10))
        search=tk.Entry(search_row,textvariable=search_var,font=("Segoe UI",10),relief="solid",bd=1); search.pack(side="left",fill="x",expand=True,ipady=7)
        outer=tk.Frame(self.content,bg=BG); outer.pack(fill="both",expand=True)
        canvas=tk.Canvas(outer,bg=BG,highlightthickness=0)
        scrollbar=ttk.Scrollbar(outer,orient="vertical",command=canvas.yview)
        results=tk.Frame(canvas,bg=BG)
        window_id=canvas.create_window((0,0),window=results,anchor="nw")
        results.bind("<Configure>",lambda e:canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",lambda e:canvas.itemconfigure(window_id,width=e.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left",fill="both",expand=True); scrollbar.pack(side="right",fill="y")
        def wheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)),"units")
        canvas.bind_all("<MouseWheel>",wheel)
        def render(*_):
            for child in results.winfo_children(): child.destroy()
            term=search_var.get().strip().lower()
            matches=[a for a in ARTICLES if term in (a['title']+' '+a['category']+' '+a['body']+' '+a.get('advice','')).lower()]
            if not matches:
                tk.Label(results,text="No matching topics. Try PCOS, cramps, discharge, menopause, endometriosis, or periods.",font=("Segoe UI",10),fg=MUTED,bg=BG,wraplength=800).pack(anchor="w",pady=12); return
            for article in matches:
                card=tk.Frame(results,bg=CARD,highlightbackground=BORDER,highlightthickness=1); card.pack(fill="x",pady=5)
                tk.Label(card,text=article["category"].upper(),font=("Segoe UI",8,"bold"),fg=BURGUNDY,bg=CARD).pack(anchor="w",padx=16,pady=(12,3))
                tk.Label(card,text=article["title"],font=("Segoe UI",13,"bold"),fg=TEXT,bg=CARD,wraplength=850,justify="left").pack(anchor="w",padx=16)
                tk.Label(card,text=article["body"],font=("Segoe UI",10),fg=MUTED,bg=CARD,wraplength=850,justify="left").pack(anchor="w",padx=16,pady=8)
                if article.get("advice"):
                    tip=tk.Frame(card,bg=PINK); tip.pack(fill="x",padx=16,pady=(0,8))
                    tk.Label(tip,text="WHAT YOU CAN DO",font=("Segoe UI",8,"bold"),fg=BURGUNDY,bg=PINK).pack(anchor="w",padx=10,pady=(8,2))
                    tk.Label(tip,text=article["advice"],font=("Segoe UI",9),fg=TEXT,bg=PINK,wraplength=820,justify="left").pack(anchor="w",padx=10,pady=(0,8))
                link=tk.Label(card,text=f"Source: {article['source']}  ↗",font=("Segoe UI",9,"underline"),fg=BURGUNDY,bg=CARD,cursor="hand2")
                link.pack(anchor="w",padx=16,pady=(0,12)); link.bind("<Button-1>",lambda e,url=article['url']:webbrowser.open(url))
        search_var.trace_add("write",render); render()

    def page_period_tracker(self):
        self._header("Period tracker", "Log period dates and flow. Recorded dates and predictions are shown separately.")
        self.page_track_period_only()

    def page_track_period_only(self):
        card = self._card(self.content, "Add a period record")
        card.pack(fill="x", pady=(0, 14))
        start_var = tk.StringVar(value=date.today().isoformat()); end_var = tk.StringVar(); flow_var = tk.StringVar(value="Not recorded")
        self._date_field(card, "Start date *", start_var)
        self._date_field(card, "End date (optional)", end_var)
        self._combo_field(card, "Flow", flow_var, ["Not recorded", "Spotting", "Light", "Medium", "Heavy"])
        notes = self._text_field(card, "Notes (optional)", 2)
        def save():
            try:
                start = valid_iso_date(start_var.get(), "Start date")
                end = valid_iso_date(end_var.get(), "End date") if end_var.get().strip() else None
                if end and end < start: raise ValueError("End date cannot be earlier than start date.")
                if end and (end-start).days > 14: raise ValueError("Please check the end date; this duration is unusually long. If this is correct, seek medical advice about prolonged bleeding.")
                if end and (end-start).days < 0: raise ValueError("End date cannot be before the start date.")
                if start > date.today(): raise ValueError("A period start date cannot be in the future.")
                for existing in db.list_periods(self.profile_id):
                    old_start = date.fromisoformat(existing["start_date"])
                    old_end = date.fromisoformat(existing["end_date"]) if existing["end_date"] else old_start
                    new_end = end or start
                    if start <= old_end and new_end >= old_start:
                        raise ValueError(f"This date overlaps an existing period record ({existing['start_date']} to {existing['end_date'] or existing['start_date']}). Review your calendar before saving.")
                db.add_period(self.profile_id, start.isoformat(), end.isoformat() if end else None, flow_var.get(), notes.get("1.0", "end"))
            except sqlite3.IntegrityError:
                messagebox.showerror("Duplicate date", "A period starting on this date is already saved for this profile."); return
            except ValueError as exc: messagebox.showerror("Check entry", str(exc)); return
            messagebox.showinfo("Saved", "Period record saved."); self.show_page("Calendar")
        self._button(card, "Save period", save).pack(anchor="w", padx=18, pady=18)
        hist = self._card(self.content, "Recent period history"); hist.pack(fill="both", expand=True)
        tree = ttk.Treeview(hist, columns=("start","end","flow"), show="headings", height=7)
        for col, label in [("start","Start date"),("end","End date"),("flow","Flow")]: tree.heading(col,text=label); tree.column(col,width=180)
        tree.pack(fill="both", expand=True, padx=14, pady=(0,14))
        for x in db.list_periods(self.profile_id): tree.insert("","end",values=(x["start_date"],x["end_date"] or "Not recorded",x["flow"]))

    def page_symptoms(self):
        self._header("Symptom tracker", "Record how you feel and review your own observations. These entries are not a diagnosis.")
        self.page_symptom_only()

    def page_symptom_only(self):
        card = self._card(self.content, "Daily check-in"); card.pack(fill="x", pady=(0,12))
        day = tk.StringVar(value=date.today().isoformat()); symptom = tk.StringVar(value="Cramps"); self._active_symptom_var = symptom; intensity = tk.StringVar(value="Mild")
        self._field(card,"Date * (YYYY-MM-DD)",day)
        iconstrip=tk.Frame(card,bg=CARD); iconstrip.pack(fill="x",padx=14,pady=(4,8))
        for label,asset in [("Cramps","cramps"),("Headache","headache"),("Bloating","bloating"),("Acne","acne"),("Fatigue","fatigue"),("Mood changes","mood_changes"),("Tender breasts","tender_breasts"),("Spotting","spotting"),("Discharge","discharge_observation"),("Sleep","sleep_changes")]:
            path=ASSET_DIR/"symptoms"/f"{asset}.png"
            if path.exists():
                try:
                    im=tk.PhotoImage(file=str(path)); im=im.subsample(max(1,im.width()//30),max(1,im.height()//30)); self._images[f"form_{asset}"]=im
                    tk.Button(iconstrip,image=im,text=label,compound="top",command=lambda x=label:symptom.set("Discharge observation" if x=="Discharge" else x),relief="flat",bd=0,bg=CARD,fg=BURGUNDY,font=("Segoe UI",7),wraplength=58).pack(side="left",expand=True,fill="x")
                except tk.TclError: pass
        self._combo_field(card,"What did you notice?",symptom,["Cramps","Headache","Bloating","Acne","Fatigue","Mood changes","Tender breasts","Spotting","Discharge observation","Sleep changes","Other"])
        self._combo_field(card,"Intensity",intensity,["Mild","Moderate","Severe"])
        note=self._text_field(card,"Notes (optional)",3)
        def save():
            try: d=valid_iso_date(day.get(),"Symptom date")
            except ValueError as exc: messagebox.showerror("Check date",str(exc)); return
            db.add_symptom(self.profile_id,d.isoformat(),symptom.get(),intensity.get(),note.get("1.0","end"))
            messagebox.showinfo("Saved","Symptom entry saved to the active profile."); self.show_page("Symptoms")
        self._button(card,"Save check-in",save).pack(anchor="w",padx=18,pady=18)
        hist=self._card(self.content,"Recent check-ins"); hist.pack(fill="both",expand=True)
        tree=ttk.Treeview(hist,columns=("date","symptom","intensity","notes"),show="headings",height=7)
        for col,label,width in [("date","Date",130),("symptom","Symptom",180),("intensity","Intensity",120),("notes","Notes",360)]: tree.heading(col,text=label); tree.column(col,width=width,anchor="w")
        tree.pack(fill="both",expand=True,padx=14,pady=(0,14))
        for x in db.list_symptoms(self.profile_id,50): tree.insert("","end",values=(x["log_date"],x["symptom"],x["intensity"],x["notes"] or "—"))

    def page_insights(self):
        self._header("Cycle insights", "A summary of what has been recorded in this profile. Estimates are not medical conclusions.")
        periods=db.list_periods(self.profile_id); summary=cycle_summary(periods); symptoms=db.list_symptoms(self.profile_id,100000)
        cards=tk.Frame(self.content,bg=BG); cards.pack(fill="x",pady=6)
        metrics=[("Recorded periods",str(len(periods)),"Saved start dates"),("Average cycle",f"{summary['average_cycle']} days","Estimate from available intervals"),("Symptom entries",str(len(symptoms)),"Your logged observations")]
        for title,value,desc in metrics:
            c=tk.Frame(cards,bg=CARD,highlightbackground=BORDER,highlightthickness=1); c.pack(side="left",fill="both",expand=True,padx=(0,10))
            tk.Label(c,text=title,font=("Segoe UI",10,"bold"),fg=MUTED,bg=CARD).pack(anchor="w",padx=16,pady=(16,5))
            tk.Label(c,text=value,font=("Segoe UI",22,"bold"),fg=BURGUNDY,bg=CARD).pack(anchor="w",padx=16)
            tk.Label(c,text=desc,font=("Segoe UI",9),fg=MUTED,bg=CARD).pack(anchor="w",padx=16,pady=(4,16))
        card=self._card(self.content,"What your records show"); card.pack(fill="x",pady=10)
        tk.Label(card,text=f"Last period start: {fmt_day(summary['last_start'])}",font=("Segoe UI",10),fg=TEXT,bg=CARD).pack(anchor="w",padx=18,pady=5)
        tk.Label(card,text=f"Estimated next period: {fmt_day(summary['next_period'])}",font=("Segoe UI",10),fg=TEXT,bg=CARD).pack(anchor="w",padx=18,pady=5)
        counts={}
        for item in symptoms: counts[item['symptom']]=counts.get(item['symptom'],0)+1
        top=sorted(counts.items(),key=lambda x:(-x[1],x[0]))[:5]
        tk.Label(card,text="Most logged symptoms: "+(", ".join(f"{name} ({count})" for name,count in top) if top else "No symptom entries yet."),font=("Segoe UI",10),fg=TEXT,bg=CARD,wraplength=820,justify="left").pack(anchor="w",padx=18,pady=5)
        tk.Label(card,text="These summaries reflect only the information entered in Cycora. They cannot identify the cause of symptoms or confirm ovulation.",font=("Segoe UI",9),fg=MUTED,bg=CARD,wraplength=850,justify="left").pack(anchor="w",padx=18,pady=(8,18))

    def page_sex_tracker(self):
        self._header("Sex & intimacy tracker", "An optional private log for personal wellness notes. You can leave this section unused; no entry is required.")
        card=self._card(self.content,"Add a private entry"); card.pack(fill="x",pady=(0,12))
        day=tk.StringVar(value=date.today().isoformat()); kind=tk.StringVar(value="Personal note")
        self._field(card,"Date (YYYY-MM-DD)",day)
        self._combo_field(card,"Entry type",kind,["Personal note","Contraception note","Question for a healthcare professional","Wellness observation"])
        detail=self._text_field(card,"Private note (optional)",4)
        def save():
            try: d=valid_iso_date(day.get(),"Entry date")
            except ValueError as exc: messagebox.showerror("Check date",str(exc)); return
            if not detail.get("1.0","end").strip(): messagebox.showwarning("Add a note","Enter a short note or cancel this entry."); return
            db.add_activity(self.profile_id,"sex",d.isoformat(),kind.get()+" — "+detail.get("1.0","end").strip())
            messagebox.showinfo("Saved","Private entry saved locally."); self.show_page("Sex Tracker")
        self._button(card,"Save private entry",save).pack(anchor="w",padx=18,pady=18)
        hist=self._card(self.content,"Saved entries"); hist.pack(fill="both",expand=True)
        for item in db.list_activities(self.profile_id,"sex",50):
            tk.Label(hist,text=f"{item['log_date']}  ·  {item['details']}",font=("Segoe UI",9),fg=TEXT,bg=CARD,wraplength=850,justify="left").pack(anchor="w",padx=18,pady=5)

    def page_pregnancy_tracker(self):
        self._header("Pregnancy tracker", "Optional pregnancy journal and appointment notes. This is not a medical monitoring tool.")
        card=self._card(self.content,"Pregnancy journal"); card.pack(fill="x",pady=(0,12))
        day=tk.StringVar(value=date.today().isoformat()); kind=tk.StringVar(value="Daily note")
        self._field(card,"Date (YYYY-MM-DD)",day)
        self._combo_field(card,"Entry type",kind,["Daily note","Appointment reminder","Question for clinician","Symptom to discuss"])
        detail=self._text_field(card,"Note (optional)",4)
        def save():
            try: d=valid_iso_date(day.get(),"Entry date")
            except ValueError as exc: messagebox.showerror("Check date",str(exc)); return
            if not detail.get("1.0","end").strip(): messagebox.showwarning("Add a note","Enter a note before saving."); return
            db.add_activity(self.profile_id,"pregnancy",d.isoformat(),kind.get()+" — "+detail.get("1.0","end").strip())
            messagebox.showinfo("Saved","Journal note saved locally."); self.show_page("Pregnancy Tracker")
        self._button(card,"Save journal note",save).pack(anchor="w",padx=18,pady=18)
        hist=self._card(self.content,"Pregnancy journal entries"); hist.pack(fill="both",expand=True)
        for item in db.list_activities(self.profile_id,"pregnancy",50):
            tk.Label(hist,text=f"{item['log_date']}  ·  {item['details']}",font=("Segoe UI",9),fg=TEXT,bg=CARD,wraplength=850,justify="left").pack(anchor="w",padx=18,pady=5)

    def page_journal(self):
        self._header("Private journal", "Keep personal notes about your cycle, symptoms, questions, or wellness. Entries stay in the local database.")
        card=self._card(self.content,"Write a note"); card.pack(fill="x",pady=(0,12))
        day=tk.StringVar(value=date.today().isoformat()); self._field(card,"Date (YYYY-MM-DD)",day); body=self._text_field(card,"Your note",4)
        def save():
            try: d=valid_iso_date(day.get(),"Note date")
            except ValueError as exc: messagebox.showerror("Check date",str(exc)); return
            text=body.get("1.0","end").strip()
            if not text: messagebox.showwarning("Empty note","Write something before saving."); return
            db.add_note(self.profile_id,d.isoformat(),text); messagebox.showinfo("Saved","Journal note saved."); self.show_page("Journal")
        self._button(card,"Save note",save).pack(anchor="w",padx=18,pady=18)
        hist=self._card(self.content,"Your notes"); hist.pack(fill="both",expand=True)
        for item in db.list_notes(self.profile_id):
            row=tk.Frame(hist,bg=CARD); row.pack(fill="x",padx=18,pady=8)
            tk.Label(row,text=item["note_date"],font=("Segoe UI",9,"bold"),fg=BURGUNDY,bg=CARD).pack(anchor="w")
            tk.Label(row,text=item["body"],font=("Segoe UI",10),fg=TEXT,bg=CARD,wraplength=850,justify="left").pack(anchor="w",pady=3)
            self._button(row,"Delete note",lambda note_id=item["id"]: self.delete_note_entry(note_id),False).pack(anchor="w",pady=3)

    def delete_note_entry(self,note_id):
        if messagebox.askyesno("Delete note","Permanently delete this note?"):
            db.delete_note(note_id,self.profile_id); self.show_page("Journal")

    def page_profile(self):
        profile = db.get_profile(self.profile_id)
        self._header("Profile & privacy", "Manage the active profile, switch between local profiles, and control your data.")
        top = tk.Frame(self.content, bg=BG); top.pack(fill="x")
        card = tk.Frame(top, bg=CARD, highlightbackground=BORDER, highlightthickness=1); card.pack(fill="x", pady=(0, 12))
        tk.Label(card, text=profile["name"], font=("Segoe UI", 19, "bold"), fg=BURGUNDY, bg=CARD).pack(anchor="w", padx=18, pady=(18, 4))
        tk.Label(card, text=f"Birth year: {profile['birth_year']}     •     Purpose: {profile['purpose']}     •     Profile ID: {profile['id']}", font=("Segoe UI", 10), fg=MUTED, bg=CARD).pack(anchor="w", padx=18, pady=(0, 18))
        actions = tk.Frame(card, bg=CARD); actions.pack(anchor="w", padx=18, pady=(0, 18))
        self._button(actions, "Edit profile", lambda: self.edit_profile_dialog(self.profile_id), False).pack(side="left", padx=(0, 8))
        self._button(actions, "Switch profile", self.switch_profile_dialog).pack(side="left", padx=(0, 8))
        self._button(actions, "＋ Add profile", self.create_profile_dialog, False).pack(side="left", padx=(0, 8))
        self._button(actions, "Review onboarding", self.review_onboarding, False).pack(side="left")
        data = tk.Frame(self.content, bg=CARD, highlightbackground=BORDER, highlightthickness=1); data.pack(fill="x", pady=(0, 12))
        tk.Label(data, text="Your data", font=("Segoe UI", 13, "bold"), fg=TEXT, bg=CARD).pack(anchor="w", padx=18, pady=(16, 8))
        tk.Label(data, text="Cycora stores records in a local SQLite database on this computer. Anyone with access to your Windows account and app files may be able to access that data. Use Windows account security and keep backups in a private location.", font=("Segoe UI", 9), fg=MUTED, bg=CARD, wraplength=850, justify="left").pack(anchor="w", padx=18, pady=(0, 12))
        buttons = tk.Frame(data, bg=CARD); buttons.pack(anchor="w", padx=18, pady=(0, 16))
        self._button(buttons, "Back up database", self.backup_database).pack(side="left", padx=(0, 8))
        self._button(buttons, "Export profile as CSV", self.export_profile, False).pack(side="left", padx=(0, 8))
        self._button(buttons, "Delete this profile", self.delete_active_profile, False).pack(side="left")
        tk.Label(self.content, text="Health note: Cycora's estimates are informational only. Seek qualified medical advice for personal health concerns.", font=("Segoe UI", 9), fg=MUTED, bg=BG, wraplength=850, justify="left").pack(anchor="w", pady=4)

    def review_onboarding(self):
        answers = db.get_profile_answers(self.profile_id)
        win = tk.Toplevel(self); win.title("Onboarding answers"); win.configure(bg=BG); win.geometry("620x560"); win.transient(self)
        tk.Label(win,text="Your onboarding answers",font=("Segoe UI",18,"bold"),fg=BURGUNDY,bg=BG).pack(anchor="w",padx=22,pady=(20,8))
        tk.Label(win,text="Answers are saved locally with this profile. To change a response, create a new onboarding profile or update your profile details.",font=("Segoe UI",9),fg=MUTED,bg=BG,wraplength=560,justify="left").pack(anchor="w",padx=22,pady=(0,12))
        box=tk.Text(win,wrap="word",font=("Consolas",10),bg=CARD,fg=TEXT,relief="solid",bd=1)
        box.pack(fill="both",expand=True,padx=22,pady=(0,14))
        for key,value in answers.items(): box.insert("end",f"{key.replace('_',' ').title()}: {value}\n\n")
        box.configure(state="disabled")
        self._button(win,"Close",win.destroy).pack(anchor="e",padx=22,pady=(0,18))

    def create_profile_dialog(self):
        self.start_onboarding()

    def edit_profile_dialog(self, profile_id):
        self._profile_form("Edit profile", db.get_profile(profile_id))

    def _profile_form(self, title, profile):
        win = tk.Toplevel(self); win.title(title); win.configure(bg=BG); win.resizable(False, False); win.transient(self); win.grab_set()
        win.geometry("430x430")
        tk.Label(win, text=title, font=("Segoe UI", 18, "bold"), fg=BURGUNDY, bg=BG).pack(anchor="w", padx=24, pady=(22, 6))
        tk.Label(win, text="No email or Google account needed. Use a name you are comfortable displaying.", font=("Segoe UI", 9), fg=MUTED, bg=BG, wraplength=370, justify="left").pack(anchor="w", padx=24, pady=(0, 12))
        name_var = tk.StringVar(value=profile["name"] if profile else "")
        year_var = tk.StringVar(value=str(profile["birth_year"]) if profile else str(date.today().year - 18))
        purpose_var = tk.StringVar(value=profile["purpose"] if profile else "Myself")
        tk.Label(win, text="Display name *", font=("Segoe UI", 10, "bold"), fg=TEXT, bg=BG).pack(anchor="w", padx=24, pady=(6, 4))
        name_entry = tk.Entry(win, textvariable=name_var, font=("Segoe UI", 11)); name_entry.pack(fill="x", padx=24, ipady=7)
        tk.Label(win, text="Birth year *", font=("Segoe UI", 10, "bold"), fg=TEXT, bg=BG).pack(anchor="w", padx=24, pady=(12, 4))
        year_entry = tk.Entry(win, textvariable=year_var, font=("Segoe UI", 11)); year_entry.pack(fill="x", padx=24, ipady=7)
        tk.Label(win, text="Profile purpose", font=("Segoe UI", 10, "bold"), fg=TEXT, bg=BG).pack(anchor="w", padx=24, pady=(12, 4))
        combo = ttk.Combobox(win, textvariable=purpose_var, values=["Myself", "Partner", "Mom", "Sister", "Daughter", "Friend", "Other"], state="readonly"); combo.pack(fill="x", padx=24, ipady=5)
        def save():
            name = name_var.get().strip()
            if not name: messagebox.showerror("Name required", "Enter a display name.", parent=win); return
            if len(name) > 50: messagebox.showerror("Name too long", "Use 50 characters or fewer.", parent=win); return
            if any(ord(ch) < 32 for ch in name): messagebox.showerror("Invalid name", "The name contains unsupported control characters.", parent=win); return
            try: year = int(year_var.get().strip())
            except ValueError: messagebox.showerror("Invalid year", "Birth year must be a four-digit number.", parent=win); return
            if year < 1900 or year > date.today().year: messagebox.showerror("Invalid year", f"Enter a year from 1900 to {date.today().year}.", parent=win); return
            if profile:
                db.update_profile(profile["id"], name, year, purpose_var.get()); self.profile_id = profile["id"]
            else:
                self.profile_id = db.create_profile(name, year, purpose_var.get())
            win.destroy(); self.show_page("Home")
        row = tk.Frame(win, bg=BG); row.pack(fill="x", padx=24, pady=22)
        self._button(row, "Save profile", save).pack(side="left")
        self._button(row, "Cancel", win.destroy, False).pack(side="left", padx=8)
        name_entry.focus_set()

    def switch_profile_dialog(self):
        profiles = db.list_profiles()
        if not profiles:
            self.create_profile_dialog(); return
        win = tk.Toplevel(self); win.title("Switch profile"); win.configure(bg=BG); win.geometry("420x390"); win.resizable(False, False); win.transient(self); win.grab_set()
        tk.Label(win, text="Switch profile", font=("Segoe UI", 18, "bold"), fg=BURGUNDY, bg=BG).pack(anchor="w", padx=22, pady=(20, 4))
        tk.Label(win, text="Each profile has its own separate cycle records.", font=("Segoe UI", 9), fg=MUTED, bg=BG).pack(anchor="w", padx=22, pady=(0, 12))
        listbox = tk.Listbox(win, font=("Segoe UI", 11), height=9, relief="solid", bd=1, selectbackground=PINK, selectforeground=BURGUNDY, activestyle="none")
        listbox.pack(fill="both", expand=True, padx=22, pady=4)
        for p in profiles: listbox.insert("end", f"{p['name']}  ·  {p['purpose']}  ·  {p['birth_year']}")
        current_index = next((i for i,p in enumerate(profiles) if p["id"] == self.profile_id), 0)
        listbox.selection_set(current_index); listbox.activate(current_index)
        def choose():
            sel = listbox.curselection()
            if not sel: messagebox.showinfo("Choose a profile", "Select a profile first.", parent=win); return
            self.profile_id = profiles[sel[0]]["id"]; win.destroy(); self.show_page(self.active_page if self.active_page else "Home")
        row = tk.Frame(win, bg=BG); row.pack(fill="x", padx=22, pady=14)
        self._button(row, "Switch to selected", choose).pack(side="left")
        self._button(row, "Add profile", lambda: (win.destroy(), self.create_profile_dialog()), False).pack(side="left", padx=8)

    def delete_active_profile(self):
        p = db.get_profile(self.profile_id)
        if not p: return
        if not messagebox.askyesno("Delete profile", f"Permanently delete '{p['name']}' and all its period logs, symptoms, and notes? This cannot be undone. Back up or export first if needed."):
            return
        db.delete_profile(self.profile_id)
        profiles = db.list_profiles()
        self.profile_id = profiles[0]["id"] if profiles else None
        self.show_page("Home") if self.profile_id else self.show_welcome()

    def backup_database(self):
        if not db.DB_PATH.exists(): messagebox.showerror("No database", "The database file does not exist yet."); return
        target = filedialog.asksaveasfilename(title="Save Cycora backup", defaultextension=".db", filetypes=[("SQLite database", "*.db"), ("All files", "*.*")], initialfile=f"cycora-backup-{date.today().isoformat()}.db")
        if not target: return
        try:
            with db.connect() as source:
                destination = sqlite3.connect(target)
                try: source.backup(destination)
                finally: destination.close()
            messagebox.showinfo("Backup complete", "Database backup saved. Store it somewhere private and secure.")
        except (OSError, sqlite3.Error) as exc:
            messagebox.showerror("Backup failed", f"Could not create the backup.\n{exc}")

    def export_profile(self):
        p = db.get_profile(self.profile_id)
        if not p: return
        target = filedialog.asksaveasfilename(title="Export profile data", defaultextension=".json", filetypes=[("JSON export", "*.json"), ("CSV period export", "*.csv")], initialfile=f"cycora-{p['name'].strip().replace(' ', '-')}-export")
        if not target: return
        try:
            if target.lower().endswith(".csv"):
                with open(target, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.writer(f); writer.writerow(["record_type", "date", "detail", "intensity_or_flow", "notes"])
                    for x in db.list_periods(self.profile_id): writer.writerow(["period", x["start_date"], x["end_date"] or "", x["flow"], x["notes"]])
                    for x in db.list_symptoms(self.profile_id, 100000): writer.writerow(["symptom", x["log_date"], x["symptom"], x["intensity"], x["notes"]])
            else:
                payload = {"exported_at": datetime.now().isoformat(timespec="seconds"), "profile": dict(p),
                           "period_logs": [dict(x) for x in db.list_periods(self.profile_id)],
                           "symptom_logs": [dict(x) for x in db.list_symptoms(self.profile_id, 100000)],
                           "notes": [dict(x) for x in db.list_notes(self.profile_id)],
                           "activities": [dict(x) for x in db.list_activities(self.profile_id, None, 100000)],
                           "onboarding_answers": db.get_profile_answers(self.profile_id),
                           "notice": "Contains personal health information. Keep this file private."}
                with open(target, "w", encoding="utf-8") as f: json.dump(payload, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("Export complete", "The active profile's records were exported. Keep the file private; it may contain sensitive health information.")
        except (OSError, sqlite3.Error, TypeError) as exc:
            messagebox.showerror("Export failed", f"Could not export profile data.\n{exc}")


if __name__ == "__main__":
    app = CycoraApp()
    app.mainloop()
