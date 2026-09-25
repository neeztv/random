"""Environment (sky, sun, time of day) and the streamed procedural city."""
import math
import random

from panda3d.core import BitMask32, PTA_LVecBase4f
from panda3d.core import DirectionalLight as PandaDirectionalLight
from ursina import Entity, Vec3, Vec4, destroy, scene

from .core import (BLOCK, ROAD_W, SIDEWALK, TIME_PRESETS, VIEW_CHUNKS, MeshBuilder, lerp, lerp3,
                   make_facade_texture, make_ground_texture, sky_shader, world_shader)

SHADOW_CAM = BitMask32.bit(1)

ASPHALT = (0.22, 0.22, 0.24, 0.12)
ASPHALT_LOT = (0.27, 0.27, 0.29, 0.1)
SIDEWALK_COL = (0.55, 0.54, 0.52, 0.05)
CURB = (0.62, 0.62, 0.6, 0.05)
GRASS = (0.22, 0.42, 0.16, 0.0)
PAINT_WHITE = (0.9, 0.9, 0.88, 0.3)
PAINT_YELLOW = (0.95, 0.72, 0.1, 0.3)
POLE = (0.2, 0.21, 0.23, 0.6)
BARK = (0.3, 0.2, 0.12, 0.0)
BUILDING_TINTS = [
    (0.78, 0.76, 0.72), (0.62, 0.64, 0.7), (0.72, 0.6, 0.5), (0.5, 0.52, 0.56),
    (0.82, 0.78, 0.68), (0.55, 0.6, 0.64), (0.66, 0.5, 0.44), (0.9, 0.88, 0.84),
]
NEON = [(1.0, 0.15, 0.6, 0), (0.1, 0.9, 1.0, 0), (1.0, 0.85, 0.1, 0), (0.3, 1.0, 0.35, 0), (0.7, 0.3, 1.0, 0)]
SHOP_UV = (0.0625, 0.943)


class Environment:
    """Sky dome, sun + shadow map, global shader uniforms, smooth time-of-day transitions."""

    def __init__(self, time_key='sunset', shadows=True):
        self.lamps = PTA_LVecBase4f.empty_array(12)
        self.cur = dict(TIME_PRESETS[time_key])
        self.target = dict(self.cur)
        self.key = time_key
        self.time = 0.0
        for name, value in (('u_lamps', self.lamps), ('u_hl_pos', Vec4(0, 0, 0, 0)), ('u_hl_dir', Vec3(0, 0, 1)),
                            ('u_cam_pos', Vec3(0, 0, 0)), ('u_time', 0.0), ('u_shadow', 1.0)):
            scene.set_shader_input(name, value)

        self.sky = Entity(model='sphere', scale=1500, shader=sky_shader, double_sided=True)
        self.sky.setBin('background', 0)
        self.sky.setDepthWrite(False)
        self.sky.hide(SHADOW_CAM)

        self.sun = Entity()
        self.light = PandaDirectionalLight('sun')
        self.light.set_color((1, 1, 1, 1))
        scene.set_light(self.sun.attachNewNode(self.light))
        self.light.set_camera_mask(SHADOW_CAM)
        self.shadows = False
        self.set_shadows(shadows)
        self._apply()

    def set_shadows(self, on):
        if on and not self.shadows:
            self.light.set_shadow_caster(True, 2048, 2048)
            lens = self.light.get_lens()
            lens.set_film_size(130, 130)
            lens.set_near_far(1, 500)
        elif not on and self.shadows:
            self.light.set_shadow_caster(False)
        self.shadows = on
        scene.set_shader_input('u_shadow', 1.0 if on else 0.0)

    def set_time(self, key, instant=False):
        self.key = key
        self.target = dict(TIME_PRESETS[key])
        if instant:
            self.cur = dict(self.target)
            self._apply()

    @property
    def night(self):
        return self.cur['night']

    def _apply(self):
        c = self.cur
        d = Vec3(*c['sun_dir']).normalized()
        for k in ('sun_col', 'sky_amb', 'gnd_amb', 'fog_col', 'sky_top'):
            scene.set_shader_input('u_' + k, Vec3(*c[k]))
        scene.set_shader_input('u_sun_dir', d)
        scene.set_shader_input('u_fog', c['fog'])
        scene.set_shader_input('u_night', c['night'])

    def update(self, dt, focus, cam_pos):
        self.time += dt
        k = min(1.0, dt * 1.5)
        for key, val in self.target.items():
            cur = self.cur[key]
            if isinstance(val, tuple):
                self.cur[key] = lerp3(cur, val, k)
            elif isinstance(val, float):
                self.cur[key] = lerp(cur, val, k)
        self._apply()
        d = Vec3(*self.cur['sun_dir']).normalized()
        snap = 2.0
        fx, fz = round(focus[0] / snap) * snap, round(focus[2] / snap) * snap
        f = Vec3(fx, 0, fz)
        self.sun.position = f - d * 200
        self.sun.look_at(f)
        self.sky.position = cam_pos
        scene.set_shader_input('u_cam_pos', cam_pos)
        scene.set_shader_input('u_time', self.time)

    def set_lamps(self, lamp_list):
        power = self.cur['lamps']
        for i in range(12):
            if i < len(lamp_list) and power > 0.01:
                x, y, z = lamp_list[i]
                self.lamps[i] = Vec4(x, y, z, power)
            else:
                self.lamps[i] = Vec4(0, 0, 0, 0)


class Chunk:
    __slots__ = ('entities', 'boxes', 'circles', 'lamps', 'cones', 'raised', 'kind', 'bulbs')

    def __init__(self):
        self.entities = []
        self.boxes = []
        self.circles = []
        self.lamps = []
        self.cones = []
        self.raised = None
        self.kind = 'city'
        self.bulbs = None


class Cone:
    __slots__ = ('e', 'x', 'z', 'y', 'vx', 'vy', 'vz', 'spin', 'hit', 'rest')

    def __init__(self, e, x, z):
        self.e, self.x, self.z, self.y = e, x, z, 0.0
        self.vx = self.vy = self.vz = self.spin = 0.0
        self.hit = False
        self.rest = True


class World:
    def __init__(self, seed=1337):
        self.seed = seed
        self.chunks = {}
        self.facade_tex = make_facade_texture()
        self.ground_tex = make_ground_texture()
        self.moving_cones = []
        self.lamp_power = 1.0
        cm = MeshBuilder()
        cm.box(0, 0.03, 0, 0.5, 0.06, 0.5, (0.1, 0.1, 0.1, 0.1))
        cm.cyl(0, 0.06, 0, 0.21, 0.14, 0.28, (1.0, 0.35, 0.05, 0.4), segs=10, cap=False)
        cm.cyl(0, 0.34, 0, 0.14, 0.1, 0.14, (0.95, 0.95, 0.95, 0.4), segs=10, cap=False)
        cm.cyl(0, 0.48, 0, 0.1, 0.03, 0.26, (1.0, 0.35, 0.05, 0.4), segs=10)
        self.cone_mesh = cm.build()

    # ------------------------------------------------------------------ streaming
    @staticmethod
    def key_at(x, z):
        return (math.floor(x / BLOCK), math.floor(z / BLOCK))

    def update(self, x, z, budget=1):
        pcx, pcz = self.key_at(x, z)
        missing = []
        for dx in range(-VIEW_CHUNKS, VIEW_CHUNKS + 1):
            for dz in range(-VIEW_CHUNKS, VIEW_CHUNKS + 1):
                k = (pcx + dx, pcz + dz)
                if k not in self.chunks:
                    missing.append((dx * dx + dz * dz, k))
        missing.sort()
        for _, k in missing[:budget]:
            self.chunks[k] = self._build_chunk(*k)
        for k in [k for k in self.chunks if abs(k[0] - pcx) > VIEW_CHUNKS + 1 or abs(k[1] - pcz) > VIEW_CHUNKS + 1]:
            self._kill(k)
        return len(missing) - budget

    def build_all(self, x, z):
        while self.update(x, z, budget=4) > 0:
            pass

    def _kill(self, k):
        ch = self.chunks.pop(k)
        for e in ch.entities:
            destroy(e)
        for c in ch.cones:
            if c in self.moving_cones:
                self.moving_cones.remove(c)
            destroy(c.e)

    def clear(self):
        for k in list(self.chunks):
            self._kill(k)

    def near_chunks(self, x, z):
        cx, cz = self.key_at(x, z)
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                ch = self.chunks.get((cx + dx, cz + dz))
                if ch:
                    yield ch

    def lamps_near(self, x, z, n=12):
        ls = []
        for ch in self.near_chunks(x, z):
            ls.extend(ch.lamps)
        ls.sort(key=lambda p: (p[0] - x) ** 2 + (p[2] - z) ** 2)
        return ls[:n]

    def ground_height(self, x, z):
        ch = self.chunks.get(self.key_at(x, z))
        if ch and ch.raised:
            x0, z0, x1, z1 = ch.raised
            if x0 < x < x1 and z0 < z < z1:
                return 0.14
        return 0.0

    def set_lamp_power(self, p):
        self.lamp_power = p
        for ch in self.chunks.values():
            if ch.bulbs:
                ch.bulbs.set_shader_input('u_emit', p)

    def random_road_spot(self, rnd):
        cx, cz = rnd.randint(-3, 3), rnd.randint(-3, 3)
        return cx * BLOCK, cz * BLOCK + BLOCK / 2

    # ------------------------------------------------------------------ cones
    def update_cones(self, dt):
        for c in self.moving_cones[:]:
            c.vy -= 22 * dt
            c.x += c.vx * dt
            c.z += c.vz * dt
            c.y = max(0.0, c.y + c.vy * dt)
            if c.y <= 0.0:
                c.vy = -c.vy * 0.3 if abs(c.vy) > 2 else 0.0
                c.vx *= 0.85 ** (dt * 60)
                c.vz *= 0.85 ** (dt * 60)
                c.spin *= 0.9 ** (dt * 60)
            e = c.e
            e.position = (c.x, c.y, c.z)
            e.rotation_y += c.spin * dt
            e.rotation_z = min(90, e.rotation_z + abs(c.spin) * dt * 0.5)
            if abs(c.vx) + abs(c.vz) + abs(c.vy) < 0.1 and c.y <= 0:
                self.moving_cones.remove(c)

    def hit_cones(self, x, z, vx, vz, radius):
        hits = 0
        for ch in self.near_chunks(x, z):
            for c in ch.cones:
                if c.hit:
                    continue
                if (c.x - x) ** 2 + (c.z - z) ** 2 < radius * radius:
                    c.hit = True
                    c.vx = vx * 0.9 + random.uniform(-3, 3)
                    c.vz = vz * 0.9 + random.uniform(-3, 3)
                    c.vy = 4 + math.hypot(vx, vz) * 0.15
                    c.spin = random.uniform(-720, 720)
                    self.moving_cones.append(c)
                    hits += 1
        return hits

    # ------------------------------------------------------------------ generation
    def _build_chunk(self, cx, cz):
        rnd = random.Random((cx * 73856093) ^ (cz * 19349663) ^ self.seed)
        ch = Chunk()
        G, P, F, NE, BU = MeshBuilder(), MeshBuilder(), MeshBuilder(), MeshBuilder(), MeshBuilder()
        x0, z0 = cx * BLOCK, cz * BLOCK
        h = ROAD_W / 2

        # roads
        G.flat(x0 - h, z0 + h, x0 + h, z0 + BLOCK - h, 0, ASPHALT, 7)
        G.flat(x0 + h, z0 - h, x0 + BLOCK - h, z0 + h, 0, ASPHALT, 7)
        G.flat(x0 - h, z0 - h, x0 + h, z0 + h, 0, ASPHALT, 7)
        self._road_marks(P, x0, z0, h)

        bx0, bz0, bx1, bz1 = x0 + h, z0 + h, x0 + BLOCK - h, z0 + BLOCK - h
        if abs(cx) + abs(cz) == 0:
            kind = 'plaza'
        else:
            r = rnd.random()
            kind = 'city' if r < 0.62 else ('park' if r < 0.8 else 'plaza')
        ch.kind = kind

        if kind == 'plaza':
            G.flat(bx0, bz0, bx1, bz1, 0, ASPHALT_LOT, 7)
            self._plaza(ch, P, rnd, bx0, bz0, bx1, bz1)
            for (lx, lz) in ((bx0 + 1.2, bz0 + 1.2), (bx1 - 1.2, bz0 + 1.2), (bx0 + 1.2, bz1 - 1.2), (bx1 - 1.2, bz1 - 1.2)):
                self._lamp(ch, P, BU, lx, lz, 1 if lx < x0 + BLOCK / 2 else -1, 0)
        else:
            y = 0.14
            ch.raised = (bx0, bz0, bx1, bz1)
            G.flat(bx0, bz0, bx1, bz1, y, SIDEWALK_COL, 3)
            for (ax, az, bx, bz, n) in ((bx0, bz0, bx1, bz0, (0, 0, -1)), (bx1, bz0, bx1, bz1, (1, 0, 0)),
                                        (bx1, bz1, bx0, bz1, (0, 0, 1)), (bx0, bz1, bx0, bz0, (-1, 0, 0))):
                P.quad((ax, 0, az), (bx, 0, bz), (bx, y, bz), (ax, y, az), CURB, n)
            self._sidewalk_props(ch, P, BU, rnd, bx0, bz0, bx1, bz1, kind == 'city')
            ix0, iz0, ix1, iz1 = bx0 + SIDEWALK, bz0 + SIDEWALK, bx1 - SIDEWALK, bz1 - SIDEWALK
            if kind == 'city':
                self._city_block(ch, P, F, NE, rnd, ix0, iz0, ix1, iz1)
            else:
                self._park(ch, G, P, rnd, ix0, iz0, ix1, iz1)

        for mb, tex, emit in ((G, self.ground_tex, None), (P, None, None), (F, self.facade_tex, None),
                              (NE, None, 1.0), (BU, None, self.lamp_power)):
            m = mb.build()
            if m is None:
                continue
            e = Entity(model=m, shader=world_shader, double_sided=True)
            if tex:
                e.texture = tex
            if emit is not None:
                e.set_shader_input('u_emit', emit)
            if mb is BU:
                ch.bulbs = e
            ch.entities.append(e)
        return ch

    def _road_marks(self, P, x0, z0, h):
        y = 0.012
        a, b = z0 + h, z0 + BLOCK - h
        for s in (-1, 1):
            P.flat(x0 + s * 0.12 - 0.07, a, x0 + s * 0.12 + 0.07, b, y, PAINT_YELLOW)
            P.flat(x0 + s * (h - 0.8) - 0.08, a, x0 + s * (h - 0.8) + 0.08, b, y, PAINT_WHITE)
            z = a + 7
            while z < b - 7:
                P.flat(x0 + s * 6 - 0.08, z, x0 + s * 6 + 0.08, z + 3, y, PAINT_WHITE)
                z += 8
        a2, b2 = x0 + h, x0 + BLOCK - h
        for s in (-1, 1):
            P.flat(a2, z0 + s * 0.12 - 0.07, b2, z0 + s * 0.12 + 0.07, y, PAINT_YELLOW)
            P.flat(a2, z0 + s * (h - 0.8) - 0.08, b2, z0 + s * (h - 0.8) + 0.08, y, PAINT_WHITE)
            x = a2 + 7
            while x < b2 - 7:
                P.flat(x, z0 + s * 6 - 0.08, x + 3, z0 + s * 6 + 0.08, y, PAINT_WHITE)
                x += 8
        xs = x0 - h + 1.2
        while xs < x0 + h - 1:
            P.flat(xs, a + 1.0, xs + 0.6, a + 4.0, y, PAINT_WHITE)
            P.flat(xs, b - 4.0, xs + 0.6, b - 1.0, y, PAINT_WHITE)
            xs += 1.3
        zs = z0 - h + 1.2
        while zs < z0 + h - 1:
            P.flat(a2 + 1.0, zs, a2 + 4.0, zs + 0.6, y, PAINT_WHITE)
            P.flat(b2 - 4.0, zs, b2 - 1.0, zs + 0.6, y, PAINT_WHITE)
            zs += 1.3

    def _lamp(self, ch, P, BU, x, z, dx, dz):
        P.cyl(x, 0, z, 0.13, 0.08, 7.4, POLE, segs=7)
        ax, az = x + dx * 1.1, z + dz * 1.1
        P.box((x + ax) / 2, 7.35, (z + az) / 2, abs(dx) * 2.2 + 0.1, 0.1, abs(dz) * 2.2 + 0.1, POLE)
        P.box(ax, 7.25, az, 0.8 if dx else 0.45, 0.16, 0.45 if dx else 0.8, POLE)
        BU.box(ax, 7.14, az, 0.62 if dx else 0.34, 0.06, 0.34 if dx else 0.62, (1.0, 0.8, 0.55, 0))
        ch.lamps.append((ax, 6.8, az))
        ch.circles.append((x, z, 0.35))

    def _tree(self, ch, P, rnd, x, z, scale=1.0, y=0.14):
        th = rnd.uniform(2.2, 3.2) * scale
        P.cyl(x, y, z, 0.2 * scale, 0.13 * scale, th, BARK, segs=6, cap=False)
        g = (rnd.uniform(0.12, 0.2), rnd.uniform(0.3, 0.45), rnd.uniform(0.08, 0.14), 0.0)
        for k in range(rnd.randint(2, 3)):
            r = rnd.uniform(1.4, 2.0) * scale * (1 - k * 0.18)
            gg = (g[0] * (1 + k * 0.15), g[1] * (1 + k * 0.12), g[2], 0.0)
            P.ball(x + rnd.uniform(-0.4, 0.4), y + th + r * 0.5 + k * r * 0.7, z + rnd.uniform(-0.4, 0.4),
                   r, r * 0.85, r, gg, segs=7, rings=4, rnd=rnd, jitter=0.12)
        ch.circles.append((x, z, 0.45 * scale))

    def _sidewalk_props(self, ch, P, BU, rnd, bx0, bz0, bx1, bz1, trees):
        e = 1.2
        span = bx1 - bx0
        edges = (((bx0, bz0 + e), (1, 0), (0, -1)), ((bx1 - e, bz0), (0, 1), (1, 0)),
                 ((bx1, bz1 - e), (-1, 0), (0, 1)), ((bx0 + e, bz1), (0, -1), (-1, 0)))
        for (sx, sz), (ux, uz), (dx, dz) in edges:
            t = 12.0
            while t < span - 8:
                self._lamp(ch, P, BU, sx + ux * t, sz + uz * t, dx, dz)
                if trees and t + 12 < span - 4 and rnd.random() < 0.8:
                    self._tree(ch, P, rnd, sx + ux * (t + 12) - dx * 0.6, sz + uz * (t + 12) - dz * 0.6, 0.8)
                t += 24.0

    def _city_block(self, ch, P, F, NE, rnd, ix0, iz0, ix1, iz1):
        w, d = ix1 - ix0, iz1 - iz0
        layout = rnd.choice(['one', 'two', 'four', 'four', 'two'])
        lots = []
        if layout == 'one':
            lots = [(ix0, iz0, ix1, iz1)]
        elif layout == 'two':
            if rnd.random() < 0.5:
                m = ix0 + w * rnd.uniform(0.4, 0.6)
                lots = [(ix0, iz0, m, iz1), (m, iz0, ix1, iz1)]
            else:
                m = iz0 + d * rnd.uniform(0.4, 0.6)
                lots = [(ix0, iz0, ix1, m), (ix0, m, ix1, iz1)]
        else:
            mx, mz = ix0 + w * rnd.uniform(0.4, 0.6), iz0 + d * rnd.uniform(0.4, 0.6)
            lots = [(ix0, iz0, mx, mz), (mx, iz0, ix1, mz), (ix0, mz, mx, iz1), (mx, mz, ix1, iz1)]
        for (a, b, c, e) in lots:
            m = rnd.uniform(1.0, 3.0)
            self._building(ch, P, F, NE, rnd, a + m, b + m, c - m, e - m, layout)

    def _building(self, ch, P, F, NE, rnd, x0, z0, x1, z1, layout):
        y0 = 0.14
        big = layout == 'one' or rnd.random() < 0.25
        H = rnd.uniform(34, 72) if big else rnd.uniform(12, 32)
        H = y0 + round(H / 3.6) * 3.6 + 4.5
        tint = rnd.choice(BUILDING_TINTS)
        wall = (tint[0], tint[1], tint[2], 0.05)
        stone = (tint[0] * 0.55, tint[1] * 0.55, tint[2] * 0.55, 0.1)
        gf = y0 + 4.5
        P.box((x0 + x1) / 2, (y0 + gf) / 2, (z0 + z1) / 2, x1 - x0, gf - y0, z1 - z0, stone)
        for (ax, az, bx, bz, n) in ((x0, z1, x1, z1, (0, 0, 1)), (x1, z1, x1, z0, (1, 0, 0)),
                                    (x1, z0, x0, z0, (0, 0, -1)), (x0, z0, x0, z1, (-1, 0, 0))):
            L = math.hypot(bx - ax, bz - az)
            ux, uz = (bx - ax) / L, (bz - az) / L
            off = 0.03
            nx, nz = n[0] * off, n[2] * off
            t = 1.0
            while t < L - 2.0:
                seg = min(4.5, L - 1.0 - t)
                p0 = (ax + ux * t + nx, y0 + 0.5, az + uz * t + nz)
                p1 = (ax + ux * (t + seg) + nx, y0 + 0.5, az + uz * (t + seg) + nz)
                F.quad(p0, p1, (p1[0], y0 + 3.4, p1[2]), (p0[0], y0 + 3.4, p0[2]), (1, 1, 1, 0), n, (SHOP_UV,) * 4)
                t += seg + 1.0
            if rnd.random() < 0.5 and L > 10:
                s = rnd.uniform(2, L - 8)
                nc = rnd.choice(NEON)
                cxn, czn = ax + ux * (s + 3) + n[0] * 0.15, az + uz * (s + 3) + n[2] * 0.15
                NE.box(cxn, y0 + 4.0, czn, abs(ux) * 5 + abs(n[0]) * 0.1 + 0.05, 0.5, abs(uz) * 5 + abs(n[2]) * 0.1 + 0.05, nc)
        uoff, voff = rnd.randint(0, 7) / 8, rnd.randint(0, 7) / 8
        F.facade(x0, z0, x1, z1, gf, H, wall, uoff, voff)
        top = H
        roof = (tint[0] * 0.4, tint[1] * 0.4, tint[2] * 0.42, 0.05)
        P.flat(x0, z0, x1, z1, H, roof)
        for (a, b, c, e) in ((x0, z0, x1, z0 + 0.4), (x0, z1 - 0.4, x1, z1), (x0, z0, x0 + 0.4, z1), (x1 - 0.4, z0, x1, z1)):
            P.box((a + c) / 2, H + 0.5, (b + e) / 2, c - a, 1.0, e - b, stone)
        if big and (x1 - x0) > 16 and (z1 - z0) > 16:
            ins = rnd.uniform(3.5, 6)
            H2 = H + round(rnd.uniform(10, 26) / 3.6) * 3.6
            F.facade(x0 + ins, z0 + ins, x1 - ins, z1 - ins, H, H2, wall, (uoff + 0.25) % 1, voff)
            P.flat(x0 + ins, z0 + ins, x1 - ins, z1 - ins, H2, roof)
            top = H2
            cx_, cz_ = (x0 + x1) / 2, (z0 + z1) / 2
            P.cyl(cx_, H2, cz_, 0.15, 0.05, rnd.uniform(6, 14), POLE, segs=5)
        for _ in range(rnd.randint(1, 3)):
            sx, sz = rnd.uniform(1.5, 3.5), rnd.uniform(1.5, 3.5)
            px = rnd.uniform(x0 + 2 + sx / 2, x1 - 2 - sx / 2) if x1 - x0 > 5 + sx else (x0 + x1) / 2
            pz = rnd.uniform(z0 + 2 + sz / 2, z1 - 2 - sz / 2) if z1 - z0 > 5 + sz else (z0 + z1) / 2
            if top == H:
                P.box(px, H + 0.7, pz, sx, 1.4, sz, (0.55, 0.56, 0.58, 0.3))
        ch.boxes.append((x0, z0, x1, z1))

    def _park(self, ch, G, P, rnd, ix0, iz0, ix1, iz1):
        y = 0.16
        cxp, czp = (ix0 + ix1) / 2, (iz0 + iz1) / 2
        G.flat(ix0, iz0, ix1, iz1, y, GRASS, 4)
        G.flat(cxp - 2, iz0, cxp + 2, iz1, y + 0.01, SIDEWALK_COL, 3)
        G.flat(ix0, czp - 2, ix1, czp + 2, y + 0.01, SIDEWALK_COL, 3)
        P.cyl(cxp, y, czp, 4.2, 4.2, 0.6, (0.6, 0.6, 0.62, 0.1), segs=16)
        P.cyl(cxp, y + 0.62, czp, 3.8, 3.8, 0.0, (0.1, 0.25, 0.4, 1.0), segs=16)
        P.cyl(cxp, y, czp, 0.5, 0.3, 2.2, (0.6, 0.6, 0.62, 0.1), segs=8)
        ch.circles.append((cxp, czp, 4.4))
        placed = []
        for _ in range(60):
            if len(placed) > 12:
                break
            x, z = rnd.uniform(ix0 + 2, ix1 - 2), rnd.uniform(iz0 + 2, iz1 - 2)
            if abs(x - cxp) < 4.5 or abs(z - czp) < 4.5:
                continue
            if any((x - a) ** 2 + (z - b) ** 2 < 36 for a, b in placed):
                continue
            placed.append((x, z))
            self._tree(ch, P, rnd, x, z, rnd.uniform(0.9, 1.3), y)
        for s in (-1, 1):
            for bz in (czp - 12, czp + 12):
                P.box(cxp + s * 3.2, y + 0.25, bz, 0.5, 0.08, 2.2, (0.45, 0.3, 0.18, 0.2))
                P.box(cxp + s * 3.45, y + 0.5, bz, 0.08, 0.5, 2.2, (0.45, 0.3, 0.18, 0.2))

    def _plaza(self, ch, P, rnd, bx0, bz0, bx1, bz1):
        y = 0.012
        cxp, czp = (bx0 + bx1) / 2, (bz0 + bz1) / 2
        for r in (11.0, 20.0):
            segs = 40
            for s in range(segs):
                if s % 2:
                    continue
                a0, a1 = math.tau * s / segs, math.tau * (s + 1) / segs
                p = [(cxp + math.cos(a) * rr, y, czp + math.sin(a) * rr) for a, rr in ((a0, r - 0.15), (a1, r - 0.15), (a1, r + 0.15), (a0, r + 0.15))]
                P.quad(p[0], p[1], p[2], p[3], PAINT_YELLOW if r < 15 else PAINT_WHITE, (0, 1, 0))
        for i in range(10):
            x = bx0 + 6 + i * 6
            P.flat(x - 0.07, bz1 - 9, x + 0.07, bz1 - 3, y, PAINT_WHITE)
        cones = [(cxp + math.cos(math.tau * i / 8) * 11, czp + math.sin(math.tau * i / 8) * 11) for i in range(8)]
        cones += [(bx0 + 10 + i * 9, bz0 + 8) for i in range(6)]
        cones += [(cxp, czp)]
        for (x, z) in cones:
            e = Entity(position=(x, 0, z), shader=world_shader)
            self.cone_mesh.instance_to(e)
            ch.cones.append(Cone(e, x, z))
        for i in range(3):
            bx = bx1 - 4
            bz = bz0 + 16 + i * 4.2
            P.box(bx, 0.45, bz, 0.7, 0.9, 4.0, (0.7, 0.7, 0.68, 0.05), top=(0.75, 0.75, 0.73, 0.05))
            P.box(bx, 0.62, bz, 0.72, 0.18, 4.02, (0.85, 0.1, 0.08, 0.2))
            ch.boxes.append((bx - 0.35, bz - 2.0, bx + 0.35, bz + 2.0))
