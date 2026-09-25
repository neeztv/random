"""Car definitions and procedural 3D car models (lofted body, spoked wheels, lights)."""
import math

from panda3d.core import BitMask32
from ursina import Entity, Mesh, color

from .core import MeshBuilder, clamp, make_soft_texture, world_shader

PAINTS = [
    ('Czerwień Rosso', (0.75, 0.05, 0.05)),
    ('Biel perłowa', (0.88, 0.88, 0.86)),
    ('Czerń nocy', (0.04, 0.04, 0.05)),
    ('Żółć wyścigowa', (0.95, 0.7, 0.04)),
    ('Błękit Midnight', (0.05, 0.2, 0.68)),
    ('Zieleń limonki', (0.32, 0.78, 0.1)),
    ('Pomarańcz', (0.95, 0.36, 0.04)),
    ('Fiolet neon', (0.42, 0.08, 0.72)),
]

CARS = [
    dict(
        name='KAZE GT', desc='Lekkie coupe JDM. Zwinne, przewidywalne, stworzone do driftu.',
        stats={'MOC': 0.62, 'PRZYCZEPNOŚĆ': 0.62, 'DRIFT': 0.95, 'V-MAX': 0.66},
        accel=10.5, vmax=68.0, grip=7.5, drift_grip=1.2, drift_yaw=100.0, steer=36.0, power_slide=0.9,
        L=4.45, W=1.80, rear_axle=0.2, front_axle=0.78, wheel_r=0.33, wheel_w=0.25, clear=0.17,
        rim=(0.78, 0.78, 0.8), tumble=0.8, pillar=0.47, wing='high', scoop=False, intakes=False,
        belt=[(0, 0.78), (0.08, 0.86), (0.3, 0.9), (0.62, 0.9), (0.9, 0.77), (1, 0.64)],
        roof=[(0, 0), (0.19, 0), (0.34, 1.3), (0.54, 1.32), (0.7, 0), (1, 0)],
        width=[(0, 0.9), (0.07, 0.97), (0.2, 1), (0.82, 1), (0.95, 0.95), (1, 0.86)],
    ),
    dict(
        name='BRUISER V8', desc='Amerykański muscle car. Brutalna moc i luźny tył.',
        stats={'MOC': 0.9, 'PRZYCZEPNOŚĆ': 0.45, 'DRIFT': 0.82, 'V-MAX': 0.76},
        accel=12.5, vmax=74.0, grip=6.6, drift_grip=1.0, drift_yaw=88.0, steer=32.0, power_slide=1.0,
        L=4.8, W=1.94, rear_axle=0.2, front_axle=0.79, wheel_r=0.36, wheel_w=0.3, clear=0.18,
        rim=(0.22, 0.22, 0.24), tumble=0.78, pillar=None, wing='lip', scoop=True, intakes=False,
        belt=[(0, 0.86), (0.08, 0.93), (0.4, 0.95), (0.85, 0.92), (1, 0.8)],
        roof=[(0, 0), (0.16, 0), (0.36, 1.34), (0.52, 1.36), (0.65, 0), (1, 0)],
        width=[(0, 0.93), (0.06, 0.99), (0.2, 1), (0.85, 1), (0.96, 0.96), (1, 0.9)],
    ),
    dict(
        name='VENTO RS', desc='Supersamochód z centralnym silnikiem. Szybki i precyzyjny.',
        stats={'MOC': 0.96, 'PRZYCZEPNOŚĆ': 0.9, 'DRIFT': 0.6, 'V-MAX': 0.98},
        accel=14.0, vmax=86.0, grip=9.5, drift_grip=1.5, drift_yaw=92.0, steer=30.0, power_slide=0.65,
        L=4.55, W=2.0, rear_axle=0.21, front_axle=0.8, wheel_r=0.35, wheel_w=0.31, clear=0.13,
        rim=(0.82, 0.62, 0.24), tumble=0.72, pillar=None, wing='big', scoop=False, intakes=True,
        belt=[(0, 0.84), (0.12, 0.88), (0.4, 0.86), (0.7, 0.68), (0.9, 0.58), (1, 0.48)],
        roof=[(0, 0), (0.25, 0), (0.42, 1.13), (0.55, 1.15), (0.8, 0), (1, 0)],
        width=[(0, 0.92), (0.08, 1), (0.3, 1), (0.75, 0.96), (0.95, 0.9), (1, 0.8)],
    ),
]

DARK = (0.04, 0.04, 0.05, 0.1)
TRIM = (0.07, 0.07, 0.08, 0.35)
GLASS = (0.03, 0.05, 0.08, 1.0)
CHROME = (0.85, 0.86, 0.9, 1.0)
RUBBER = (0.05, 0.05, 0.055, 0.08)


def curve(points, t):
    for (t0, v0), (t1, v1) in zip(points, points[1:]):
        if t <= t1:
            k = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
            k = (1 - math.cos(math.pi * k)) / 2
            return v0 + (v1 - v0) * k
    return points[-1][1]


def _station(spec, t):
    L, W = spec['L'], spec['W']
    z = -L / 2 + t * L
    belt = curve(spec['belt'], t)
    roof = max(belt, curve(spec['roof'], t))
    hw = W / 2 * curve(spec['width'], t)
    R = spec['wheel_r']
    yb = spec['clear']
    for at in (spec['rear_axle'], spec['front_axle']):
        dz = z - (-L / 2 + at * L)
        g = R + 0.07
        if abs(dz) < g:
            yb = max(yb, R + math.sqrt(g * g - dz * dz))
    yb = min(yb, belt - 0.1)
    cab = clamp((roof - belt) / 0.25, 0.0, 1.0)
    rw = hw * spec['tumble']
    h = belt - yb
    right = [
        (0.0, yb), (hw * 0.9, yb), (hw, yb + 0.15 * h), (hw, yb + 0.6 * h),
        (hw * 0.98, belt - 0.05), (hw * 0.92, belt),
    ]
    no_cab = [(hw * 0.78, belt + 0.015), (hw * 0.55, belt + 0.035), (hw * 0.28, belt + 0.045), (0.0, belt + 0.05)]
    with_cab = [(hw * 0.86, belt + 0.01), (rw, roof - 0.06), (rw * 0.85, roof), (0.0, roof + 0.015)]
    for a, b in zip(no_cab, with_cab):
        right.append((a[0] + (b[0] - a[0]) * cab, a[1] + (b[1] - a[1]) * cab))
    ring = right + [(-x, y) for (x, y) in reversed(right[:-1])]
    return z, ring, dict(belt=belt, roof=roof, hw=hw, yb=yb, cab=cab)


def _segment_color(j, info0, info1, dz, paint, spec, t):
    k = j if j < 9 else 17 - j
    cab = (info0['cab'] + info1['cab']) / 2
    if k == 0:
        return DARK
    if k == 1:
        return TRIM
    if k == 6:
        if cab > 0.45:
            if spec['pillar'] is not None and abs(t - spec['pillar']) < 0.012:
                return TRIM
            return GLASS
        return paint
    if k in (7, 8):
        slope = abs(info1['roof'] - info0['roof']) / max(dz, 1e-4)
        if cab > 0.3 and slope > 0.28:
            return GLASS
    return paint


def build_body(spec, paint_rgb):
    """Returns (body_builder, head_builder, tail_builder, info)."""
    paint = (paint_rgb[0], paint_rgb[1], paint_rgb[2], 0.85)
    N = 52
    stations = [_station(spec, i / (N - 1)) for i in range(N)]
    M = len(stations[0][1])
    grid = [[(p[0], p[1], z) for p in ring] for z, ring, _ in stations]

    normals = []
    for i in range(N):
        row = []
        for j in range(M):
            a = grid[i][min(j + 1, M - 1)]
            b = grid[i][max(j - 1, 0)]
            c = grid[min(i + 1, N - 1)][j]
            d = grid[max(i - 1, 0)][j]
            tj = (a[0] - b[0], a[1] - b[1], a[2] - b[2])
            ti = (c[0] - d[0], c[1] - d[1], c[2] - d[2])
            n = (tj[1] * ti[2] - tj[2] * ti[1], tj[2] * ti[0] - tj[0] * ti[2], tj[0] * ti[1] - tj[1] * ti[0])
            p = grid[i][j]
            info = stations[i][2]
            out = (p[0], p[1] - (info['yb'] + info['roof']) / 2, 0.0)
            if n[0] * out[0] + n[1] * out[1] < 0:
                n = (-n[0], -n[1], -n[2])
            l = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2) or 1.0
            row.append((n[0] / l, n[1] / l, n[2] / l))
        normals.append(row)

    mb = MeshBuilder()
    dz = spec['L'] / (N - 1)
    for i in range(N - 1):
        t = (i + 0.5) / (N - 1)
        for j in range(M - 1):
            col = _segment_color(j, stations[i][2], stations[i + 1][2], dz, paint, spec, t)
            b = len(mb)
            for (ii, jj) in ((i, j), (i, j + 1), (i + 1, j + 1), (i + 1, j)):
                mb.v.extend(grid[ii][jj])
                mb.n.extend(normals[ii][jj])
                mb.c.extend(col)
                mb.t.extend((0.0, 0.0))
            mb.i.extend((b, b + 1, b + 2, b, b + 2, b + 3))

    for idx, nz in ((0, -1.0), (N - 1, 1.0)):
        z, ring, info = stations[idx]
        cy = (info['yb'] + info['belt']) / 2
        for j in range(M - 1):
            mb.tri((0.0, cy, z), (ring[j][0], ring[j][1], z), (ring[j + 1][0], ring[j + 1][1], z), paint, (0, 0, nz))

    L, W = spec['L'], spec['W']
    zf, zr = L / 2, -L / 2
    front, rear = stations[-1][2], stations[0][2]
    head = MeshBuilder()
    tail = MeshBuilder()

    # front fascia
    fh = front['belt'] - spec['clear']
    mb.box(0, spec['clear'] + fh * 0.32, zf + 0.01, front['hw'] * 1.05, fh * 0.34, 0.04, TRIM)
    mb.box(0, spec['clear'] + 0.03, zf - 0.08, W * 0.94, 0.05, 0.3, DARK)
    for s in (-1, 1):
        x = s * front['hw'] * 0.62
        mb.box(x, front['belt'] - 0.09, zf + 0.01, front['hw'] * 0.56, 0.14, 0.04, TRIM)
        head.box(x, front['belt'] - 0.09, zf + 0.03, front['hw'] * 0.46, 0.08, 0.04, (1.0, 0.97, 0.9, 1.0))
    mb.box(0, spec['clear'] + fh * 0.12, zf + 0.02, 0.5, 0.11, 0.02, (0.9, 0.9, 0.9, 0.3))

    # rear
    rh = rear['belt'] - spec['clear']
    for s in (-1, 1):
        x = s * rear['hw'] * 0.62
        mb.box(x, rear['belt'] - 0.1, zr - 0.01, rear['hw'] * 0.6, 0.14, 0.04, TRIM)
        tail.box(x, rear['belt'] - 0.1, zr - 0.03, rear['hw'] * 0.52, 0.08, 0.04, (1.0, 0.05, 0.03, 1.0))
        mb.box(s * 0.5, spec['clear'] + 0.1, zr - 0.05, 0.11, 0.1, 0.16, CHROME)
    if spec['wing'] == 'big':
        tail.box(0, rear['belt'] - 0.1, zr - 0.03, rear['hw'] * 0.7, 0.03, 0.03, (1.0, 0.05, 0.03, 1.0))
    mb.box(0, spec['clear'] + 0.06, zr + 0.1, W * 0.9, 0.1, 0.3, DARK)
    mb.box(0, spec['clear'] + rh * 0.4, zr - 0.02, 0.5, 0.12, 0.02, (0.9, 0.9, 0.9, 0.3))

    # side skirts
    ar = -L / 2 + spec['rear_axle'] * L
    af = -L / 2 + spec['front_axle'] * L
    R = spec['wheel_r']
    mid_hw = W / 2 * curve(spec['width'], 0.5)
    for s in (-1, 1):
        mb.box(s * (mid_hw - 0.02), spec['clear'] + 0.05, (ar + af) / 2, 0.08, 0.1, af - ar - 2 * R - 0.2, DARK)

    # mirrors at the windshield base
    ws_t = 0.7
    for i in range(N - 1, 0, -1):
        if stations[i][2]['cab'] > 0.1:
            ws_t = i / (N - 1)
            break
    ws_z = -L / 2 + ws_t * L - 0.15
    ws_belt = curve(spec['belt'], ws_t)
    ws_hw = W / 2 * curve(spec['width'], ws_t)
    for s in (-1, 1):
        mb.box(s * (ws_hw + 0.06), ws_belt + 0.1, ws_z, 0.16, 0.1, 0.12, paint)
        mb.box(s * (ws_hw - 0.02), ws_belt + 0.06, ws_z, 0.06, 0.03, 0.05, DARK)

    # spoilers / scoops / intakes
    wing = spec['wing']
    if wing in ('high', 'big'):
        h = 0.26 if wing == 'high' else 0.36
        wz = zr + 0.28
        for s in (-1, 1):
            mb.box(s * 0.55, rear['belt'] + h / 2, wz, 0.05, h, 0.14, DARK)
        span = W * (0.9 if wing == 'high' else 0.98)
        mb.box(0, rear['belt'] + h + 0.03, wz - 0.03, span, 0.05, 0.36 if wing == 'high' else 0.44, paint)
        for s in (-1, 1):
            mb.box(s * span / 2, rear['belt'] + h + 0.02, wz - 0.03, 0.03, 0.2, 0.44, DARK)
    elif wing == 'lip':
        mb.box(0, rear['belt'] + 0.05, zr + 0.14, W * 0.84, 0.05, 0.22, paint)
    if spec['scoop']:
        st = 0.86
        sz = -L / 2 + st * L
        by = curve(spec['belt'], st) + 0.045
        mb.box(0, by + 0.05, sz, 0.62, 0.1, 0.8, paint)
        mb.box(0, by + 0.06, sz + 0.41, 0.5, 0.07, 0.02, DARK)
    if spec['intakes']:
        st = 0.34
        sz = -L / 2 + st * L
        hw = W / 2 * curve(spec['width'], st)
        yb, belt = spec['clear'], curve(spec['belt'], st)
        for s in (-1, 1):
            mb.box(s * (hw + 0.005), (yb + belt) / 2 + 0.05, sz, 0.02, (belt - yb) * 0.42, 0.7, DARK)

    info = dict(
        L=L, W=W, rear_z=ar, front_z=af, wheel_r=R, wheel_w=spec['wheel_w'],
        track=W / 2 - spec['wheel_w'] / 2 + 0.02, exhaust=[(s * 0.5, spec['clear'] + 0.1, zr - 0.14) for s in (-1, 1)],
        head_pos=(0, front['belt'] - 0.1, zf + 0.1), rear_y=rear['belt'],
    )
    return mb, head, tail, info


def build_wheel(R, w, rim_col):
    mb = MeshBuilder()
    mb.cyl_x(0, 0, 0, R, w, RUBBER, segs=20)
    rim = (rim_col[0], rim_col[1], rim_col[2], 0.9)
    xo = w / 2 + 0.004
    segs = 20
    for s in range(segs):
        a0 = math.tau * s / segs
        a1 = math.tau * (s + 1) / segs
        for r0, r1, col in ((0.0, R * 0.6, (0.06, 0.06, 0.07, 0.2)), (R * 0.6, R * 0.7, rim)):
            p = [(xo, math.cos(a) * r, math.sin(a) * r) for (a, r) in ((a0, r0), (a1, r0), (a1, r1), (a0, r1))]
            mb.quad(p[0], p[1], p[2], p[3], col, (1, 0, 0))
    for k in range(5):
        a = math.tau * k / 5
        d = (math.cos(a), math.sin(a))
        pd = (-d[1], d[0])
        x = xo + 0.012
        for w0, w1 in ((0.045, 0.03),):
            p0 = (x, pd[0] * w0 + d[0] * 0.06, pd[1] * w0 + d[1] * 0.06)
            p1 = (x, -pd[0] * w0 + d[0] * 0.06, -pd[1] * w0 + d[1] * 0.06)
            p2 = (x, -pd[0] * w1 + d[0] * R * 0.64, -pd[1] * w1 + d[1] * R * 0.64)
            p3 = (x, pd[0] * w1 + d[0] * R * 0.64, pd[1] * w1 + d[1] * R * 0.64)
            mb.quad(p0, p1, p2, p3, rim, (1, 0, 0))
    mb.cyl_x(xo + 0.01, 0, 0, 0.075, 0.03, CHROME, segs=10)
    return mb.build()


def _hide_from_shadow(e):
    e.hide(BitMask32.bit(1))


class CarVisual(Entity):
    """Visual car: body, wheels (steer + spin), lights, blob shadow, nitro flames."""

    _soft = None

    def __init__(self, spec_index=0, paint_index=0, **kwargs):
        super().__init__(**kwargs)
        if CarVisual._soft is None:
            CarVisual._soft = make_soft_texture(64, 1.2)
        self.tilt = Entity(parent=self)
        self.body = Entity(parent=self.tilt, shader=world_shader, double_sided=True)
        self.head = Entity(parent=self.tilt, shader=world_shader, double_sided=True)
        self.tail = Entity(parent=self.tilt, shader=world_shader, double_sided=True)
        self.blob = Entity(parent=self, model='quad', texture=CarVisual._soft, rotation_x=90, y=0.03,
                           color=color.rgba(0, 0, 0, 0.55))
        _hide_from_shadow(self.blob)
        self.wheels = []
        self.flames = []
        self.spec_index = -1
        self.set_car(spec_index, paint_index)

    def set_car(self, spec_index, paint_index):
        spec = CARS[spec_index]
        self.spec_index = spec_index
        self.paint_index = paint_index
        body, head, tail, info = build_body(spec, PAINTS[paint_index][1])
        self.info = info
        self.body.model = body.build()
        self.head.model = head.build()
        self.tail.model = tail.build()
        self.head.set_shader_input('u_emit', 1.0)
        self.tail.set_shader_input('u_emit', 0.6)
        self.blob.scale = (info['W'] * 1.35, info['L'] * 1.2)
        for w in self.wheels:
            w['pivot'].parent = None
            w['pivot'].disable()
        for f in self.flames:
            f.disable()
        self.wheels = []
        R, ww = info['wheel_r'], info['wheel_w']
        for front in (True, False):
            for side in (-1, 1):
                pivot = Entity(parent=self.tilt, position=(side * info['track'], R, info['front_z'] if front else info['rear_z']),
                               rotation_y=0 if side > 0 else 180)
                wheel = Entity(parent=pivot, model=build_wheel(R, ww, spec['rim']), shader=world_shader, double_sided=True)
                caliper = MeshBuilder()
                caliper.box(ww / 2 - 0.03, R * 0.32, -R * 0.28, 0.05, R * 0.42, R * 0.4, (0.85, 0.08, 0.05, 0.6))
                Entity(parent=pivot, model=caliper.build(), shader=world_shader, double_sided=True)
                self.wheels.append(dict(pivot=pivot, wheel=wheel, front=front, side=side))
        self.flames = []
        for (x, y, z) in info['exhaust']:
            fm = MeshBuilder()
            segs = 8
            for s in range(segs):
                a0, a1 = math.tau * s / segs, math.tau * (s + 1) / segs
                fm.tri((0, 0, 0), (math.cos(a0) * 0.07, math.sin(a0) * 0.07, 0), (0, 0, -1.0), (0.4, 0.6, 1.0, 0))
                fm.tri((0, 0, 0), (math.cos(a1) * 0.07, math.sin(a1) * 0.07, 0), (0, 0, -1.0), (0.4, 0.6, 1.0, 0))
            f = Entity(parent=self.tilt, model=fm.build(), position=(x, y, z), unlit=True, double_sided=True,
                       color=color.rgba(0.55, 0.75, 1.0, 0.85), enabled=False)
            f.setLightOff()
            _hide_from_shadow(f)
            self.flames.append(f)

    def set_paint(self, paint_index):
        self.set_car(self.spec_index, paint_index)

    def update_visual(self, steer_deg, spin_deg, roll, pitch, headlights, brake, nitro, t):
        for w in self.wheels:
            base = 0 if w['side'] > 0 else 180
            w['pivot'].rotation_y = base + (steer_deg if w['front'] else 0)
            w['wheel'].rotation_x += spin_deg * w['side']
        self.tilt.rotation_z = roll
        self.tilt.rotation_x = pitch
        self.head.set_shader_input('u_emit', 1.0 if headlights else 0.0)
        self.tail.set_shader_input('u_emit', 1.0 if brake else (0.55 if headlights else 0.25))
        for i, f in enumerate(self.flames):
            f.enabled = nitro
            if nitro:
                k = 0.7 + 0.5 * abs(math.sin(t * 40 + i * 1.7))
                f.scale = (1 + 0.3 * k, 1 + 0.3 * k, k)
