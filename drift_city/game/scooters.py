"""Electric scooter definitions, procedural 3D scooter models and the blocky rider."""
import math
import random

from panda3d.core import BitMask32, Point3
from PIL import Image, ImageDraw, ImageFont
from ursina import Entity, Text, Vec3, Vec4, color

from .core import FONT_TITLE, FONT_UI_FILE, MeshBuilder, _to_texture, make_soft_texture, world_shader

SHADOW_CAM = BitMask32.bit(1)

PAINTS = [
    ('Pomarańcz KuKirin', (1.0, 0.45, 0.02)),
    ('Czerwień', (0.95, 0.08, 0.06)),
    ('Cyjan neon', (0.1, 0.85, 1.0)),
    ('Limonka', (0.55, 1.0, 0.1)),
    ('Róż', (1.0, 0.25, 0.65)),
    ('Żółć', (1.0, 0.82, 0.05)),
    ('Fiolet', (0.6, 0.25, 1.0)),
    ('Biel', (0.95, 0.95, 0.95)),
]

SCOOTERS = [
    dict(
        name='KUKIRIN G2', brand='KuKirin G2', badge='G2', dash='KuKirin',
        desc='Terenowa bestia z podwójnym zawieszeniem. Idealna do wheelie.',
        stats={'MOC': 0.7, 'PRZYCZEPNOŚĆ': 0.7, 'WHEELIE': 0.95, 'V-MAX': 0.72},
        vmax_kmh=80, accel=6.8, grip=8.5, drift_grip=1.7, drift_yaw=105.0, steer=32.0, power_slide=0.35,
        frame=(0.36, 0.42, 0.5), dark=(0.05, 0.05, 0.07), stem=(0.03, 0.03, 0.04), rim=(0.86, 0.88, 0.9),
        paint=0, R=0.16, deck_w=0.23,
    ),
    dict(
        name='AUSOM GALLOP', brand='AUSOM GALLOP', badge='AUSOM', dash='AUSOM',
        desc='Dwa silniki, twarde zawieszenie i brutalne przyspieszenie.',
        stats={'MOC': 0.86, 'PRZYCZEPNOŚĆ': 0.8, 'WHEELIE': 0.8, 'V-MAX': 0.85},
        vmax_kmh=88, accel=7.8, grip=9.5, drift_grip=1.9, drift_yaw=100.0, steer=30.0, power_slide=0.3,
        frame=(0.07, 0.07, 0.08), dark=(0.03, 0.03, 0.035), stem=(0.05, 0.05, 0.06), rim=(0.2, 0.2, 0.22),
        paint=1, R=0.17, deck_w=0.25,
    ),
    dict(
        name='KAMIKAZE X', brand='KAMIKAZE X', badge='X', dash='KAMIKAZE',
        desc='Najszybsza hulajnoga w mieście. 100 km/h i zero litości.',
        stats={'MOC': 1.0, 'PRZYCZEPNOŚĆ': 0.72, 'WHEELIE': 0.85, 'V-MAX': 1.0},
        vmax_kmh=100, accel=8.8, grip=9.0, drift_grip=1.6, drift_yaw=110.0, steer=29.0, power_slide=0.4,
        frame=(0.9, 0.9, 0.92), dark=(0.06, 0.06, 0.07), stem=(0.08, 0.08, 0.09), rim=(0.08, 0.08, 0.09),
        paint=2, R=0.165, deck_w=0.24,
    ),
]

REAR_Z, FRONT_Z, STEER_Z = -0.5, 0.5, 0.42
DECK_Y0, DECK_Y1 = 0.17, 0.34


# ---------------------------------------------------------------------------
#   geometry helpers
# ---------------------------------------------------------------------------

def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(v):
    l = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2) or 1.0
    return (v[0] / l, v[1] / l, v[2] / l)


def _axes(p0, p1, up):
    f = _norm(_sub(p1, p0))
    s = _cross(up, f)
    if abs(s[0]) + abs(s[1]) + abs(s[2]) < 1e-6:
        s = (1.0, 0.0, 0.0)
    s = _norm(s)
    u = _cross(f, s)
    return f, s, u


def _p(base, s, a, u, b, f=None, c=0.0):
    x = base[0] + s[0] * a + u[0] * b
    y = base[1] + s[1] * a + u[1] * b
    z = base[2] + s[2] * a + u[2] * b
    if f:
        x, y, z = x + f[0] * c, y + f[1] * c, z + f[2] * c
    return (x, y, z)


def beam(mb, p0, p1, w, h, col, up=(0, 1, 0)):
    f, s, u = _axes(p0, p1, up)
    hw, hh = w / 2, h / 2
    neg = lambda v: (-v[0], -v[1], -v[2])
    for sa, n in ((hw, s), (-hw, neg(s))):
        mb.quad(_p(p0, s, sa, u, -hh), _p(p1, s, sa, u, -hh), _p(p1, s, sa, u, hh), _p(p0, s, sa, u, hh), col, n)
    for ub, n in ((hh, u), (-hh, neg(u))):
        mb.quad(_p(p0, s, -hw, u, ub), _p(p1, s, -hw, u, ub), _p(p1, s, hw, u, ub), _p(p0, s, hw, u, ub), col, n)
    for pp, n in ((p0, neg(f)), (p1, f)):
        mb.quad(_p(pp, s, -hw, u, -hh), _p(pp, s, hw, u, -hh), _p(pp, s, hw, u, hh), _p(pp, s, -hw, u, hh), col, n)
    return f, s, u


def squares_on(mb, p0, p1, w, up, side, pattern, sq, col):
    """Pixel squares on the side face (+s if side>0) of a beam. pattern: [(t along 0..1, offset across)]"""
    f, s, u = _axes(p0, p1, up)
    L = math.dist(p0, p1)
    n = s if side > 0 else (-s[0], -s[1], -s[2])
    off = side * (w / 2 + 0.002)
    for t, o in pattern:
        c = _p(p0, s, off, u, o, f, t * L)
        h = sq / 2
        mb.quad(_p(c, f, -h, u, -h), _p(c, f, h, u, -h), _p(c, f, h, u, h), _p(c, f, -h, u, h), col, n)


def coil(mb, a, b, radius, turns, col, wire=0.011):
    f, s, u = _axes(a, b, (1, 0, 0) if abs(b[1] - a[1]) > abs(b[2] - a[2]) else (0, 1, 0))
    L = math.dist(a, b)
    n = int(turns * 10)
    prev = None
    for k in range(n + 1):
        th = math.tau * turns * k / n
        p = _p(a, s, math.cos(th) * radius, u, math.sin(th) * radius, f, L * k / n)
        if prev:
            beam(mb, prev, p, wire, wire, col)
        prev = p
    beam(mb, a, b, 0.018, 0.018, (0.55, 0.56, 0.6, 0.8))


def arc_strip(mb, center, r, a0, a1, width, col, segs=10):
    """Fender strip around the X axis (angles in degrees, 0 = +z, 90 = +y)."""
    cy, cz = center[1], center[2]
    pts = []
    for k in range(segs + 1):
        a = math.radians(a0 + (a1 - a0) * k / segs)
        pts.append((math.sin(a), math.cos(a)))
    for (s0, c0), (s1, c1) in zip(pts, pts[1:]):
        n = ((s0 + s1) / 2, (c0 + c1) / 2)
        mb.quad((-width / 2, cy + s0 * r, cz + c0 * r), (width / 2, cy + s0 * r, cz + c0 * r),
                (width / 2, cy + s1 * r, cz + c1 * r), (-width / 2, cy + s1 * r, cz + c1 * r), col, (0, n[0], n[1]))


def annulus(mb, x, r0, r1, col, nx, segs=18):
    for k in range(segs):
        a0, a1 = math.tau * k / segs, math.tau * (k + 1) / segs
        mb.quad((x, math.cos(a0) * r0, math.sin(a0) * r0), (x, math.cos(a1) * r0, math.sin(a1) * r0),
                (x, math.cos(a1) * r1, math.sin(a1) * r1), (x, math.cos(a0) * r1, math.sin(a0) * r1), col, (nx, 0, 0))


def shift_z(mb, dz):
    for i in range(2, len(mb.v), 3):
        mb.v[i] -= dz


def build_wheel(R, w, rim_col, disc_side=-1):
    mb = MeshBuilder()
    rubber = (0.045, 0.045, 0.05, 0.08)
    mb.cyl_x(0, 0, 0, R * 0.9, w, rubber, segs=22)
    blocks = 26
    for k in range(blocks):
        a = math.tau * k / blocks
        ca, sa = math.cos(a), math.sin(a)
        xo = (w * 0.22) if k % 2 else (-w * 0.22)
        p0 = (xo, ca * R * 0.88, sa * R * 0.88)
        p1 = (xo, ca * R, sa * R)
        beam(mb, p0, p1, 0.034, w * 0.46, rubber, up=(1, 0, 0))
    rim = (rim_col[0], rim_col[1], rim_col[2], 0.7)
    for side in (-1, 1):
        x = side * (w / 2 + 0.002)
        annulus(mb, x, R * 0.18, R * 0.62, rim, side)
        annulus(mb, x + side * 0.001, R * 0.55, R * 0.62, (rim_col[0] * 0.8, rim_col[1] * 0.8, rim_col[2] * 0.8, 0.9), side)
    xd = disc_side * (w / 2 + 0.014)
    annulus(mb, xd, R * 0.36, R * 0.56, (0.78, 0.79, 0.82, 1.0), disc_side, segs=24)
    for ring, n in ((0.42, 12), (0.5, 16)):
        for k in range(n):
            a = math.tau * (k + ring) / n
            y, z = math.cos(a) * R * ring, math.sin(a) * R * ring
            h = 0.0045
            mb.quad((xd + disc_side * 0.001, y - h, z - h), (xd + disc_side * 0.001, y + h, z - h),
                    (xd + disc_side * 0.001, y + h, z + h), (xd + disc_side * 0.001, y - h, z + h), (0.1, 0.1, 0.1, 0.2), (disc_side, 0, 0))
    for k in range(5):
        a = math.tau * k / 5
        beam(mb, (xd, math.cos(a) * R * 0.1, math.sin(a) * R * 0.1), (xd, math.cos(a) * R * 0.37, math.sin(a) * R * 0.37),
             0.018, 0.006, (0.25, 0.25, 0.27, 0.6), up=(1, 0, 0))
    mb.cyl_x(0, 0, 0, R * 0.14, w + 0.05, (0.12, 0.12, 0.13, 0.6), segs=10)
    return mb.build()


def make_decal_texture(spec, accent):
    """512x128: top half = stem lettering (black bg), bottom-left = side badge (accent bg)."""
    img = Image.new('RGBA', (512, 128), (8, 8, 10, 255))
    d = ImageDraw.Draw(img)
    a255 = tuple(int(c * 255) for c in accent) + (255,)
    try:
        f_stem = ImageFont.truetype(FONT_UI_FILE, 46)
        f_badge = ImageFont.truetype(FONT_UI_FILE, 50)
    except OSError:
        f_stem = f_badge = ImageFont.load_default()
    d.text((18, 4), spec['brand'], font=f_stem, fill=a255)
    tw = d.textlength(spec['brand'], font=f_stem)
    rnd = random.Random(4)
    x = 30 + tw
    while x < 500:
        for _ in range(2):
            if rnd.random() < max(0.15, 1 - (x - tw) / 300):
                y = rnd.choice((10, 22, 34, 46))
                d.rectangle([x, y, x + 9, y + 9], fill=a255)
        x += 14
    d.rectangle([0, 64, 255, 127], fill=a255)
    bw = d.textlength(spec['badge'], font=f_badge)
    d.text((248 - bw, 66), spec['badge'], font=f_badge, fill=(15, 15, 18, 255))
    return _to_texture(img)


STEM_UV = (0.0, 0.5, 1.0, 1.0)
BADGE_UV = (0.0, 0.0, 0.5, 0.5)


# ---------------------------------------------------------------------------
#   rider
# ---------------------------------------------------------------------------

SKIN = (0.96, 0.8, 0.62, 0.1)
HOODIE = (0.05, 0.05, 0.06, 0.15)
PANTS = (0.12, 0.12, 0.15, 0.1)
SHOE = (0.93, 0.93, 0.95, 0.3)


def _limb_mesh(w, d, main_col, end_col, split=0.82):
    mb = MeshBuilder()
    mb.box(0, 0, split / 2, w, d, split, main_col)
    mb.box(0, 0, split + (1 - split) / 2, w * 1.02, d * 1.02, 1 - split, end_col)
    return mb.build()


class Rider(Entity):
    """Blocky rider. Legs/arms are pivots whose +Z points at their targets (hands on grips, feet on deck)."""

    HIP = 0.78

    def __init__(self, parent, grips, feet):
        super().__init__(parent=parent, shader=world_shader)
        self.grips, self.feet = grips, feet
        self.legs = []
        for side, shoe_col in ((-1, SHOE), (1, SHOE)):
            p = Entity(parent=self, position=(side * 0.1, self.HIP, 0))
            Entity(parent=p, model=_limb_mesh(0.19, 0.21, PANTS, shoe_col, 0.84), shader=world_shader, double_sided=True)
            self.legs.append(p)
        self.torso = Entity(parent=self, position=(0, self.HIP, 0))
        tb = MeshBuilder()
        tb.box(0, 0.3, 0, 0.42, 0.6, 0.22, HOODIE)
        tb.box(0, 0.38, 0.112, 0.2, 0.2, 0.004, (0.92, 0.92, 0.94, 0.1))
        tb.box(0, 0.38, 0.115, 0.1, 0.1, 0.004, HOODIE)
        tb.box(0, 0.55, -0.1, 0.36, 0.12, 0.06, HOODIE)
        self.torso_mesh = Entity(parent=self.torso, model=tb.build(), shader=world_shader, double_sided=True)
        self.head = Entity(parent=self.torso, position=(0, 0.6, 0))
        hb = MeshBuilder()
        hb.box(0, 0.17, 0, 0.3, 0.3, 0.3, SKIN)
        for s in (-1, 1):
            hb.box(s * 0.065, 0.19, 0.151, 0.04, 0.06, 0.004, (0.02, 0.02, 0.02, 0.4))
        hb.box(0, 0.1, 0.151, 0.1, 0.018, 0.004, (0.25, 0.08, 0.06, 0.2))
        hb.box(0, 0.33, -0.01, 0.32, 0.06, 0.33, (0.06, 0.05, 0.05, 0.1))
        hb.box(0, 0.27, 0.0, 0.315, 0.05, 0.315, (0.12, 0.85, 1.0, 0.9))
        hb.box(0, 0.27, 0.16, 0.24, 0.07, 0.03, (0.1, 0.9, 1.0, 1.0))
        Entity(parent=self.head, model=hb.build(), shader=world_shader, double_sided=True)
        self.arms = []
        for side in (-1, 1):
            p = Entity(parent=self.torso, position=(side * 0.3, 0.55, 0))
            Entity(parent=p, model=_limb_mesh(0.17, 0.17, HOODIE, SKIN, 0.8), shader=world_shader, double_sided=True)
            self.arms.append(p)
        self.wave = 0.0
        self.pose(0.016, 0.0, 0.0, 0.0, False)

    def pose(self, dt, t, wheelie, lean_fwd, first_person):
        self.enabled = not first_person
        self.wave += ((1.0 if wheelie > 10 else 0.0) - self.wave) * min(1.0, dt * 6)
        self.rotation_x = wheelie * 0.8
        self.torso.rotation_x = 16 + lean_fwd + self.wave * 6
        up = Vec3(0, 1, 0)
        for arm, grip in zip(self.arms, self.grips):
            target = self.torso.getRelativePoint(grip, Point3(0, 0, 0))
            arm.lookAt(self.torso, target, up)
            arm.scale_z = min(0.8, max(0.4, (target - arm.getPos(self.torso)).length()))
        for i, (leg, foot) in enumerate(zip(self.legs, self.feet)):
            target = self.getRelativePoint(foot, Point3(0, 0, 0))
            if i == 0 and self.wave > 0.01:
                swing = Point3(-0.5 - 0.07 * math.sin(t * 3.1), 0.32 + 0.14 * math.sin(t * 5.3), 0.12 + 0.22 * math.sin(t * 3.7))
                target = target + (swing - target) * self.wave
            leg.lookAt(self, target, Vec3(0, 0, 1))
            dist = (target - leg.getPos(self)).length()
            leg.scale_z = min(0.9, max(0.5, dist))


# ---------------------------------------------------------------------------
#   scooter visual
# ---------------------------------------------------------------------------

def _hide_shadow(e):
    e.hide(SHADOW_CAM)


class ScooterVisual(Entity):
    """root(heading) -> tilt(lean) -> pitch(rear axle, wheelie) -> body."""

    _soft = None

    def __init__(self, spec_index=0, paint_index=0, **kwargs):
        super().__init__(**kwargs)
        if ScooterVisual._soft is None:
            ScooterVisual._soft = make_soft_texture(64, 1.2)
        self.tilt = Entity(parent=self)
        self.pitch = Entity(parent=self.tilt)
        self.body = Entity(parent=self.pitch)
        self.blob = Entity(parent=self, model='quad', texture=ScooterVisual._soft, rotation_x=90, y=0.02,
                           scale=(0.7, 1.6), color=color.rgba(0, 0, 0, 0.5))
        _hide_shadow(self.blob)
        self.parts = []
        self.spec_index = -1
        self.speed_shown = -1
        self.set_car(spec_index, paint_index)

    def set_car(self, spec_index, paint_index):
        for e in self.parts:
            e.parent = None
            e.disable()
        self.parts = []
        spec = SCOOTERS[spec_index]
        self.spec_index, self.paint_index = spec_index, paint_index
        acc = PAINTS[paint_index][1]
        R = spec['R']
        self.info = dict(L=1.28, W=0.62, rear_z=REAR_Z, front_z=FRONT_Z, wheel_r=R, wheel_w=0.085, track=0.0,
                         head_y=DECK_Y1 + 1.6)
        self.pitch.position = (0, R, REAR_Z)
        self.body.position = (0, -R, -REAR_Z)

        tex = make_decal_texture(spec, acc)
        frame = spec['frame'] + (0.55,)
        dark = spec['dark'] + (0.3,)
        stem = spec['stem'] + (0.5,)
        accent = acc + (0.4,)
        dw = spec['deck_w']

        # ---------------- fixed frame (deck, rear) ----------------
        F = MeshBuilder()
        D = MeshBuilder()
        L = MeshBuilder()
        T = MeshBuilder()
        F.box(0, (DECK_Y0 + DECK_Y1) / 2 + 0.01, -0.015, dw, DECK_Y1 - DECK_Y0 - 0.02, 0.56, frame)
        F.box(0, DECK_Y0 + 0.012, -0.015, dw - 0.03, 0.03, 0.54, dark)
        F.box(0, DECK_Y1 + 0.004, -0.02, dw - 0.012, 0.018, 0.55, (0.02, 0.02, 0.025, 0.05))
        F.box(0, DECK_Y1 + 0.014, 0.1, 0.07, 0.002, 0.05, accent)
        for s in (-1, 1):
            F.box(s * (dw / 2 + 0.003), DECK_Y1 - 0.01, -0.015, 0.006, 0.012, 0.56, dark)
            x = s * (dw / 2 + 0.002)
            rnd = random.Random(7)
            for c in range(8):
                for r in range(5):
                    if rnd.random() < 0.15 + c * 0.1 and (c + r) % 2 == 0:
                        z, y, h = -0.02 + c * 0.021, 0.205 + r * 0.021, 0.0095
                        F.quad((x, y - h, z - h), (x, y - h, z + h), (x, y + h, z + h), (x, y + h, z - h), accent, (s, 0, 0))
            z0, z1, y0, y1 = 0.155, 0.255, 0.21, 0.3
            u0, v0, u1, v1 = BADGE_UV
            if s > 0:
                D.quad((x, y0, z0), (x, y0, z1), (x, y1, z1), (x, y1, z0), (1, 1, 1, 0.3), (1, 0, 0), ((u0, v0), (u1, v0), (u1, v1), (u0, v1)))
            else:
                D.quad((x, y0, z1), (x, y0, z0), (x, y1, z0), (x, y1, z1), (1, 1, 1, 0.3), (-1, 0, 0), ((u0, v0), (u1, v0), (u1, v1), (u0, v1)))
            F.box(x + s * 0.001, 0.3, -0.23, 0.002, 0.012, 0.06, (0.3, 0.3, 0.32, 0.3))
            # rear swingarm with pixel squares
            a0, a1 = (s * 0.07, 0.24, -0.26), (s * 0.07, R, REAR_Z)
            beam(F, a0, a1, 0.028, 0.06, frame)
            squares_on(F, a0, a1, 0.028, (0, 1, 0), s, [(0.3, 0.0), (0.42, 0.012), (0.5, -0.01), (0.6, 0.008), (0.7, -0.012), (0.8, 0.0)], 0.014, accent)
            F.cyl_x(s * 0.075, R, REAR_Z, 0.02, 0.02, dark, segs=8)
        coil(F, (0, 0.21, -0.36), (0, 0.4, -0.31), 0.03, 6, dark)
        beam(F, (0, 0.27, -0.28), (0, 0.42, -0.34), 0.08, 0.04, frame)
        F.box(0, 0.425, -0.43, 0.14, 0.025, 0.2, (0.02, 0.02, 0.025, 0.2))
        arc_strip(F, (0, R, REAR_Z), R + 0.05, 25, 150, 0.11, dark)
        T.box(0, 0.425, -0.535, 0.09, 0.03, 0.02, (1.0, 0.05, 0.03, 1.0))
        # neck (fixed)
        beam(F, (0, 0.32, 0.24), (0, 0.55, 0.4), 0.1, 0.07, frame)
        beam(F, (0, 0.2, 0.25), (0, 0.42, 0.36), 0.08, 0.05, dark)

        # ---------------- steering assembly ----------------
        S = MeshBuilder()
        SD = MeshBuilder()
        H = MeshBuilder()
        S.box(0, 0.57, 0.42, 0.075, 0.12, 0.075, dark)
        stem_a, stem_b = (0, 0.6, 0.43), (0, 1.18, 0.3)
        beam(S, stem_a, stem_b, 0.055, 0.055, stem, up=(0, 0, 1))
        S.box(0, 0.68, 0.415, 0.07, 0.05, 0.07, dark)
        f, s_ax, u_ax = _axes(stem_a, stem_b, (0, 0, 1))
        Ls = math.dist(stem_a, stem_b)
        for side in (-1, 1):
            n = s_ax if side > 0 else (-s_ax[0], -s_ax[1], -s_ax[2])
            off = side * 0.0295
            t0, t1, hw = 0.32, 0.86, 0.022
            p = [_p(stem_a, s_ax, off, u_ax, b, f, t * Ls) for t, b in ((t0, -hw), (t1, -hw), (t1, hw), (t0, hw))]
            uu0, vv0, uu1, vv1 = STEM_UV
            uv = ((uu0, vv0), (uu1, vv0), (uu1, vv1), (uu0, vv1)) if side > 0 else ((uu0, vv1), (uu1, vv1), (uu1, vv0), (uu0, vv0))
            SD.quad(p[0], p[1], p[2], p[3], (1, 1, 1, 0.3), n, uv)
            squares_on(S, stem_a, stem_b, 0.055, (0, 0, 1), side,
                       [(0.2, 0.0), (0.24, 0.012), (0.27, -0.01), (0.12, 0.008), (0.16, -0.012)], 0.011, accent)
        for side in (-1, 1):
            a0, a1 = (side * 0.07, 0.4, 0.33), (side * 0.07, R, FRONT_Z)
            beam(S, a0, a1, 0.026, 0.055, frame)
            squares_on(S, a0, a1, 0.026, (0, 1, 0), side, [(0.2, 0.0), (0.3, 0.012), (0.4, -0.008), (0.55, 0.01), (0.65, -0.01)], 0.013, accent)
            coil(S, (side * 0.045, 0.28, 0.42), (side * 0.045, 0.52, 0.425), 0.026, 6, dark)
            S.cyl_x(side * 0.075, R, FRONT_Z, 0.02, 0.02, dark, segs=8)
        arc_strip(S, (0, R, FRONT_Z), R + 0.045, 40, 115, 0.1, dark)
        H.box(0, 0.64, 0.46, 0.07, 0.035, 0.012, (1.0, 0.98, 0.9, 1.0))
        H.box(0, 1.1, 0.34, 0.06, 0.03, 0.012, (1.0, 0.98, 0.9, 1.0))
        bar_y, bar_z = 1.2, 0.3
        beam(S, (-0.31, bar_y, bar_z), (0.31, bar_y, bar_z), 0.028, 0.028, stem, up=(0, 1, 0))
        for side in (-1, 1):
            beam(S, (side * 0.2, bar_y, bar_z), (side * 0.325, bar_y, bar_z), 0.04, 0.04, (0.02, 0.02, 0.02, 0.1))
            S.box(side * 0.16, bar_y + 0.005, bar_z + 0.01, 0.05, 0.045, 0.05, dark)
            beam(S, (side * 0.17, bar_y, bar_z + 0.03), (side * 0.29, bar_y - 0.01, bar_z + 0.09), 0.012, 0.018, dark)
        S.box(0.13, bar_y - 0.02, bar_z - 0.035, 0.03, 0.05, 0.02, dark)
        S.box(0, bar_y, bar_z, 0.06, 0.05, 0.05, dark)
        pod_a, pod_b = (0, bar_y + 0.025, bar_z - 0.045), (0, bar_y + 0.06, bar_z + 0.035)
        pf, ps, pu = beam(S, pod_a, pod_b, 0.2, 0.03, (0.03, 0.03, 0.035, 0.6), up=(0, 1, 0))
        centre = ((pod_a[0] + pod_b[0]) / 2, (pod_a[1] + pod_b[1]) / 2, (pod_a[2] + pod_b[2]) / 2)
        scr = _p(centre, pu, 0.0155, pf, 0.0)
        hw, hh = 0.085, 0.034
        S.quad(_p(scr, ps, -hw, pf, -hh), _p(scr, ps, hw, pf, -hh), _p(scr, ps, hw, pf, hh), _p(scr, ps, -hw, pf, hh), (0.01, 0.015, 0.03, 1.0), pu)
        lit = _p(scr, pu, 0.001, pf, 0.0)
        for k in range(10):
            bx = -0.055 + k * 0.007
            L.quad(_p(lit, ps, bx, pf, -0.024), _p(lit, ps, bx + 0.005, pf, -0.024),
                   _p(lit, ps, bx + 0.005, pf, -0.018), _p(lit, ps, bx, pf, -0.018),
                   (0.95, 0.95, 0.95, 0) if k < 8 else (0.25, 0.25, 0.3, 0), pu)
        for mb in (S, SD, H, L):
            shift_z(mb, STEER_Z)

        self.frame = self._part(self.body, F)
        self.decal = self._part(self.body, D, tex)
        self.tail = self._part(self.body, T, emit=0.6)
        self.front = Entity(parent=self.body, position=(0, 0, STEER_Z))
        self.parts.append(self.front)
        self._part(self.front, S)
        self._part(self.front, SD, tex)
        self.head = self._part(self.front, H, emit=1.0)
        self._part(self.front, L, emit=1.0)
        w = 0.085
        self.rear_wheel = Entity(parent=self.body, position=(0, R, REAR_Z), model=build_wheel(R, w, spec['rim']),
                                 shader=world_shader, double_sided=True)
        self.front_wheel = Entity(parent=self.front, position=(0, R, FRONT_Z - STEER_Z),
                                  model=build_wheel(R, w, spec['rim']), shader=world_shader, double_sided=True)
        self.parts += [self.rear_wheel, self.front_wheel]

        # dashboard text lives on the screen plane
        sz = scr[2] - STEER_Z
        self.dash = Entity(parent=self.front, position=(scr[0], scr[1], sz))
        self.dash.lookAt(Point3(scr[0] - pu[0], scr[1] - pu[1], sz - pu[2]), Vec3(*pf))
        self.parts.append(self.dash)
        self.speed_txt = Text('0', parent=self.dash, font=FONT_TITLE, scale=1.5, origin=(0, 0), y=0.004, z=-0.002,
                              color=color.white)
        self.brand_txt = Text(spec['dash'], parent=self.dash, font=FONT_TITLE, scale=0.28, origin=(0.5, 0), x=0.08,
                              y=0.018, z=-0.002, color=Vec4(0.2, 0.85, 1, 1))
        self.unit_txt = Text('km/h', parent=self.dash, scale=0.22, origin=(0.5, 0), x=0.08, y=0.004, z=-0.002,
                             color=Vec4(0.6, 0.65, 0.8, 1))
        self.mode_txt = Text('RACE', parent=self.dash, font=FONT_TITLE, scale=0.24, origin=(-0.5, 0), x=-0.078, y=0.018,
                             z=-0.002, color=Vec4(1, 0.15, 0.15, 1))
        for t in (self.speed_txt, self.brand_txt, self.unit_txt, self.mode_txt):
            _hide_shadow(t)
            t.setLightOff()
        self.speed_shown = -1

        # anchors for the rider
        self.grips = [Entity(parent=self.front, position=(s * 0.27, bar_y, bar_z - STEER_Z)) for s in (-1, 1)]
        self.feet = [Entity(parent=self.body, position=(-0.055, DECK_Y1 + 0.02, 0.12)),
                     Entity(parent=self.body, position=(0.055, DECK_Y1 + 0.02, -0.17))]
        self.parts += self.grips + self.feet
        self.rider = Rider(self.body, self.grips, self.feet)
        self.rider.position = (0, DECK_Y1 + 0.02, -0.03)
        self.rider.scale = 0.88
        self.parts.append(self.rider)
        self.wheelie = 0.0

    def _part(self, parent, mb, texture=None, emit=None):
        m = mb.build()
        e = Entity(parent=parent, model=m, shader=world_shader, double_sided=True)
        if texture:
            e.texture = texture
        if emit is not None:
            e.set_shader_input('u_emit', emit)
        self.parts.append(e)
        return e

    def set_paint(self, paint_index):
        self.set_car(self.spec_index, paint_index)

    def update_visual(self, steer_deg, spin_deg, lean, wheelie, headlights, brake, boost, t,
                      speed_kmh=0.0, first_person=False, dt=0.016, lean_fwd=0.0):
        self.front.rotation_y = steer_deg
        self.rear_wheel.rotation_x += spin_deg
        self.front_wheel.rotation_x += spin_deg
        self.tilt.rotation_z = lean
        self.pitch.rotation_x = -wheelie
        self.head.set_shader_input('u_emit', 1.0 if headlights else 0.0)
        self.tail.set_shader_input('u_emit', 1.0 if brake else (0.6 if headlights else 0.25))
        v = int(round(speed_kmh))
        if v != self.speed_shown:
            self.speed_shown = v
            self.speed_txt.text = str(v)
        self.mode_txt.text = 'TURBO' if boost else 'RACE'
        self.rider.pose(dt, t, wheelie, lean_fwd, first_person)
