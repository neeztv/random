"""
DRIFT CITY 2.0

Uruchomienie:
    pip install -r requirements.txt
    python main.py

Sterowanie:
    W / ↑        gaz                 SPACJA   ręczny (drift)
    S / ↓        hamulec / wsteczny  SHIFT    nitro
    A D / ← →    skręt               Q / E    biegi (tryb manual)
    C kamera   L światła   T pora dnia   R reset   TAB HUD   ESC pauza   F11 pełny ekran
Pad: lewa gałka = skręt, triggery = gaz/hamulec, A = ręczny, X = nitro, START = pauza.
"""
import math
import random

from panda3d.core import BitMask32, loadPrcFileData
from ursina import Entity, Ursina, Vec3, Vec4, application, camera, scene, time, window

loadPrcFileData('', 'framebuffer-multisample 1\nmultisamples 4')
app = Ursina(title='DRIFT CITY', development_mode=False)
window.exit_button.visible = False
window.fps_counter.enabled = True
window.color = Vec4(0, 0, 0, 1)

from game.cars import CARS, PAINTS, CarVisual  # noqa: E402
from game.core import (TIME_ORDER, TIME_PRESETS, BLOCK, MeshBuilder, clamp, lerp, load_save, post_shader,  # noqa: E402
                       world_shader, write_save)
from game.ui import ACC, ACC2, GOLD, HUD, WHITE, Controls, Garage, MainMenu, Pause, Results, Settings  # noqa: E402
from game.vehicle import PlayerCar, Sound  # noqa: E402
from game.world import Environment, World  # noqa: E402

PODIUM = Vec3(26, 0, 62)
START = (30.0, 30.0, 45.0)
CHALLENGE_TIME = 180.0


def angle_diff(a, b):
    return (b - a + 180) % 360 - 180


class CameraRig:
    MODES = ['POŚCIGOWA', 'DALEKA', 'MASKA', 'KINOWA']

    def __init__(self):
        self.pos = Vec3(0, 5, -10)
        self.yaw = 0.0
        self.fov = 80.0
        self.shake = 0.0
        self.mode = 0
        self.orbit = 0.0

    def snap(self, car):
        self.yaw = car.heading
        h = math.radians(self.yaw)
        self.pos = Vec3(car.x - math.sin(h) * 7, car.y + 2.5, car.z - math.cos(h) * 7)

    def update(self, dt, car, clock):
        speed = car.speed
        h = math.radians(car.heading)
        fwd = Vec3(math.sin(h), 0, math.cos(h))
        cp = Vec3(car.x, car.y, car.z)
        vel_yaw = math.degrees(math.atan2(car.vx, car.vz)) if speed > 2 and car.vl > -1 else car.heading
        target = car.heading + angle_diff(car.heading, vel_yaw) * 0.6
        self.yaw += angle_diff(self.yaw, target) * min(1.0, dt * 3.5)
        y = math.radians(self.yaw)
        if self.mode in (0, 1):
            d = (6.6 if self.mode == 0 else 10.5) + min(speed, 60) * 0.04
            ht = (2.2 if self.mode == 0 else 3.8) + min(speed, 60) * 0.01
            want = cp + Vec3(-math.sin(y) * d, ht, -math.cos(y) * d)
            self.pos = lerp(self.pos, want, min(1.0, dt * 9))
            look = cp + fwd * 2.2 + Vec3(0, 0.95, 0)
        elif self.mode == 2:
            self.pos = cp + fwd * 0.2 + Vec3(0, 1.28, 0)
            look = self.pos + fwd * 10 + Vec3(0, -0.4, 0)
        else:
            self.orbit += dt * 14
            a = math.radians(self.orbit)
            want = cp + Vec3(math.sin(a) * 9, 1.6 + math.sin(a * 0.5) * 0.8, math.cos(a) * 9)
            self.pos = lerp(self.pos, want, min(1.0, dt * 4))
            look = cp + Vec3(0, 0.7, 0)
        self.shake = max(0.0, self.shake - dt * 2.2)
        s = self.shake * self.shake * 0.35
        off = Vec3(random.uniform(-s, s), random.uniform(-s, s), random.uniform(-s, s))
        camera.position = self.pos + off
        camera.lookAt(look + off * 0.5, Vec3(0, 1, 0))
        fov = (78 if self.mode != 2 else 84) + min(speed, 70) * 0.22 + (9 if car.nitro_on else 0)
        self.fov += (fov - self.fov) * min(1.0, dt * 3)
        camera.fov = self.fov

    def showcase(self, dt, center, radius, height, shift, speed=8.0):
        self.orbit += dt * speed
        a = math.radians(self.orbit)
        pos = center + Vec3(math.sin(a) * radius, height, math.cos(a) * radius)
        self.pos = lerp(self.pos, pos, min(1.0, dt * 3))
        camera.position = self.pos
        fwd = (center - self.pos).normalized()
        right = Vec3(fwd.z, 0, -fwd.x).normalized()
        camera.lookAt(center + Vec3(0, 0.75, 0) - right * shift, Vec3(0, 1, 0))
        self.fov += (62 - self.fov) * min(1.0, dt * 3)
        camera.fov = self.fov


class Game(Entity):
    def __init__(self):
        super().__init__()
        self.save = load_save()
        self.clock = 0.0
        self.mode = 'free'
        self.state = None
        self.time_left = None
        self.countdown = 0.0
        self.record_announced = False
        self.post = False
        self.flash = 0.0
        application.base.cam.node().set_camera_mask(BitMask32.bit(0))
        camera.clip_plane_far = 1600

        self.sound = Sound(self.save['volume'])
        self.env = Environment(self.save['time'], shadows=self.save['quality'] != 'low')
        self.world = World()
        self.world.set_lamp_power(TIME_PRESETS[self.save['time']]['lamps'])
        self.world.build_all(PODIUM.x, PODIUM.z)
        self._podium()

        ci = self.save['car']
        self.visual = CarVisual(ci, self.save['paint'][ci])
        self.car = PlayerCar(self, self.visual)
        self.car.manual = self.save['gearbox'] == 'manual'
        self.rig = CameraRig()
        self.rig.mode = self.save['camera']
        self.hud = HUD(self)
        self.screens = {'menu': MainMenu(self), 'garage': Garage(self), 'settings': Settings(self),
                        'controls': Controls(self), 'pause': Pause(self), 'results': Results(self)}
        self.fade = Entity(parent=camera.ui, model='quad', scale=(4, 2), z=-50, color=Vec4(0, 0, 0, 1))
        self.fade_a = 1.0
        self.apply_quality(self.save['quality'])
        self.goto('menu')

    # ------------------------------------------------------------------ scene helpers
    def _podium(self):
        mb = MeshBuilder()
        mb.cyl(PODIUM.x, 0, PODIUM.z, 3.4, 3.3, 0.14, (0.05, 0.05, 0.06, 0.9), segs=40)
        ring = MeshBuilder()
        segs = 48
        for s in range(segs):
            a0, a1 = math.tau * s / segs, math.tau * (s + 1) / segs
            p = [(PODIUM.x + math.cos(a) * r, 0.145, PODIUM.z + math.sin(a) * r) for a, r in ((a0, 3.0), (a1, 3.0), (a1, 3.15), (a0, 3.15))]
            ring.quad(p[0], p[1], p[2], p[3], (1.0, 0.3, 0.1, 0), (0, 1, 0))
        self.podium = Entity(model=mb.build(), shader=world_shader, double_sided=True)
        self.podium_ring = Entity(model=ring.build(), shader=world_shader, double_sided=True)
        self.podium_ring.set_shader_input('u_emit', 1.0)

    def place_on_podium(self):
        self.car.reset(PODIUM.x, PODIUM.z, 150)
        self.car.y = 0.14
        self.visual.position = (PODIUM.x, 0.14, PODIUM.z)
        self.podium.enabled = self.podium_ring.enabled = True

    # ------------------------------------------------------------------ state machine
    def goto(self, name, from_pause=False):
        prev = self.state
        for s in self.screens.values():
            s.hide()
        if name in ('menu', 'garage', 'controls') or (name == 'settings' and not from_pause):
            self.hud.hide()
            if prev in ('play', 'pause', 'results', None):
                self.end_session()
                self.place_on_podium()
                self.fade_a = max(self.fade_a, 0.8)
        if name == 'settings':
            self.screens['settings'].return_to = 'pause' if from_pause else 'menu'
        self.state = name
        if name in self.screens:
            self.screens[name].show()
            if name == 'pause':
                self.screens[name].sel = 0

    def start(self, mode):
        self.mode = mode
        for s in self.screens.values():
            s.hide()
        self.podium.enabled = self.podium_ring.enabled = False
        self.car.skids.clear()
        self.car.fx.clear()
        self.car.reset(*START)
        self.car.manual = self.save['gearbox'] == 'manual'
        self.world.build_all(START[0], START[1])
        self.rig.snap(self.car)
        self.record_announced = False
        self.hud.show()
        self.state = 'play'
        self.fade_a = 1.0
        if mode == 'challenge':
            self.time_left = CHALLENGE_TIME
            self.countdown = 3.5
        else:
            self.time_left = None
            self.countdown = 0.0
            self.hud.popup('WOLNA JAZDA', 'SPACJA = ręczny  •  SHIFT = nitro', ACC2, 0.12, 2.6, 2.8)

    def restart(self):
        self.end_session()
        self.start(self.mode)

    def resume(self):
        self.screens['pause'].hide()
        self.state = 'play'

    def quit(self):
        self.end_session()
        write_save(self.save)
        application.quit()

    def end_session(self):
        if self.mode == 'free' and self.car.score > self.save['best_score']:
            self.save['best_score'] = self.car.score
        write_save(self.save)

    def finish_challenge(self):
        self.car.bank()
        score = self.car.score
        record = score > self.save.get('best_challenge', 0)
        if record:
            self.save['best_challenge'] = score
        write_save(self.save)
        self.screens['results'].set(score, self.car.best_drift, record)
        self.state = 'results'
        self.screens['results'].show()
        self.sound.play('score', 1.0, 0.8)

    # ------------------------------------------------------------------ settings
    def apply_setting(self, key, value):
        self.save[key] = value
        if key == 'time':
            self.env.set_time(value)
            self.world.set_lamp_power(TIME_PRESETS[value]['lamps'])
        elif key == 'gearbox':
            self.car.manual = value == 'manual'
        elif key == 'quality':
            self.apply_quality(value)
        elif key == 'camera':
            self.rig.mode = value
        elif key == 'volume':
            self.sound.volume = value
        write_save(self.save)

    def apply_quality(self, q):
        self.env.set_shadows(q != 'low')
        want_post = q == 'high'
        if want_post and not self.post:
            camera.shader = post_shader
        elif not want_post and self.post:
            camera.shader = None
        self.post = want_post
        camera.clip_plane_near = 0.3

    def change_car(self, d):
        ci = (self.save['car'] + d) % len(CARS)
        self.save['car'] = ci
        self.visual.set_car(ci, self.save['paint'][ci])
        self.visual.scale = 0.85
        write_save(self.save)
        self.sound.play('select', 0.7)

    def change_paint(self, d):
        ci = self.save['car']
        self.save['paint'][ci] = (self.save['paint'][ci] + d) % len(PAINTS)
        self.visual.set_paint(self.save['paint'][ci])
        write_save(self.save)
        self.sound.play('click', 0.7)

    # ------------------------------------------------------------------ gameplay events
    def on_drift_end(self, pts, grade, mult):
        big = pts >= 4000
        self.hud.popup(grade, f'+{pts:,}'.replace(',', ' ') + (f'   (x{mult})' if mult > 1 else ''),
                       GOLD if big else ACC, 0.1, 2.9 if big else 2.3, 2.0)
        self.sound.play('score', 0.7, 1.0 + min(mult, 5) * 0.06)
        best = self.save['best_score'] if self.mode == 'free' else self.save.get('best_challenge', 0)
        if not self.record_announced and best > 0 and self.car.score > best:
            self.record_announced = True
            self.hud.popup('NOWY REKORD!', '', GOLD, -0.05, 3.2, 2.5)
            self.flash = 0.35

    def on_drift_failed(self, pts):
        self.hud.popup('DRIFT PRZERWANY', f'-{pts:,}'.replace(',', ' '), Vec4(1, 0.25, 0.2, 1), 0.1, 2.2, 1.6)
        self.sound.play('lost', 0.8)

    def on_combo_lost(self):
        self.hud.popup('COMBO STRACONE', '', Vec4(1, 0.35, 0.3, 1), -0.02, 1.6, 1.2)

    def on_crash(self, strength):
        self.rig.shake = min(1.2, self.rig.shake + strength / 14)
        self.hud.crash_flash(strength)
        self.sound.play('crash', clamp(strength / 18, 0.25, 1.0), random.uniform(0.85, 1.15))
        if strength > 5 and self.car.drift_pts > 0:
            self.car.fail_drift()

    def on_cones(self, n):
        self.car.score += 50 * n
        self.hud.popup(f'+{50 * n}', 'PACHOŁEK' if n == 1 else f'{n} PACHOŁKI', ACC2, -0.1, 1.8, 1.0)
        self.sound.play('click', 0.8, 0.7)

    def on_shift(self, g):
        self.hud.gear_changed()

    # ------------------------------------------------------------------ loop
    def update(self):
        dt = min(time.dt, 1 / 20)
        self.clock += dt
        st = self.state
        car = self.car

        if st in ('play', 'results'):
            controls = st == 'play' and self.countdown <= 0
            if self.countdown > 0:
                prev = math.ceil(self.countdown - 0.5)
                self.countdown -= dt
                now = math.ceil(self.countdown - 0.5)
                if now != prev:
                    if now > 0:
                        self.hud.popup(str(now), '', WHITE, 0.1, 5, 0.9)
                        self.sound.play('click', 1.0, 0.8)
                    else:
                        self.hud.popup('START!', 'WYZWANIE 3:00', ACC, 0.1, 4, 1.2)
                        self.sound.play('select', 1.0)
            car.update(dt, controls)
            if st == 'play' and self.time_left is not None and self.countdown <= 0:
                self.time_left -= dt
                if self.time_left <= 0:
                    self.time_left = 0
                    self.finish_challenge()
            self.world.update(car.x, car.z, 1)
            self.world.update_cones(dt)
            self.rig.update(dt, car, self.clock)
            self.hud.update(dt, car, self.time_left)
            self.sound.set_engine(car.rpm, car.throttle, car.slide, car.speed, True)
        elif st == 'pause':
            self.sound.set_engine(0, 0, 0, 0, False)
        else:
            self.visual.rotation_y += dt * (18 if st == 'garage' else 6)
            self.visual.scale = lerp(self.visual.scale_x, 1.0, min(1.0, dt * 8))
            self.visual.update_visual(0, 0, 0, 0, True, False, False, self.clock)
            garage = st == 'garage'
            self.rig.showcase(dt, PODIUM, 7.6 if garage else 10.0, 1.7 if garage else 2.6, 1.6 if garage else 1.9,
                              6 if garage else 9)
            self.world.update(PODIUM.x, PODIUM.z, 1)
            self.sound.set_engine(0, 0, 0, 0, False)

        if st in self.screens:
            self.screens[st].update(dt)

        cam = camera.world_position
        focus = Vec3(car.x, 0, car.z)
        self.env.update(dt, focus, cam)
        self.env.set_lamps(self.world.lamps_near(car.x, car.z))
        car.fx.brightness = lerp(1.0, 0.28, self.env.night)
        if st in ('play', 'results', 'pause'):
            h = math.radians(car.heading)
            fwd = Vec3(math.sin(h), 0, math.cos(h))
            power = (0.35 + 0.9 * self.env.night) if car.headlights else 0.0
            scene.set_shader_input('u_hl_pos', Vec4(car.x + fwd.x * 2.4, car.y + 0.7, car.z + fwd.z * 2.4, power))
            scene.set_shader_input('u_hl_dir', (fwd + Vec3(0, -0.12, 0)).normalized())
        else:
            scene.set_shader_input('u_hl_pos', Vec4(0, 0, 0, 0))

        if self.post:
            blur = clamp((car.speed - 40) / 50, 0, 1) * 0.15 + (0.3 if car.nitro_on else 0) if st == 'play' else 0
            camera.set_shader_input('u_blur', blur)
            camera.set_shader_input('u_aberr', (1.0 if car.nitro_on else 0) + self.rig.shake * 0.8 if st == 'play' else 0)
            self.flash = max(0.0, self.flash - dt * 0.8)
            camera.set_shader_input('u_flash', self.flash)

        self.fade_a = max(0.0, self.fade_a - dt * 2.2)
        self.fade.color = Vec4(0, 0, 0, self.fade_a)
        self.fade.enabled = self.fade_a > 0.001

    def input(self, key):
        if key == 'f11':
            window.fullscreen = not window.fullscreen
            return
        st = self.state
        if st == 'play':
            car = self.car
            if key in ('escape', 'gamepad start'):
                self.state = 'pause'
                self.screens['pause'].show()
                self.screens['pause'].sel = 0
            elif key in ('c', 'gamepad y'):
                self.rig.mode = (self.rig.mode + 1) % 4
                self.save['camera'] = self.rig.mode
                self.hud.camera_name(CameraRig.MODES[self.rig.mode])
            elif key == 'l':
                car.headlights = not car.headlights
            elif key == 't':
                i = (TIME_ORDER.index(self.save['time']) + 1) % len(TIME_ORDER)
                self.apply_setting('time', TIME_ORDER[i])
                self.hud.camera_name(TIME_PRESETS[TIME_ORDER[i]]['label'])
            elif key in ('r', 'gamepad back'):
                self.reset_to_road()
            elif key == 'tab':
                self.hud.toggle()
            elif key in ('e', 'gamepad right shoulder'):
                car.shift(1)
            elif key in ('q', 'gamepad left shoulder'):
                car.shift(-1)
        elif st in self.screens:
            self.screens[st].input(key)

    def reset_to_road(self):
        car = self.car
        gx, gz = round(car.x / BLOCK) * BLOCK, round(car.z / BLOCK) * BLOCK
        if abs(car.x - gx) < abs(car.z - gz):
            north = math.cos(math.radians(car.heading)) >= 0
            car.respawn(gx + (6 if north else -6), car.z, 0 if north else 180)
        else:
            east = math.sin(math.radians(car.heading)) >= 0
            car.respawn(car.x, gz + (-6 if east else 6), 90 if east else 270)
        self.rig.snap(car)


if __name__ == '__main__':
    game = Game()
    app.run()
