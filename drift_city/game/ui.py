"""HUD and menu screens (all animated manually each frame for smooth, interruptible motion)."""
import math

from ursina import Entity, Text, Vec4, camera, color, mouse, window

from .cars import CARS, PAINTS
from .core import (ACCENT, ACCENT2, FONT_TITLE, FONT_UI, TIME_PRESETS, clamp, lerp, make_gauge_texture,
                   make_gradient_texture, make_ring_texture, make_soft_texture)

WHITE = Vec4(1, 1, 1, 1)
DIM = Vec4(0.62, 0.66, 0.74, 1)
ACC = Vec4(*ACCENT, 1)
ACC2 = Vec4(*ACCENT2, 1)
GOLD = Vec4(1.0, 0.8, 0.2, 1)
PANEL = Vec4(0.03, 0.04, 0.07, 0.78)


def rgba(c, a):
    return Vec4(c[0], c[1], c[2], a)


def ease_out(t):
    t = clamp(t, 0, 1)
    return 1 - (1 - t) ** 3


def ease_back(t):
    t = clamp(t, 0, 1)
    c = 1.9
    return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2


class _Tex:
    grad = None
    soft = None
    ring = None
    gauge = None

    @classmethod
    def load(cls):
        if cls.grad is None:
            cls.grad = make_gradient_texture()
            cls.soft = make_soft_texture(128, 1.0)
            cls.ring = make_ring_texture()
            cls.gauge = make_gauge_texture()


def label(text, parent, x=0, y=0, scale=1.0, font=FONT_UI, col=WHITE, origin=(-0.5, 0), z=-0.01):
    return Text(text, parent=parent, x=x, y=y, z=z, scale=scale, font=font, color=col, origin=origin)


def quad(parent, x=0, y=0, sx=0.1, sy=0.1, col=PANEL, texture=None, origin=(0, 0), z=0.02):
    return Entity(parent=parent, model='quad', x=x, y=y, z=z, scale=(sx, sy), color=col, texture=texture, origin=origin)


class MenuButton(Entity):
    def __init__(self, text, action, parent, x, y, width=0.46, height=0.062, sub=''):
        super().__init__(parent=parent, x=x, y=y)
        self.action = action
        self.w = width
        self.bg = Entity(parent=self, model='quad', origin=(-0.5, 0), scale=(width, height), color=Vec4(0.03, 0.04, 0.07, 0.72),
                         collider='box')
        self.fill = Entity(parent=self, model='quad', origin=(-0.5, 0), scale=(0.001, height), color=rgba(ACCENT, 0.9), z=-0.001)
        self.bar = Entity(parent=self, model='quad', origin=(-0.5, 0), scale=(0.008, height), color=ACC, z=-0.002)
        self.label = label(text, self, 0.03, 0.002, 1.35, col=DIM)
        self.label.z = -0.003
        self.sub = label(sub, self, width - 0.02, 0.0, 0.9, col=DIM, origin=(0.5, 0)) if sub else None
        if self.sub:
            self.sub.z = -0.003
        self.h = 0.0
        self.appear = 0.0
        self.selected = False

    def tick(self, dt):
        self.h += ((1.0 if self.selected else 0.0) - self.h) * min(1.0, dt * 14)
        h = self.h
        self.fill.scale_x = max(0.001, self.w * ease_out(h))
        self.label.x = 0.03 + 0.018 * h
        self.label.color = lerp(DIM, WHITE, h)
        self.bar.color = lerp(ACC, WHITE, h)
        if self.sub:
            self.sub.color = lerp(DIM, WHITE, h)

    @property
    def is_hovered(self):
        return mouse.hovered_entity == self.bg


class Screen:
    def __init__(self, game):
        _Tex.load()
        self.game = game
        self.root = Entity(parent=camera.ui, enabled=False, z=-1)
        self.t = 0.0
        self.buttons = []
        self.sel = 0
        self.ar = window.aspect_ratio

    def show(self):
        self.root.enabled = True
        self.t = 0.0
        for b in self.buttons:
            b.h = 0.0

    def hide(self):
        self.root.enabled = False

    @property
    def visible(self):
        return self.root.enabled

    def nav(self, key):
        if not self.buttons:
            return False
        if key in ('w', 'up arrow', 'gamepad dpad up'):
            self.sel = (self.sel - 1) % len(self.buttons)
            self.game.sound.play('click', 0.6)
            return True
        if key in ('s', 'down arrow', 'gamepad dpad down'):
            self.sel = (self.sel + 1) % len(self.buttons)
            self.game.sound.play('click', 0.6)
            return True
        if key in ('enter', 'gamepad a', 'space'):
            self.game.sound.play('select', 0.8)
            self.buttons[self.sel].action()
            return True
        if key == 'left mouse down':
            for i, b in enumerate(self.buttons):
                if b.is_hovered:
                    self.sel = i
                    self.game.sound.play('select', 0.8)
                    b.action()
                    return True
        return False

    def tick_buttons(self, dt, x0, stagger=0.06):
        for i, b in enumerate(self.buttons):
            if b.is_hovered and self.sel != i:
                self.sel = i
                self.game.sound.play('click', 0.4)
            b.selected = i == self.sel
            b.tick(dt)
            k = ease_out((self.t - 0.15 - i * stagger) / 0.35)
            b.x = x0 - 0.5 * (1 - k)
            b.bg.color = Vec4(0.03, 0.04, 0.07, 0.72 * k)

    def update(self, dt):
        self.t += dt

    def input(self, key):
        pass


class MainMenu(Screen):
    def __init__(self, game):
        super().__init__(game)
        ar = self.ar
        self.panel = quad(self.root, -ar / 2, 0, 1.1, 1.0, Vec4(0.0, 0.0, 0.02, 0.85), _Tex.grad, origin=(-0.5, 0))
        self.x0 = -ar / 2 + 0.09
        self.title1 = label('DRIFT', self.root, self.x0, 0.36, 5.2, FONT_TITLE)
        self.title2 = label('CITY', self.root, self.x0, 0.36, 5.2, FONT_TITLE, ACC)
        self.t2x = self.title1.width * self.title1.scale_x + 0.025
        self.line = quad(self.root, self.x0, 0.29, 0.001, 0.005, ACC, origin=(-0.5, 0), z=0.01)
        self.subtitle = label('NOCNE ULICE  •  EDYCJA 2.0', self.root, self.x0, 0.255, 1.05, col=DIM)
        items = [('WOLNA JAZDA', lambda: game.start('free'), 'zbieraj punkty'),
                 ('WYZWANIE 3:00', lambda: game.start('challenge'), 'bij rekord'),
                 ('GARAŻ', lambda: game.goto('garage'), ''),
                 ('USTAWIENIA', lambda: game.goto('settings'), ''),
                 ('STEROWANIE', lambda: game.goto('controls'), ''),
                 ('WYJŚCIE', game.quit, '')]
        for i, (t, a, s) in enumerate(items):
            self.buttons.append(MenuButton(t, a, self.root, self.x0, 0.14 - i * 0.078, sub=s))
        self.best = label('', self.root, self.x0, -0.36, 1.1, col=GOLD)
        self.hint = label('W/S wybór   •   ENTER zatwierdź   •   MYSZ klik', self.root, self.x0, -0.44, 0.9, col=DIM)
        self.car_name = label('', self.root, ar / 2 - 0.06, -0.38, 2.2, FONT_TITLE, WHITE, origin=(0.5, 0))
        self.car_paint = label('', self.root, ar / 2 - 0.06, -0.43, 1.0, col=DIM, origin=(0.5, 0))

    def show(self):
        super().show()
        g = self.game
        self.best.text = f'REKORD WOLNEJ JAZDY: {g.save["best_score"]:,}   •   WYZWANIE: {g.save.get("best_challenge", 0):,}'.replace(',', ' ')
        self.car_name.text = CARS[g.save['car']].get('name')
        self.car_paint.text = PAINTS[g.save['paint'][g.save['car']]][0].upper()

    def update(self, dt):
        super().update(dt)
        t = self.t
        k = ease_out(t / 0.6)
        self.title1.x = self.x0 - 0.3 * (1 - k)
        self.title2.x = self.x0 + self.t2x + 0.3 * (1 - k)
        a = k
        self.title1.color = Vec4(1, 1, 1, a)
        glow = 0.75 + 0.25 * math.sin(t * 2.2)
        self.title2.color = Vec4(ACCENT[0], ACCENT[1] * glow + 0.1 * (1 - glow), ACCENT[2], a)
        self.line.scale_x = max(0.001, (self.t2x + self.title2.width * self.title2.scale_x) * ease_out((t - 0.3) / 0.5))
        self.subtitle.color = Vec4(DIM[0], DIM[1], DIM[2], ease_out((t - 0.4) / 0.4))
        self.tick_buttons(dt, self.x0)
        ck = ease_out((t - 0.5) / 0.5)
        self.car_name.color = Vec4(1, 1, 1, ck)
        self.car_paint.color = Vec4(DIM[0], DIM[1], DIM[2], ck)

    def input(self, key):
        self.nav(key)


class Garage(Screen):
    def __init__(self, game):
        super().__init__(game)
        ar = self.ar
        x0 = -ar / 2 + 0.08
        self.x0 = x0
        quad(self.root, -ar / 2, 0, 0.95, 1.0, Vec4(0, 0, 0.02, 0.8), _Tex.grad, origin=(-0.5, 0))
        label('GARAŻ', self.root, x0, 0.42, 3.2, FONT_TITLE)
        quad(self.root, x0, 0.375, 0.2, 0.005, ACC, origin=(-0.5, 0))
        self.name = label('', self.root, x0, 0.28, 3.4, FONT_TITLE)
        self.idx = label('', self.root, x0, 0.33, 1.0, col=ACC)
        self.desc = label('', self.root, x0, 0.215, 1.0, col=DIM)
        self.bars = []
        for i, key in enumerate(CARS[0]['stats']):
            y = 0.12 - i * 0.07
            label(key, self.root, x0, y + 0.02, 0.95, col=DIM)
            quad(self.root, x0, y - 0.012, 0.42, 0.014, Vec4(1, 1, 1, 0.1), origin=(-0.5, 0))
            fill = quad(self.root, x0, y - 0.012, 0.001, 0.014, ACC, origin=(-0.5, 0), z=0.01)
            val = label('', self.root, x0 + 0.42, y + 0.02, 0.95, col=WHITE, origin=(0.5, 0))
            self.bars.append((key, fill, val))
        label('LAKIER', self.root, x0, -0.19, 0.95, col=DIM)
        self.paint_name = label('', self.root, x0 + 0.42, -0.19, 0.95, col=WHITE, origin=(0.5, 0))
        self.swatches = []
        for i, (_, rgb) in enumerate(PAINTS):
            sx = x0 + 0.027 + i * 0.053
            ring = Entity(parent=self.root, model='quad', texture=_Tex.ring, x=sx, y=-0.245, z=0.01, scale=0.05, color=WHITE)
            sw = Entity(parent=self.root, model='circle', x=sx, y=-0.245, scale=0.036, color=Vec4(*rgb, 1), collider='box')
            self.swatches.append((ring, sw))
        self.buttons = [MenuButton('GOTOWE', lambda: game.goto('menu'), self.root, x0, -0.35, width=0.42)]
        label('A/D samochód   •   W/S lakier   •   ENTER gotowe', self.root, x0, -0.44, 0.9, col=DIM)
        self.left = label('‹', self.root, 0.06, 0.0, 6, FONT_TITLE, Vec4(1, 1, 1, 0.5), origin=(0, 0))
        self.left.collider = 'box'
        self.right = label('›', self.root, ar / 2 - 0.08, 0.0, 6, FONT_TITLE, Vec4(1, 1, 1, 0.5), origin=(0, 0))
        self.right.collider = 'box'
        self.anim = 0.0

    def show(self):
        super().show()
        self.refresh()

    def refresh(self):
        g = self.game
        ci = g.save['car']
        spec = CARS[ci]
        self.name.text = spec['name']
        self.idx.text = f'SAMOCHÓD {ci + 1}/{len(CARS)}'
        self.desc.text = spec['desc']
        self.paint_name.text = PAINTS[g.save['paint'][ci]][0].upper()
        self.anim = 0.0

    def update(self, dt):
        super().update(dt)
        self.anim += dt
        g = self.game
        spec = CARS[g.save['car']]
        k = ease_out(self.anim / 0.5)
        self.name.x = self.x0 - 0.08 * (1 - k)
        self.name.color = Vec4(1, 1, 1, k)
        for key, fill, val in self.bars:
            v = spec['stats'][key]
            cur = fill.scale_x / 0.42
            nv = cur + (v - cur) * min(1.0, dt * 6)
            fill.scale_x = max(0.001, 0.42 * nv)
            fill.color = lerp(ACC2, ACC, v)
            val.text = str(int(round(nv * 100)))
        pi = g.save['paint'][g.save['car']]
        for i, (ring, sw) in enumerate(self.swatches):
            target = 1.35 if i == pi else 1.0
            ring.scale = lerp(ring.scale_x, 0.05 * target, min(1, dt * 12))
            ring.color = WHITE if i == pi else Vec4(1, 1, 1, 0.25)
        pulse = 0.5 + 0.5 * math.sin(self.t * 4)
        self.left.color = Vec4(1, 1, 1, 0.35 + 0.35 * pulse)
        self.right.color = Vec4(1, 1, 1, 0.35 + 0.35 * pulse)
        self.tick_buttons(dt, self.x0, 0)

    def input(self, key):
        g = self.game
        if key in ('left arrow', 'a', 'gamepad dpad left'):
            g.change_car(-1)
            self.refresh()
        elif key in ('right arrow', 'd', 'gamepad dpad right'):
            g.change_car(1)
            self.refresh()
        elif key in ('up arrow', 'w', 'gamepad dpad up'):
            g.change_paint(-1)
            self.refresh()
        elif key in ('down arrow', 's', 'gamepad dpad down'):
            g.change_paint(1)
            self.refresh()
        elif key in ('escape', 'backspace', 'gamepad b'):
            g.goto('menu')
        elif key == 'left mouse down':
            for i, (_, sw) in enumerate(self.swatches):
                if mouse.hovered_entity == sw:
                    g.change_paint(i - g.save['paint'][g.save['car']])
                    self.refresh()
                    return
            if mouse.hovered_entity == self.left:
                g.change_car(-1)
                self.refresh()
                return
            if mouse.hovered_entity == self.right:
                g.change_car(1)
                self.refresh()
                return
            self.nav(key)
        elif key in ('enter', 'gamepad a'):
            self.nav(key)


SETTINGS = [
    ('time', 'PORA DNIA', ['day', 'sunset', 'night'], lambda v: TIME_PRESETS[v]['label']),
    ('gearbox', 'SKRZYNIA BIEGÓW', ['auto', 'manual'], lambda v: 'AUTOMAT' if v == 'auto' else 'MANUAL (Q/E)'),
    ('quality', 'GRAFIKA', ['high', 'medium', 'low'], lambda v: {'high': 'WYSOKA', 'medium': 'ŚREDNIA', 'low': 'NISKA'}[v]),
    ('camera', 'KAMERA', [0, 1, 2, 3], lambda v: ['POŚCIGOWA', 'DALEKA', 'MASKA', 'KINOWA'][v]),
    ('volume', 'GŁOŚNOŚĆ', [0.0, 0.2, 0.4, 0.6, 0.8, 1.0], lambda v: f'{int(v * 100)}%'),
]


class Settings(Screen):
    def __init__(self, game):
        super().__init__(game)
        ar = self.ar
        x0 = -ar / 2 + 0.08
        self.x0 = x0
        quad(self.root, -ar / 2, 0, 1.2, 1.0, Vec4(0, 0, 0.02, 0.85), _Tex.grad, origin=(-0.5, 0))
        label('USTAWIENIA', self.root, x0, 0.42, 3.2, FONT_TITLE)
        quad(self.root, x0, 0.375, 0.2, 0.005, ACC, origin=(-0.5, 0))
        self.rows = []
        for i, (key, name, opts, fmt) in enumerate(SETTINGS):
            b = MenuButton(name, lambda k=key: self.cycle(k, 1), self.root, x0, 0.27 - i * 0.078, width=0.62, sub=' ')
            self.buttons.append(b)
            self.rows.append((key, opts, fmt, b))
        self.buttons.append(MenuButton('WRÓĆ', self.back, self.root, x0, 0.27 - len(SETTINGS) * 0.078 - 0.03, width=0.62))
        label('W/S wybór   •   A/D zmiana   •   ESC powrót', self.root, x0, -0.44, 0.9, col=DIM)
        self.return_to = 'menu'

    def back(self):
        self.game.goto(self.return_to)

    def cycle(self, key, d):
        for k, opts, fmt, b in self.rows:
            if k == key:
                cur = self.game.save[key]
                i = opts.index(cur) if cur in opts else 0
                self.game.apply_setting(key, opts[(i + d) % len(opts)])
        self.refresh()

    def refresh(self):
        for k, opts, fmt, b in self.rows:
            b.sub.text = '‹  ' + fmt(self.game.save[k]) + '  ›'

    def show(self):
        super().show()
        self.refresh()

    def update(self, dt):
        super().update(dt)
        self.tick_buttons(dt, self.x0, 0.04)

    def input(self, key):
        if key in ('left arrow', 'a', 'right arrow', 'd', 'gamepad dpad left', 'gamepad dpad right') and self.sel < len(self.rows):
            self.game.sound.play('click', 0.6)
            self.cycle(self.rows[self.sel][0], -1 if key in ('left arrow', 'a', 'gamepad dpad left') else 1)
        elif key in ('escape', 'backspace', 'gamepad b'):
            self.back()
        else:
            self.nav(key)


CONTROLS = [
    ('W', 'Gaz'), ('S', 'Hamulec / wsteczny'), ('A / D', 'Skręt'), ('SPACJA', 'Ręczny — inicjuj drift'),
    ('SHIFT', 'Nitro (ładuje się w drifcie)'), ('Q / E', 'Bieg w dół / w górę (manual)'), ('C', 'Zmień kamerę'),
    ('L', 'Światła'), ('T', 'Pora dnia'), ('R', 'Reset na drogę'), ('TAB', 'Ukryj HUD'), ('ESC', 'Pauza'),
]


class Controls(Screen):
    def __init__(self, game):
        super().__init__(game)
        ar = self.ar
        x0 = -ar / 2 + 0.08
        self.x0 = x0
        quad(self.root, -ar / 2, 0, 1.3, 1.0, Vec4(0, 0, 0.02, 0.86), _Tex.grad, origin=(-0.5, 0))
        label('STEROWANIE', self.root, x0, 0.42, 3.2, FONT_TITLE)
        quad(self.root, x0, 0.375, 0.2, 0.005, ACC, origin=(-0.5, 0))
        for i, (k, v) in enumerate(CONTROLS):
            y = 0.3 - i * 0.052
            quad(self.root, x0, y, 0.2, 0.042, Vec4(1, 1, 1, 0.07), origin=(-0.5, 0), z=0.01)
            label(k, self.root, x0 + 0.1, y, 1.05, col=ACC2, origin=(0, 0))
            label(v, self.root, x0 + 0.23, y, 1.05, col=WHITE)
        label('Strzałki działają jak WASD.   PAD: gałka skręt • triggery gaz/hamulec • A ręczny • X nitro', self.root, x0, -0.34, 0.95, col=DIM)
        label('Drift = ręczny lub gaz w zakręcie. Kontruj, żeby utrzymać kąt!', self.root, x0, -0.39, 0.95, col=GOLD)
        self.buttons = [MenuButton('WRÓĆ', lambda: game.goto('menu'), self.root, x0, -0.455, width=0.3)]

    def update(self, dt):
        super().update(dt)
        self.tick_buttons(dt, self.x0)

    def input(self, key):
        if key in ('escape', 'backspace', 'gamepad b'):
            self.game.goto('menu')
        else:
            self.nav(key)


class Pause(Screen):
    def __init__(self, game):
        super().__init__(game)
        ar = self.ar
        self.dim = quad(self.root, 0, 0, ar * 1.1, 1.1, Vec4(0, 0, 0.02, 0.55), z=0.05)
        self.x0 = -0.2
        label('PAUZA', self.root, 0, 0.25, 4, FONT_TITLE, origin=(0, 0))
        items = [('WZNÓW', game.resume), ('RESTART', game.restart), ('USTAWIENIA', lambda: game.goto('settings', from_pause=True)),
                 ('MENU GŁÓWNE', lambda: game.goto('menu'))]
        for i, (t, a) in enumerate(items):
            self.buttons.append(MenuButton(t, a, self.root, self.x0, 0.1 - i * 0.078, width=0.4))

    def update(self, dt):
        super().update(dt)
        self.tick_buttons(dt, self.x0, 0.03)

    def input(self, key):
        if key in ('escape', 'gamepad start', 'gamepad b'):
            self.game.resume()
        else:
            self.nav(key)


class Results(Screen):
    def __init__(self, game):
        super().__init__(game)
        ar = self.ar
        quad(self.root, 0, 0, ar * 1.1, 1.1, Vec4(0, 0, 0.02, 0.6), z=0.05)
        quad(self.root, 0, 0.02, 0.8, 0.62, PANEL, z=0.03)
        quad(self.root, 0, 0.33, 0.8, 0.006, ACC)
        label('KONIEC CZASU', self.root, 0, 0.26, 3, FONT_TITLE, origin=(0, 0))
        self.score = label('', self.root, 0, 0.14, 4.5, FONT_TITLE, GOLD, origin=(0, 0))
        self.info = label('', self.root, 0, 0.05, 1.2, col=WHITE, origin=(0, 0))
        self.record = label('', self.root, 0, -0.01, 1.6, FONT_TITLE, ACC, origin=(0, 0))
        self.x0 = -0.2
        self.buttons = [MenuButton('JESZCZE RAZ', lambda: game.start('challenge'), self.root, self.x0, -0.1, width=0.4),
                        MenuButton('MENU GŁÓWNE', lambda: game.goto('menu'), self.root, self.x0, -0.18, width=0.4)]
        self.final = 0

    def set(self, score, best_drift, record):
        self.final = score
        self.info.text = f'Najlepszy drift: {best_drift:,}'.replace(',', ' ')
        self.record.text = 'NOWY REKORD!' if record else ''

    def update(self, dt):
        super().update(dt)
        k = ease_out(self.t / 1.4)
        self.score.text = f'{int(self.final * k):,}'.replace(',', ' ')
        self.record.scale = 1.6 + 0.15 * math.sin(self.t * 6)
        self.tick_buttons(dt, self.x0, 0.05)

    def input(self, key):
        self.nav(key)


# ---------------------------------------------------------------------------
#   HUD
# ---------------------------------------------------------------------------

class Popup:
    def __init__(self, parent):
        self.text = label('', parent, 0, 0, 2.5, FONT_TITLE, WHITE, origin=(0, 0), z=-0.05)
        self.sub = label('', parent, 0, 0, 1.3, FONT_UI, WHITE, origin=(0, 0), z=-0.05)
        self.t = 99.0
        self.dur = 1.0
        self.col = WHITE
        self.y = 0.0
        self.size = 2.5

    def fire(self, text, sub, col, y, size, dur):
        self.text.text, self.sub.text = text, sub
        self.col, self.y, self.size, self.dur, self.t = col, y, size, dur, 0.0

    def tick(self, dt):
        self.t += dt
        if self.t > self.dur:
            self.text.enabled = self.sub.enabled = False
            return
        self.text.enabled = self.sub.enabled = True
        t = self.t
        s = ease_back(t / 0.28) * self.size
        fade = clamp((self.dur - t) / 0.4, 0, 1)
        self.text.scale = s
        self.text.y = self.y + t * 0.03
        self.text.color = Vec4(self.col[0], self.col[1], self.col[2], fade)
        self.sub.scale = 1.3 * ease_out(t / 0.3)
        self.sub.y = self.y - 0.05 + t * 0.03
        self.sub.color = Vec4(1, 1, 1, fade * 0.9)


class HUD:
    def __init__(self, game):
        _Tex.load()
        self.game = game
        ar = window.aspect_ratio
        self.ar = ar
        self.root = Entity(parent=camera.ui, enabled=False)
        r = self.root

        # tachometer
        gx, gy, gs = ar / 2 - 0.21, -0.29, 0.36
        self.gauge = Entity(parent=r, model='quad', texture=_Tex.gauge, x=gx, y=gy, z=0.02, scale=gs)
        self.needle = Entity(parent=r, model='quad', x=gx, y=gy, z=0.0, scale=(0.008, gs * 0.4), origin=(0, -0.5),
                             color=ACC)
        Entity(parent=r, model='circle', x=gx, y=gy, z=-0.005, scale=0.03, color=Vec4(0.12, 0.13, 0.16, 1))
        self.speed = label('0', r, gx, gy - 0.075, 3.4, FONT_TITLE, WHITE, origin=(0, 0))
        label('KM/H', r, gx, gy - 0.12, 0.9, col=DIM, origin=(0, 0))
        self.gear_bg = quad(r, gx, gy + 0.075, 0.05, 0.05, Vec4(1, 1, 1, 0.08), z=0.01)
        self.gear = label('1', r, gx, gy + 0.075, 2.2, FONT_TITLE, WHITE, origin=(0, 0))
        self.gear_pop = 0.0
        # nitro
        nx = gx - gs / 2 - 0.035
        label('NOS', r, nx, gy - 0.165, 0.85, col=ACC2, origin=(0, 0))
        quad(r, nx, gy - 0.15, 0.022, 0.26, Vec4(1, 1, 1, 0.1), origin=(0, -0.5))
        self.nos = quad(r, nx, gy - 0.15, 0.016, 0.26, ACC2, origin=(0, -0.5), z=0.01)

        # score panel
        x0 = -ar / 2 + 0.04
        quad(r, -ar / 2, 0.41, 0.62, 0.17, Vec4(0, 0, 0.02, 0.6), _Tex.grad, origin=(-0.5, 0))
        self.score_lbl = label('WYNIK', r, x0, 0.465, 0.9, col=DIM)
        self.score = label('0', r, x0, 0.42, 2.6, FONT_TITLE, WHITE)
        self.best = label('', r, x0, 0.365, 0.95, col=GOLD)
        self.timer = label('', r, 0, 0.455, 2.6, FONT_TITLE, WHITE, origin=(0, 0))
        self.shown_score = 0.0

        # drift panel
        self.drift_root = Entity(parent=r, y=0.3)
        d = self.drift_root
        self.drift_pts = label('0', d, 0, 0.0, 3.4, FONT_TITLE, WHITE, origin=(0, 0))
        self.drift_lbl = label('DRIFT', d, 0, 0.065, 1.1, col=ACC, origin=(0, 0))
        self.mult_ring = Entity(parent=d, model='quad', texture=_Tex.ring, x=0.2, y=0.0, z=0.01, scale=0.075, color=ACC)
        self.mult = label('x1', d, 0.2, 0.0, 1.5, FONT_TITLE, WHITE, origin=(0, 0))
        quad(d, 0, -0.055, 0.3, 0.008, Vec4(1, 1, 1, 0.12))
        self.chain = quad(d, 0, -0.055, 0.3, 0.008, ACC, z=0.01)
        self.angle = label('', d, 0, -0.09, 1.1, col=DIM, origin=(0, 0))
        self.near = label('BLISKO! x1.5', d, 0, -0.13, 1.2, FONT_TITLE, ACC2, origin=(0, 0))
        self.drift_alpha = 0.0
        self.pop = 0.0
        self.last_pts = 0

        # overlays
        self.flash = quad(r, 0, 0, ar * 1.1, 1.1, Vec4(1, 0.1, 0.05, 0), _Tex.soft, z=0.04)
        self.flash.scale = (ar * 2.2, 2.2)
        self.flash_t = 0.0
        self.popups = [Popup(r) for _ in range(4)]
        self.pi = 0
        self.hint = label('C kamera   L światła   T pora dnia   R reset   ESC pauza', r, -ar / 2 + 0.04, -0.47, 0.85, col=DIM)
        self.cam_lbl = label('', r, 0, -0.42, 1.2, col=WHITE, origin=(0, 0))
        self.cam_t = 99.0
        self.full = True

    def show(self):
        self.root.enabled = True

    def hide(self):
        self.root.enabled = False

    def toggle(self):
        self.full = not self.full
        for e in (self.gauge, self.needle, self.hint):
            e.enabled = self.full

    def popup(self, text, sub='', col=WHITE, y=0.08, size=2.4, dur=1.6):
        p = self.popups[self.pi]
        self.pi = (self.pi + 1) % len(self.popups)
        p.fire(text, sub, col, y, size, dur)

    def crash_flash(self, strength):
        self.flash_t = max(self.flash_t, clamp(strength / 25, 0.2, 0.6))

    def camera_name(self, name):
        self.cam_lbl.text = 'KAMERA: ' + name
        self.cam_t = 0.0

    def gear_changed(self):
        self.gear_pop = 1.0

    def update(self, dt, car, time_left=None):
        kmh = int(car.speed * 3.6)
        self.speed.text = str(kmh)
        f = clamp((car.rpm - 0) / 8000, 0, 1)
        self.needle.rotation_z = -135 + 270 * f
        red = car.rpm > 7000
        self.needle.color = Vec4(1, 0.15, 0.1, 1) if red else ACC
        self.gear.text = 'R' if car.vl < -0.5 else str(car.gear)
        self.gear_pop = max(0.0, self.gear_pop - dt * 4)
        self.gear.scale = 2.2 + 1.2 * self.gear_pop
        self.gear.color = lerp(WHITE, ACC, self.gear_pop)
        self.nos.scale_y = max(0.001, 0.26 * car.nitro / 100)
        self.nos.color = Vec4(0.6, 0.9, 1, 1) if car.nitro_on else (ACC2 if car.nitro > 15 else Vec4(1, 0.2, 0.2, 1))

        self.shown_score += (car.score - self.shown_score) * min(1.0, dt * 6)
        self.score.text = f'{int(round(self.shown_score)):,}'.replace(',', ' ')
        g = self.game
        best = g.save['best_score'] if g.mode == 'free' else g.save.get('best_challenge', 0)
        self.best.text = f'REKORD  {max(best, car.score):,}'.replace(',', ' ')
        if time_left is not None:
            s = max(0, int(math.ceil(time_left)))
            self.timer.text = f'{s // 60}:{s % 60:02d}'
            self.timer.color = Vec4(1, 0.25, 0.2, 1) if time_left < 10 and (time_left % 1) > 0.5 else WHITE
        else:
            self.timer.text = ''

        active = car.drift_pts > 0 or (car.chain > 0 and car.mult > 1)
        self.drift_alpha += ((1.0 if active else 0.0) - self.drift_alpha) * min(1, dt * 8)
        a = self.drift_alpha
        self.drift_root.enabled = a > 0.02
        if self.drift_root.enabled:
            pts = int(car.drift_pts)
            if pts // 100 != self.last_pts // 100:
                self.pop = 1.0
            self.last_pts = pts
            self.pop = max(0.0, self.pop - dt * 5)
            self.drift_pts.text = f'{pts:,}'.replace(',', ' ') if pts else ''
            self.drift_pts.scale = 3.4 + 0.5 * self.pop
            self.drift_pts.color = Vec4(1, 1, 1, a)
            self.drift_lbl.color = Vec4(ACCENT[0], ACCENT[1], ACCENT[2], a)
            self.mult.text = f'x{car.mult}'
            self.mult.enabled = self.mult_ring.enabled = car.mult > 1
            self.mult.color = Vec4(1, 1, 1, a)
            self.mult_ring.color = Vec4(ACCENT[0], ACCENT[1], ACCENT[2], a)
            self.mult_ring.rotation_z += dt * 90
            self.chain.scale_x = max(0.001, 0.3 * clamp(car.chain / 3.2, 0, 1))
            self.chain.color = Vec4(ACCENT[0], ACCENT[1], ACCENT[2], a)
            self.angle.text = f'{int(abs(car.slip))}°' if car.drifting else ''
            self.angle.color = Vec4(DIM[0], DIM[1], DIM[2], a)
            self.near.enabled = car.near and car.drifting
            self.near.scale = 1.2 + 0.1 * math.sin(g.clock * 20)

        self.flash_t = max(0.0, self.flash_t - dt * 1.5)
        self.flash.color = Vec4(1, 0.1, 0.05, self.flash_t)
        for p in self.popups:
            p.tick(dt)
        self.cam_t += dt
        self.cam_lbl.enabled = self.cam_t < 1.5
        self.cam_lbl.color = Vec4(1, 1, 1, clamp(1.5 - self.cam_t, 0, 1))
