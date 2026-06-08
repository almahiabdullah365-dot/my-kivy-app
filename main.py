import os
import time
import pygame
import sympy as sp
import numpy as np # Used for advanced vector/matrix calculations
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.slider import Slider
from kivy.uix.relativelayout import RelativeLayout
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.animation import Animation
from kivy.storage.jsonstore import JsonStore
from kivy.graphics import Color, RoundedRectangle, Rectangle, Line
from sympy.parsing.sympy_parser import (
    parse_expr, standard_transformations, implicit_multiplication_application
)

import importlib.util

# Modular Import
try:
    from engines.physics_formulas import solve_physics
    from engines.algebra_engine import solve_algebra
except ImportError:
    def solve_physics(x): return None
    def solve_algebra(x): return None

Window.softinput_mode = "below_target"
transformations = standard_transformations + (implicit_multiplication_application,)

# UI Design Component
class ChatBubble(Label):
    def __init__(self, role, **kwargs):
        super().__init__(**kwargs)
        self.markup = True
        self.size_hint = (None, None)
        self.font_size = '19sp'
        self.padding = [20, 15]
        self.bg_color = (0.1, 0.3, 0.4, 1) if role == "Bot" else (0.2, 0.2, 0.2, 1)
        self.pos_hint = {'x': 0.05} if role == "Bot" else {'right': 0.95}
        with self.canvas.before:
            self.color_inst = Color(*self.bg_color)
            self.rect_inst = RoundedRectangle(pos=self.pos, size=self.size, radius=[15,])
        self.bind(pos=self.update_rect, size=self.update_rect)

    def update_rect(self, *args):
        self.rect_inst.pos, self.rect_inst.size = self.pos, self.size

# Drawer Menu Icon
class DrawerButton(Button):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.after:
            Color(1, 1, 1, 1)
            self.l1 = Line(width=1.5); self.l2 = Line(width=1.5); self.l3 = Line(width=1.5)
        self.bind(pos=self.update_l, size=self.update_l)

    def update_l(self, *args):
        cx, cy = self.center; w = 30
        self.l1.points = [cx-w/2, cy+10, cx+w/2, cy+10]
        self.l2.points = [cx-w/2, cy, cx+w/2, cy]
        self.l3.points = [cx-w/2, cy-10, cx+w/2, cy-10]

class MathBotApp(App):
    def build(self):
        self.store = JsonStore("chat_v9_pro.json")
        self.session_logs = []
        self.audio_active = False
        self.root = RelativeLayout()
        Window.clearcolor = (0, 0, 0, 1)

        # 1. Main UI Container
        self.main_ui = BoxLayout(orientation='vertical', padding=[10, 140, 10, 10], spacing=15)
        self.scroll = ScrollView(do_scroll_x=False)
        self.chat_box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=20)
        self.chat_box.bind(minimum_height=self.chat_box.setter('height'))
        self.scroll.add_widget(self.chat_box)
        
        # 2. Input Area (Fixed 225px)
        self.input_area = BoxLayout(size_hint_y=None, height=225, spacing=-1)
        self.user_input = TextInput(
            multiline=False, font_size='32sp', hint_text=" Type here...",
            background_color=(0.1, 0.1, 0.1, 1), foreground_color=(1, 1, 1, 1),
            cursor_color=(0, 0.7, 1, 1)
        )
        self.user_input.bind(on_text_validate=self.process_msg, focus=self.on_focus)
        
        send_btn = Button(text="SEND", size_hint_x=0.25, background_color=(0, 0.4, 0.8, 1), bold=True)
        send_btn.bind(on_press=self.process_msg)
        
        self.input_area.add_widget(self.user_input)
        self.input_area.add_widget(send_btn)
        self.main_ui.add_widget(self.scroll)
        self.main_ui.add_widget(self.input_area)
        self.root.add_widget(self.main_ui)

        # 3. Top Bar (Menu & Audio)
        self.top_bar = BoxLayout(size_hint_y=None, height=130, pos_hint={'top': 1}, padding=10, spacing=10)
        with self.top_bar.canvas.before:
            Color(0.05, 0.05, 0.05, 1)
            self.tr = Rectangle(size=self.top_bar.size, pos=self.top_bar.pos)
        self.top_bar.bind(pos=self.update_tr, size=self.update_tr)

        menu_btn = DrawerButton(size_hint_x=0.15, background_color=(0,0,0,0))
        menu_btn.bind(on_press=self.toggle_drawer)
        
        new_btn = Button(text="NEW", size_hint_x=0.2, background_color=(0.6, 0.1, 0.1, 1), bold=True)
        new_btn.bind(on_press=self.reset_chat)

        self.vol_slider = Slider(min=0, max=1, value=0.5, size_hint_x=0.4)
        self.vol_slider.bind(value=self.set_volume)
        
        self.top_bar.add_widget(menu_btn); self.top_bar.add_widget(new_btn); self.top_bar.add_widget(self.vol_slider)
        self.root.add_widget(self.top_bar)

        # 4. Drawer & History
        self.overlay = Button(background_color=(0,0,0,0.5), size_hint=(1,1))
        self.overlay.bind(on_press=self.toggle_drawer)
        
        self.drawer_width = Window.width * 0.75
        self.drawer = BoxLayout(orientation='vertical', size_hint=(None, 1), width=self.drawer_width, x=-self.drawer_width)
        with self.drawer.canvas.before:
            Color(0.12, 0.12, 0.12, 1)
            self.dr = Rectangle(size=self.drawer.size, pos=self.drawer.pos)
        self.drawer.bind(pos=self.update_dr, size=self.update_dr)
        
        self.history_list = BoxLayout(orientation='vertical', size_hint_y=None, spacing=10, padding=10)
        self.history_list.bind(minimum_height=self.history_list.setter('height'))
        h_scroll = ScrollView(); h_scroll.add_widget(self.history_list)
        
        self.drawer.add_widget(Label(text="HISTORY SESSIONS", size_hint_y=None, height=100, bold=True))
        self.drawer.add_widget(h_scroll)
        self.root.add_widget(self.drawer)
        
        self.drawer_open = False
        self.loaded_mods = {}
        self.load_external_mods()
        Clock.schedule_once(lambda dt: self.init_audio(), 1)
        return self.root

    # --- Real Logical Implementations ---
    def update_tr(self, i, v): self.tr.pos, self.tr.size = i.pos, i.size
    def update_dr(self, i, v): self.dr.pos, self.dr.size = i.pos, i.size

    def on_focus(self, inst, val):
        pad = [10, Window.height * 0.35, 10, 10] if val else [10, 140, 10, 10]
        Animation(padding=pad, duration=0.2).start(self.main_ui)

    def init_audio(self):
        try:
            pygame.mixer.init()
            if os.path.exists("music"):
                files = [f for f in os.listdir("music") if f.endswith(".mp3")]
                if files:
                    pygame.mixer.music.load(os.path.join("music", files[0]))
                    pygame.mixer.music.play(-1)
                    pygame.mixer.music.set_volume(0.5)
                    self.audio_active = True
        except: pass

    def set_volume(self, inst, val):
        if self.audio_active: pygame.mixer.music.set_volume(val)

    def toggle_drawer(self, *args):
        if not self.drawer_open:
            self.refresh_history()
            self.root.add_widget(self.overlay, index=1)
            Animation(x=0, duration=0.25).start(self.drawer)
        else:
            if self.overlay in self.root.children: self.root.remove_widget(self.overlay)
            Animation(x=-self.drawer_width, duration=0.25).start(self.drawer)
        self.drawer_open = not self.drawer_open

    def save_session(self):
        if self.session_logs:
            sid = time.strftime("%d-%b %H:%M:%S")
            self.store.put(sid, logs=self.session_logs)

    def refresh_history(self):
        self.history_list.clear_widgets()
        for sid in sorted(self.store.keys(), reverse=True):
            item_box = BoxLayout(orientation='horizontal', size_hint_y=None, height=90, spacing=5)
            
            btn = Button(text=sid, size_hint_x=0.8, background_color=(0.2, 0.2, 0.2, 1))
            btn.bind(on_press=lambda inst, s=sid: self.load_session(s))
            
            del_btn = Button(text="X", size_hint_x=0.2, background_color=(0.8, 0.2, 0.2, 1), bold=True)
            del_btn.bind(on_press=lambda inst, s=sid: self.delete_session(s))
            
            item_box.add_widget(btn)
            item_box.add_widget(del_btn)
            self.history_list.add_widget(item_box)

    def load_session(self, sid):
        self.chat_box.clear_widgets()
        self.session_logs = self.store.get(sid)['logs']
        for m in self.session_logs:
            self.add_bubble(m['role'], m['text'])
        self.toggle_drawer()

    def reset_chat(self, *args):
        self.save_session()
        self.chat_box.clear_widgets()
        self.session_logs = []

    def on_stop(self): self.save_session()

    def load_external_mods(self):
        if not os.path.exists("mods"):
            os.makedirs("mods")
        for file in os.listdir("mods"):
            if file.endswith(".py") and file != "__init__.py":
                mod_name = file[:-3]
                try:
                    spec = importlib.util.spec_from_file_location(mod_name, os.path.join("mods", file))
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    if hasattr(module, "solve_mod"):
                        self.loaded_mods[mod_name] = module.solve_mod
                except:
                    pass

    def delete_session(self, sid):
        if self.store.exists(sid):
            self.store.delete(sid)
        if self.session_logs and time.strftime("%d-%b %H:%M:%S") == sid:
            self.session_logs = []
            self.chat_box.clear_widgets()
        self.refresh_history()

    def smart_engine(self, text):
        # 0. Dynamic Mods Loader Check
        for mod_name, mod_func in self.loaded_mods.items():
            try:
                mod_res = mod_func(text)
                if mod_res: return f"🧩 [{mod_name.upper()} MOD]:\n{mod_res}"
            except: pass

        # 1. Physics Engine Check
        p_res = solve_physics(text)
        if p_res: return p_res

        # 2. Algebra Engine Check (নতুন ইঞ্জিন সংযোগ)
        a_res = solve_algebra(text)
        if a_res: return a_res

        # 3. Advanced Math Engine
        raw = text.lower().strip()
        local_dict = {s: sp.Symbol(s) for s in 'abcdefghijklmnopqrstuvwxyz'}
        
        if raw.startswith("solve"):
            try:
                eq_part = raw.replace("solve", "").strip()
                if "=" in eq_part:
                    l, r = eq_part.split("=")
                    eq = parse_expr(l, transformations=transformations, local_dict=local_dict) - \
                         parse_expr(r, transformations=transformations, local_dict=local_dict)
                else:
                    eq = parse_expr(eq_part, transformations=transformations, local_dict=local_dict)
                sol = sp.solve(eq)
                return f"🔍 Solutions:\n{sol}"
            except: return "Invalid equation format."

        # 3. NumPy Integration Example (Advanced Calc)
        if "matrix" in raw:
            try:
                # Example: Solve a simple matrix [[1,2],[3,4]] inverse
                m = np.array([[1, 2], [3, 4]])
                inv = np.linalg.inv(m)
                return f"📊 NumPy Matrix Inverse:\n{inv}"
            except: pass

        try:
            expr = parse_expr(raw.replace("^", "**"), transformations=transformations, local_dict=local_dict)
            return f"✅ Result: {sp.expand(expr)}"
        except: return "Try solving x^2-9 or physics: force m=10 a=5"

    def process_msg(self, inst):
        raw = self.user_input.text.strip()
        if not raw: return
        
        self.add_bubble("You", raw)
        self.session_logs.append({"role": "You", "text": raw})
        
        reply = self.smart_engine(raw)
        
        self.add_bubble("Bot", reply)
        self.session_logs.append({"role": "Bot", "text": reply})
        
        self.user_input.text = ""
        self.user_input.focus = True

    def add_bubble(self, role, text):
        bubble = ChatBubble(role=role, text=text)
        bubble.text_size = (Window.width * 0.75, None)
        bubble.texture_update()
        bubble.size = (bubble.texture_size[0] + 40, bubble.texture_size[1] + 30)
        container = RelativeLayout(size_hint_y=None, height=bubble.height + 20)
        container.add_widget(bubble)
        self.chat_box.add_widget(container)
        Clock.schedule_once(lambda dt: setattr(self.scroll, 'scroll_y', 0), 0.1)

if __name__ == "__main__":
    MathBotApp().run()
