"""Player scooter: drift + wheelie physics, collisions, scoring, particles, skid marks, sound."""
import math
import random
import struct
import wave

from panda3d.core import (BitMask32, Filename, Geom, GeomNode, GeomTriangles, GeomVertexData, GeomVertexFormat,
                          GeomVertexWriter, OmniBoundingVolume, TransparencyAttrib)
from ursina import Audio, Entity, Vec3, Vec4, application, color, held_keys, scene

from .scooters import SCOOTERS
from .core import CACHE_DIR, clamp, lerp, make_soft_texture

SHADOW_CAM = BitMask32.bit(1)
GRADES = {
    'DRIFT': [(500, 'DRIFT'), (1500, 'DOBRY DRIFT'), (4000, 'ŚWIETNY DRIFT!'), (10000, 'SZALONY DRIFT!!'), (1e18, 'LEGENDARNY!!!')],
    'WHEELIE': [(500, 'WHEELIE'), (1500, 'DOBRE WHEELIE'), (4000, 'ŚWIETNE WHEELIE!'), (10000, 'SZALONE WHEELIE!!'), (1e18, 'LEGENDA KOŁA!!!')],
    'WHEELIE DRIFT': [(1500, 'WHEELIE DRIFT'), (5000, 'WHEELIE DRIFT!!'), (1e18, 'KRÓL ULICY!!!')],
}


# ---------------------------------------------------------------------------
#   EFFECTS
# ---------------------------------------------------------------------------

class SkidMarks:
    """Ring buffer of quads in one dynamic Geom."""

    def __init__(self, n=1500):
        self.n = n
        self.i = 0
        self.vdata = GeomVertexData('skid', GeomVertexFormat.get_v3c4(), Geom.UH_dynamic)
        self.vdata.set_num_rows(n * 4)
        tris = GeomTriangles(Geom.UH_static)
        for k in range(n):
            b = k * 4
            tris.add_vertices(b, b + 1, b + 2)
            tris.add_vertices(b, b + 2, b + 3)
        geom = Geom(self.vdata)
        geom.add_primitive(tris)
        node = GeomNode('skidmarks')
        node.add_geom(geom)
        node.set_bounds(OmniBoundingVolume())
        node.set_final(True)
        self.np = scene.attach_new_node(node)
        self.np.set_transparency(TransparencyAttrib.M_alpha)
        self.np.set_depth_write(False)
        self.np.set_light_off()
        self.np.set_two_sided(True)
        self.np.set_bin('transparent', 5)
        self.np.hide(SHADOW_CAM)

    def add(self, a, b, half_w, alpha):
        dx, dz = b[0] - a[0], b[2] - a[2]
        l = math.hypot(dx, dz)
        if l < 0.05 or l > 3:
            return
        px, pz = -dz / l * half_w, dx / l * half_w
        vw = GeomVertexWriter(self.vdata, 'vertex')
        cw = GeomVertexWriter(self.vdata, 'color')
        vw.set_row(self.i * 4)
        cw.set_row(self.i * 4)
        for (x, y, z) in ((a[0] - px, a[1], a[2] - pz), (a[0] + px, a[1], a[2] + pz),
                          (b[0] + px, b[1], b[2] + pz), (b[0] - px, b[1], b[2] - pz)):
            vw.set_data3f(x, y, z)
            cw.set_data4f(0.02, 0.02, 0.02, alpha)
        self.i = (self.i + 1) % self.n

    def clear(self):
        vw = GeomVertexWriter(self.vdata, 'vertex')
        for _ in range(self.n * 4):
            vw.set_data3f(0, -10, 0)


class Particles:
    def __init__(self):
        soft = make_soft_texture(64, 1.4)
        self.smoke = []
        for _ in range(110):
            e = Entity(model='quad', texture=soft, billboard=True, enabled=False)
            e.setLightOff()
            e.set_depth_write(False)
            e.hide(SHADOW_CAM)
            e.data = [0.0, 1.0, 0.0, 0.0, 0.0, 1.0]  # life, max, vx, vy, vz, size
            self.smoke.append(e)
        self.sparks = []
        for _ in range(60):
            e = Entity(model='quad', texture=soft, billboard=True, enabled=False, scale=0.12)
            e.setLightOff()
            e.set_depth_write(False)
            e.hide(SHADOW_CAM)
            e.data = [0.0, 1.0, 0.0, 0.0, 0.0]
            self.sparks.append(e)
        self.si = 0
        self.pi = 0
        self.brightness = 1.0

    def smoke_at(self, x, y, z, vx, vz, size=1.0):
        e = self.smoke[self.si]
        self.si = (self.si + 1) % len(self.smoke)
        life = random.uniform(1.4, 2.6)
        e.data[:] = [life, life, vx * 0.3 + random.uniform(-0.8, 0.8), random.uniform(0.5, 1.3),
                     vz * 0.3 + random.uniform(-0.8, 0.8), size * random.uniform(0.9, 1.4)]
        e.position = (x, y, z)
        e.enabled = True

    def sparks_at(self, x, y, z, nx, nz, n=12):
        for _ in range(n):
            e = self.sparks[self.pi]
            self.pi = (self.pi + 1) % len(self.sparks)
            life = random.uniform(0.25, 0.6)
            sp = random.uniform(4, 11)
            e.data[:] = [life, life, nx * sp + random.uniform(-4, 4), random.uniform(2, 7), nz * sp + random.uniform(-4, 4)]
            e.position = (x, y, z)
            e.enabled = True

    def update(self, dt):
        b = self.brightness
        for e in self.smoke:
            if not e.enabled:
                continue
            d = e.data
            d[0] -= dt
            if d[0] <= 0:
                e.enabled = False
                continue
            t = 1 - d[0] / d[1]
            e.x += d[2] * dt
            e.y += d[3] * dt
            e.z += d[4] * dt
            d[2] *= 0.98
            d[4] *= 0.98
            s = d[5] * (0.8 + t * 3.2)
            e.scale = (s, s)
            e.color = Vec4(0.86 * b, 0.86 * b, 0.88 * b, 0.3 * (1 - t) * min(1.0, t * 8))
        for e in self.sparks:
            if not e.enabled:
                continue
            d = e.data
            d[0] -= dt
            if d[0] <= 0:
                e.enabled = False
                continue
            d[3] -= 20 * dt
            e.x += d[2] * dt
            e.y = max(0.05, e.y + d[3] * dt)
            e.z += d[4] * dt
            k = d[0] / d[1]
            e.color = Vec4(1.0, 0.55 + 0.4 * k, 0.15, k)

    def clear(self):
        for e in self.smoke + self.sparks:
            e.enabled = False


# ---------------------------------------------------------------------------
#   PROCEDURAL SOUND
# ---------------------------------------------------------------------------

RATE = 22050


def _write_wav(path, samples):
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b''.join(struct.pack('<h', int(clamp(s, -1, 1) * 32000)) for s in samples))


def _gen_motor():
    """Electric hub-motor whine: 1 s seamless loop (integer frequencies)."""
    rnd = random.Random(1)
    out = []
    for i in range(RATE):
        t = i / RATE
        v = (0.5 * math.sin(math.tau * 110 * t) + 0.35 * math.sin(math.tau * 220 * t + 1.3)
             + 0.3 * math.sin(math.tau * 660 * t + 0.4) + 0.22 * math.sin(math.tau * 1320 * t + 2.1)
             + 0.12 * math.sin(math.tau * 2640 * t))
        v *= 0.85 + 0.15 * math.sin(math.tau * 12 * t)
        out.append(v * 0.3 + rnd.uniform(-0.03, 0.03))
    return out


def _gen_screech():
    rnd = random.Random(2)
    out = []
    for i in range(RATE):
        t = i / RATE
        v = (math.sin(math.tau * 1850 * t + 3 * math.sin(math.tau * 5 * t))
             + 0.7 * math.sin(math.tau * 2310 * t + 4 * math.sin(math.tau * 7 * t))
             + 0.5 * math.sin(math.tau * 2890 * t + 2 * math.sin(math.tau * 3 * t)))
        out.append(v * 0.2 + rnd.uniform(-0.12, 0.12))
    return out


def _gen_crash():
    rnd = random.Random(3)
    out = []
    lp = 0.0
    for i in range(int(RATE * 0.6)):
        t = i / RATE
        lp += (rnd.uniform(-1, 1) - lp) * 0.25
        v = lp * math.exp(-t * 7) * 1.6 + math.sin(math.tau * 55 * t) * math.exp(-t * 9) * 0.8
        out.append(v)
    return out


def _gen_tone(freqs, dur=0.12, decay=18.0, vol=0.5):
    out = []
    seg = dur / len(freqs)
    for i in range(int(RATE * dur)):
        t = i / RATE
        f = freqs[min(len(freqs) - 1, int(t / seg))]
        lt = t % seg
        out.append(math.sin(math.tau * f * t) * math.exp(-lt * decay) * vol)
    return out


class Sound:
    def __init__(self, volume=0.7):
        self.volume = volume
        CACHE_DIR.mkdir(exist_ok=True)
        gens = {'motor': _gen_motor, 'screech': _gen_screech, 'crash': _gen_crash,
                'click': lambda: _gen_tone([1300], 0.06, 50, 0.35),
                'select': lambda: _gen_tone([880, 1320], 0.14, 25, 0.35),
                'score': lambda: _gen_tone([660, 880, 1320], 0.36, 12, 0.4),
                'lost': lambda: _gen_tone([440, 300], 0.3, 10, 0.35)}
        self.clips = {}
        for name, fn in gens.items():
            p = CACHE_DIR / f'{name}.wav'
            if not p.exists():
                _write_wav(p, fn())
            self.clips[name] = p
        self.sfx = {}
        self.engine = self._loop('motor')
        self.screech = self._loop('screech')

    def _load(self, name):
        return application.base.loader.loadSfx(Filename.from_os_specific(str(self.clips[name])))

    def _loop(self, name):
        a = Audio(self._load(name), loop=True, autoplay=True, volume=0)
        return a

    def play(self, name, vol=1.0, pitch=1.0):
        s = self.sfx.get(name)
        if s is None:
            s = self.sfx[name] = self._load(name)
        s.stop()
        s.set_volume(vol * self.volume)
        s.set_play_rate(pitch)
        s.play()

    def set_engine(self, ratio, throttle, slide, speed, active):
        if not active:
            self.engine.volume = 0
            self.screech.volume = 0
            return
        self.engine.pitch = 0.35 + ratio * 1.25 + throttle * 0.08
        self.engine.volume = self.volume * (0.12 + 0.25 * throttle + 0.2 * ratio)
        self.screech.volume = self.volume * clamp(slide * min(1.0, speed / 12), 0, 1) * 0.4
        self.screech.pitch = 1.0 + min(speed, 30) / 150


# ---------------------------------------------------------------------------
#   PLAYER SCOOTER
# ---------------------------------------------------------------------------

class PlayerCar:
    """Player scooter (the name is kept so the game loop stays vehicle-agnostic)."""

    def __init__(self, game, visual):
        self.game = game
        self.visual = visual
        self.skids = SkidMarks()
        self.fx = Particles()
        self.headlights = True
        self.first_person = False
        self.reset(0, 40, 0)

    @property
    def spec(self):
        return SCOOTERS[self.visual.spec_index]

    def reset(self, x, z, heading):
        self.respawn(x, z, heading)
        self.nitro = 100.0
        self.score = 0
        self.mult = 1
        self.chain = 0.0
        self.best_drift = 0

    def respawn(self, x, z, heading):
        self.x, self.z, self.y = x, z, 0.0
        self.heading = heading
        self.vx = self.vz = 0.0
        self.yaw = 0.0
        self.steer = 0.0
        self.slide = 0.0
        self.slip = 0.0
        self.speed = 0.0
        self.vl = 0.0
        self.ratio = 0.0
        self.nitro_on = False
        self.throttle = 0.0
        self.braking = False
        self.lean = 0.0
        self.lean_fwd = 0.0
        self.wheelie = 0.0
        self.wheelie_v = 0.0
        self.last_skid = [None]
        self.smoke_acc = 0.0
        self.drift_pts = 0.0
        self.drift_time = 0.0
        self.drift_grace = 0.0
        self.trick = 'DRIFT'
        self.near = False
        self.drifting = False
        self.wheelie_on = False
        self.crash_cool = 0.0
        self.visual.position = (x, 0, z)
        self.visual.rotation_y = heading

    # --------------------------------------------------------------- input
    def read_input(self):
        thr = max(held_keys['w'], held_keys['up arrow'], held_keys['gamepad right trigger'])
        brk = max(held_keys['s'], held_keys['down arrow'], held_keys['gamepad left trigger'])
        st = (held_keys['d'] + held_keys['right arrow']) - (held_keys['a'] + held_keys['left arrow'])
        pad = held_keys['gamepad left stick x']
        if abs(pad) > 0.12:
            st = pad
        hb = held_keys['space'] or held_keys['gamepad a']
        nos = held_keys['left shift'] or held_keys['right shift'] or held_keys['gamepad x']
        wh = held_keys['left control'] or held_keys['right control'] or held_keys['control'] or held_keys['gamepad b']
        return clamp(thr, 0, 1), clamp(brk, 0, 1), clamp(st, -1, 1), bool(hb), bool(nos), bool(wh)

    def shift(self, d):
        pass

    # --------------------------------------------------------------- physics
    def update(self, dt, controls=True):
        spec = self.spec
        thr, brk, st_in, hb, nos, wh = self.read_input() if controls else (0, 0, 0, False, False, False)
        self.throttle = thr
        h = math.radians(self.heading)
        fx, fz = math.sin(h), math.cos(h)
        rx, rz = math.cos(h), -math.sin(h)
        vl = self.vx * fx + self.vz * fz
        vs = self.vx * rx + self.vz * rz
        speed = math.hypot(self.vx, self.vz)

        in_wheelie = self.wheelie > 8
        self.steer += (st_in - self.steer) * min(1.0, dt * (7.0 if st_in else 9.0))
        slip = math.degrees(math.atan2(vs, max(abs(vl), 1.0)))
        self.slip = slip

        target = 0.0
        if hb and speed > 4:
            target = 1.0
        elif thr > 0.6 and abs(self.steer) > 0.6 and speed > 12:
            target = spec['power_slide'] * 0.75
        if abs(slip) > 8 and thr > 0.3 and speed > 5:
            target = max(target, 0.5 + 0.4 * spec['power_slide'])
        if speed < 2.5:
            target = 0.0
        up = target > self.slide
        self.slide += (target - self.slide) * min(1.0, dt * (5.0 if up else (1.4 if thr > 0.3 else 2.8)))
        grip = lerp(spec['grip'], spec['drift_grip'], self.slide)
        vs *= math.exp(-grip * dt)

        # electric motor: strong torque, controller-limited top speed
        vmax = spec['vmax_kmh'] / 3.6 * (1.15 if self.nitro_on else 1.0)
        self.ratio = clamp(abs(vl) / (spec['vmax_kmh'] / 3.6), 0, 1.2)
        self.rpm = 900 + 7100 * min(self.ratio, 1.0)
        self.nitro_on = nos and self.nitro > 0 and thr > 0.1
        if self.nitro_on:
            self.nitro = max(0.0, self.nitro - 28 * dt)
        else:
            self.nitro = min(100.0, self.nitro + (12.0 if (self.drifting or self.wheelie_on) else 3.0) * dt)

        acc = 0.0
        if thr > 0:
            acc += thr * spec['accel'] * (1.3 if self.nitro_on else 1.0) * clamp(6.0 * (1 - vl / (vmax * 1.03)), 0, 1)
        self.braking = False
        if brk > 0:
            if vl > 0.6:
                acc -= brk * 10
                self.braking = True
            elif vl > -4:
                acc -= brk * 3
        acc -= 0.02 * vl + 0.0015 * vl * abs(vl)
        if hb:
            acc -= math.copysign(3.0, vl) if abs(vl) > 0.5 else 0
        acc -= math.copysign(abs(math.sin(math.radians(slip))) * 3.5, vl) if abs(vl) > 0.5 else 0
        vl += acc * dt
        if brk > 0 and not self.braking and acc < 0 and 0 < vl < 0.3:
            vl = 0.0

        # wheelie: spring towards a balance angle while CTRL is held
        w_target = 0.0
        if wh and vl > 2.0 and not self.braking:
            w_target = 34 + 4 * math.sin(self.game.clock * 2.3) + thr * 4
        k, c = (40.0, 8.0) if w_target > 0 else (55.0, 6.0)
        self.wheelie_v += (k * (w_target - self.wheelie) - c * self.wheelie_v) * dt
        self.wheelie += self.wheelie_v * dt
        if self.wheelie > 62:
            self.wheelie, self.wheelie_v = 62, 0.0
        if self.wheelie < 0:
            if self.wheelie_v < -60:
                self.game.on_land(-self.wheelie_v)
            self.wheelie = 0.0
            self.wheelie_v = -self.wheelie_v * 0.2 if self.wheelie_v < -60 else 0.0

        steer_auth = 0.45 if in_wheelie else 1.0
        max_steer = spec['steer'] * (1 - 0.7 * min(speed / 25, 1)) * steer_auth
        steer_deg = self.steer * max_steer
        wb = self.visual.info['front_z'] - self.visual.info['rear_z']
        r_kin = math.degrees(vl / wb * math.tan(math.radians(steer_deg)))
        lim = math.degrees(spec['grip'] * 1.25 / max(speed, 3.0))
        r_kin = clamp(r_kin, -lim, lim)
        assist = 4.0 * clamp((abs(slip) - 38) / 25, 0, 1)
        r_drift = self.steer * spec['drift_yaw'] * min(1.0, speed / 10) + slip * (1.6 - 1.1 * thr + assist)
        r_target = lerp(r_kin, r_drift, self.slide)
        self.yaw += (r_target - self.yaw) * min(1.0, dt * lerp(12, 6.5, self.slide))
        self.heading = (self.heading + self.yaw * dt) % 360

        self.vx = fx * vl + rx * vs
        self.vz = fz * vl + rz * vs
        self.x += self.vx * dt
        self.z += self.vz * dt
        self.vl = vl
        self.speed = speed

        self.collide(dt)
        gy = self.game.world.ground_height(self.x, self.z)
        self.y += (gy - self.y) * min(1.0, dt * 14)

        # lean into the turn like a bike; body tucks forward under throttle
        lat = math.radians(self.yaw) * speed
        target_lean = clamp(math.degrees(math.atan2(lat, 9.81)) * 0.8, -32, 32)
        self.lean += (target_lean - self.lean) * min(1.0, dt * 6)
        self.lean_fwd += (clamp(acc * 1.2, -8, 10) - self.lean_fwd) * min(1.0, dt * 4)
        spin = vl / self.visual.info['wheel_r'] * 57.3 * dt
        v = self.visual
        v.position = (self.x, self.y, self.z)
        v.rotation_y = self.heading
        v.update_visual(steer_deg if abs(slip) < 8 else -slip * 0.4 + steer_deg * 0.6, -spin, self.lean, self.wheelie,
                        self.headlights, self.braking or (brk > 0 and speed > 1), self.nitro_on, self.game.clock,
                        speed * 3.6, self.first_person, dt, self.lean_fwd)
        self.effects(dt, slip, speed, thr, brk)
        self.scoring(dt, slip, speed)
        self.fx.update(dt)

    # --------------------------------------------------------------- collisions
    def collide(self, dt):
        info = self.visual.info
        r = info['W'] * 0.5
        h = math.radians(self.heading)
        fx, fz = math.sin(h), math.cos(h)
        offs = (-info['L'] * 0.3, 0.0, info['L'] * 0.3)
        world = self.game.world
        self.crash_cool -= dt
        near = False
        for ch in world.near_chunks(self.x, self.z):
            for (x0, z0, x1, z1) in ch.boxes:
                if self.x < x0 - 6 or self.x > x1 + 6 or self.z < z0 - 6 or self.z > z1 + 6:
                    continue
                for o in offs:
                    cx, cz = self.x + fx * o, self.z + fz * o
                    px, pz = clamp(cx, x0, x1), clamp(cz, z0, z1)
                    dx, dz = cx - px, cz - pz
                    d2 = dx * dx + dz * dz
                    if d2 < (r + 2.0) ** 2:
                        near = True
                    if d2 >= r * r:
                        continue
                    if d2 < 1e-8:
                        dists = ((cx - x0, -1, 0), (x1 - cx, 1, 0), (cz - z0, 0, -1), (z1 - cz, 0, 1))
                        dmin, nx, nz = min(dists)
                        pen = r + dmin
                    else:
                        d = math.sqrt(d2)
                        nx, nz = dx / d, dz / d
                        pen = r - d
                    self._resolve(nx, nz, pen, cx - nx * r, cz - nz * r, o)
            for (x, z, cr) in ch.circles:
                if abs(self.x - x) > 6 or abs(self.z - z) > 6:
                    continue
                for o in offs:
                    cx, cz = self.x + fx * o, self.z + fz * o
                    dx, dz = cx - x, cz - z
                    d2 = dx * dx + dz * dz
                    rr = r + cr
                    if d2 < (rr + 1.3) ** 2:
                        near = True
                    if d2 >= rr * rr or d2 < 1e-8:
                        continue
                    d = math.sqrt(d2)
                    nx, nz = dx / d, dz / d
                    self._resolve(nx, nz, rr - d, x + nx * cr, z + nz * cr, o)
        self.near = near
        hits = world.hit_cones(self.x + fx * info['L'] * 0.4, self.z + fz * info['L'] * 0.4, self.vx, self.vz, 0.7)
        hits += world.hit_cones(self.x, self.z, self.vx, self.vz, 0.6)
        if hits:
            self.game.on_cones(hits)

    def _resolve(self, nx, nz, pen, px, pz, offset):
        self.x += nx * pen
        self.z += nz * pen
        vn = self.vx * nx + self.vz * nz
        if vn >= 0:
            return
        e = 0.3
        jx, jz = -(1 + e) * vn * nx, -(1 + e) * vn * nz
        self.vx += jx
        self.vz += jz
        self.vx *= 0.9
        self.vz *= 0.9
        h = math.radians(self.heading)
        lx, lz = math.sin(h) * offset, math.cos(h) * offset
        self.yaw += (lz * jx - lx * jz) * 14
        strength = -vn
        if strength > 2.5 and self.crash_cool <= 0:
            self.crash_cool = 0.25
            self.wheelie_v -= strength * 6
            self.fx.sparks_at(px, self.y + 0.4, pz, nx, nz, int(clamp(strength * 2, 6, 20)))
            self.game.on_crash(strength)

    # --------------------------------------------------------------- effects
    def effects(self, dt, slip, speed, thr, brk):
        info = self.visual.info
        h = math.radians(self.heading)
        fx, fz = math.sin(h), math.cos(h)
        sliding = (abs(slip) > 9 and speed > 4) or (self.braking and speed > 10 and brk > 0.8)
        p = (self.x + fx * info['rear_z'], self.y + 0.02, self.z + fz * info['rear_z'])
        prev = self.last_skid[0]
        if sliding:
            if prev is not None:
                self.skids.add(prev, p, 0.05, clamp(0.3 + abs(slip) / 60, 0.3, 0.7))
            self.last_skid[0] = p
        else:
            self.last_skid[0] = None
        if sliding and abs(slip) > 12:
            self.smoke_acc += dt * (8 + speed * 0.8) * min(1.0, abs(slip) / 30)
            while self.smoke_acc > 1:
                self.smoke_acc -= 1
                self.fx.smoke_at(p[0], p[1] + 0.15, p[2], self.vx, self.vz, 0.35 + min(speed, 25) / 60)
        elif speed < 4 and thr > 0.8 and brk > 0.5:
            self.smoke_acc += dt * 14
            while self.smoke_acc > 1:
                self.smoke_acc -= 1
                self.fx.smoke_at(p[0], p[1] + 0.15, p[2], 0, 0, 0.4)

    # --------------------------------------------------------------- scoring
    def scoring(self, dt, slip, speed):
        drifting = abs(slip) > 11 and speed > 7 and abs(self.vl) > 2.5
        wheelie_on = self.wheelie > 14 and speed > 3
        self.drifting = drifting
        self.wheelie_on = wheelie_on
        if drifting or wheelie_on:
            near = 1.5 if self.near else 1.0
            if drifting:
                self.drift_pts += abs(min(slip, 70)) * speed * 0.3 * dt * near
            if wheelie_on:
                self.drift_pts += (12 + speed * 3.6 * 1.3) * dt * near * (2.0 if drifting else 1.0)
            trick = 'WHEELIE DRIFT' if drifting and wheelie_on else ('WHEELIE' if wheelie_on else 'DRIFT')
            if self.trick != 'WHEELIE DRIFT':
                self.trick = trick
            self.drift_time += dt
            self.drift_grace = 0.7
            self.chain = 3.2
        elif self.drift_pts > 0:
            self.drift_grace -= dt
            if self.drift_grace <= 0:
                self.bank()
        else:
            if self.chain > 0:
                self.chain -= dt
                if self.chain <= 0 and self.mult > 1:
                    self.mult = 1
                    self.game.on_combo_lost()

    def bank(self):
        pts = int(self.drift_pts * self.mult)
        if pts >= 50:
            self.score += pts
            self.best_drift = max(self.best_drift, pts)
            grade = next(g for lim, g in GRADES[self.trick] if pts < lim)
            self.game.on_drift_end(pts, grade, self.mult)
            if self.drift_pts > 250:
                self.mult = min(5, self.mult + 1)
        self.drift_pts = 0.0
        self.drift_time = 0.0
        self.trick = 'DRIFT'

    def fail_drift(self):
        if self.drift_pts > 50:
            self.game.on_drift_failed(int(self.drift_pts * self.mult))
        self.drift_pts = 0.0
        self.drift_time = 0.0
        self.mult = 1
        self.chain = 0.0
        self.trick = 'DRIFT'
