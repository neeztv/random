"""Shared config, save data, GLSL shaders, mesh building and procedural textures."""
import json
import math
import random
from array import array
from pathlib import Path

from panda3d.core import Filename, SamplerState
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from ursina import Mesh, Shader, Texture

ROOT = Path(__file__).resolve().parent.parent


def panda_path(p):
    return Filename.from_os_specific(str(p)).get_fullpath()


FONT_TITLE = panda_path(ROOT / 'assets' / 'fonts' / 'RussoOne-Regular.ttf')
FONT_UI = panda_path(ROOT / 'assets' / 'fonts' / 'Rajdhani-Bold.ttf')
FONT_UI_FILE = str(ROOT / 'assets' / 'fonts' / 'Rajdhani-Bold.ttf')
FONT_TITLE_FILE = str(ROOT / 'assets' / 'fonts' / 'RussoOne-Regular.ttf')
SAVE_FILE = ROOT / 'save.json'
CACHE_DIR = ROOT / '.cache'

BLOCK = 96.0        # city grid spacing (m)
ROAD_W = 24.0       # road width
SIDEWALK = 4.0
VIEW_CHUNKS = 2     # chunks generated around the player in each direction

ACCENT = (1.0, 0.32, 0.12)
ACCENT2 = (0.2, 0.85, 1.0)

TIME_PRESETS = {
    'day': dict(
        label='DZIEŃ', sun_dir=(-0.45, -0.78, -0.43), sun_col=(1.08, 1.0, 0.9),
        sky_amb=(0.42, 0.48, 0.6), gnd_amb=(0.26, 0.24, 0.22), sky_top=(0.18, 0.42, 0.85),
        fog_col=(0.66, 0.77, 0.9), fog=0.0030, night=0.0, lamps=0.0),
    'sunset': dict(
        label='ZACHÓD', sun_dir=(-0.82, -0.2, 0.53), sun_col=(1.25, 0.66, 0.36),
        sky_amb=(0.36, 0.3, 0.42), gnd_amb=(0.2, 0.13, 0.12), sky_top=(0.16, 0.2, 0.45),
        fog_col=(0.98, 0.56, 0.38), fog=0.0036, night=0.55, lamps=0.6),
    'night': dict(
        label='NOC', sun_dir=(0.3, -0.72, 0.62), sun_col=(0.16, 0.2, 0.34),
        sky_amb=(0.07, 0.09, 0.16), gnd_amb=(0.035, 0.035, 0.05), sky_top=(0.01, 0.02, 0.07),
        fog_col=(0.05, 0.07, 0.14), fog=0.0042, night=1.0, lamps=1.0),
}
TIME_ORDER = ['day', 'sunset', 'night']

DEFAULT_SAVE = {
    'best_score': 0, 'best_drift': 0, 'car': 0, 'paint': [0, 0, 0],
    'time': 'sunset', 'gearbox': 'auto', 'quality': 'high', 'volume': 0.7, 'camera': 0,
}


def load_save():
    data = dict(DEFAULT_SAVE)
    try:
        data.update(json.loads(SAVE_FILE.read_text(encoding='utf-8')))
    except (OSError, ValueError):
        pass
    return data


def write_save(data):
    try:
        SAVE_FILE.write_text(json.dumps(data, indent=2), encoding='utf-8')
    except OSError:
        pass


def lerp(a, b, t):
    return a + (b - a) * t


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def lerp3(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


# ---------------------------------------------------------------------------
#   SHADERS
# ---------------------------------------------------------------------------

_LIGHT_STRUCT = '''
uniform struct {
    sampler2DShadow shadowMap;
    mat4 shadowViewMatrix;
} p3d_LightSource[1];
'''

WORLD_VERT = '''#version 330
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelViewMatrix;
uniform mat4 p3d_ModelMatrix;
uniform mat3 p3d_NormalMatrix;
''' + _LIGHT_STRUCT + '''
in vec4 p3d_Vertex;
in vec3 p3d_Normal;
in vec4 p3d_Color;
in vec2 p3d_MultiTexCoord0;
out vec3 v_wpos;
out vec3 v_wnorm;
out vec4 v_col;
out vec2 v_uv;
out vec4 v_shad;
void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    v_wpos = (p3d_ModelMatrix * p3d_Vertex).xyz;
    v_wnorm = mat3(p3d_ModelMatrix) * p3d_Normal;
    vec3 vn = normalize(p3d_NormalMatrix * p3d_Normal);
    vec4 vpos = p3d_ModelViewMatrix * p3d_Vertex;
    v_shad = p3d_LightSource[0].shadowViewMatrix * vec4(vpos.xyz + vn * 0.06, 1.0);
    v_col = p3d_Color;
    v_uv = p3d_MultiTexCoord0;
}
'''

WORLD_FRAG = '''#version 330
uniform sampler2D p3d_Texture0;
uniform vec4 p3d_ColorScale;
''' + _LIGHT_STRUCT + '''
uniform vec3 u_sun_dir;
uniform vec3 u_sun_col;
uniform vec3 u_sky_amb;
uniform vec3 u_gnd_amb;
uniform vec3 u_fog_col;
uniform vec3 u_sky_top;
uniform vec3 u_cam_pos;
uniform float u_fog;
uniform float u_night;
uniform float u_shadow;
uniform vec4 u_lamps[12];
uniform vec4 u_hl_pos;
uniform vec3 u_hl_dir;
uniform float u_emit;
uniform float u_gloss;
in vec3 v_wpos;
in vec3 v_wnorm;
in vec4 v_col;
in vec2 v_uv;
in vec4 v_shad;
out vec4 o_color;

float shadow_at() {
    if (u_shadow < 0.5 || v_shad.w <= 0.0) return 1.0;
    vec3 p = v_shad.xyz / v_shad.w;
    if (p.x < 0.0 || p.x > 1.0 || p.y < 0.0 || p.y > 1.0 || p.z > 1.0) return 1.0;
    float s = 0.0;
    float tx = 1.0 / 2048.0;
    for (int x = -1; x <= 1; x++)
        for (int y = -1; y <= 1; y++)
            s += texture(p3d_LightSource[0].shadowMap, vec3(p.xy + vec2(x, y) * tx * 1.3, p.z - 0.0006));
    return s / 9.0;
}

void main() {
    vec4 tex = texture(p3d_Texture0, v_uv);
    float win = smoothstep(0.97, 0.9, tex.a);
    vec3 alb = mix(tex.rgb * v_col.rgb, tex.rgb, win) * p3d_ColorScale.rgb;
    float lit_win = win * clamp(1.0 - tex.a / 0.75, 0.0, 1.0);

    vec3 N = normalize(v_wnorm);
    vec3 V = normalize(u_cam_pos - v_wpos);
    vec3 L = -u_sun_dir;
    float sh = shadow_at();
    vec3 light = mix(u_gnd_amb, u_sky_amb, N.y * 0.5 + 0.5) + u_sun_col * max(dot(N, L), 0.0) * sh;

    vec3 lamp_col = vec3(1.0, 0.68, 0.36);
    for (int i = 0; i < 12; i++) {
        vec4 lp = u_lamps[i];
        if (lp.w <= 0.0) continue;
        vec3 d = lp.xyz - v_wpos;
        float d2 = dot(d, d);
        float att = lp.w * 60.0 / (d2 + 8.0) * clamp(1.0 - d2 / 1800.0, 0.0, 1.0);
        light += lamp_col * att * (max(dot(N, d * inversesqrt(d2)), 0.0) * 0.8 + 0.2);
    }
    if (u_hl_pos.w > 0.0) {
        vec3 d = v_wpos - u_hl_pos.xyz;
        float dist = max(length(d), 0.001);
        vec3 dn = d / dist;
        float cone = smoothstep(0.72, 0.93, dot(dn, u_hl_dir));
        float att = u_hl_pos.w * cone * 220.0 / (dist * dist + 30.0);
        light += vec3(1.0, 0.95, 0.85) * att * (max(dot(N, -dn), 0.0) * 0.85 + 0.15);
    }

    vec3 col = alb * light;
    float g = v_col.a * u_gloss * (1.0 - win);
    if (g > 0.01) {
        vec3 H = normalize(L + V);
        float sp = pow(max(dot(N, H), 0.0), mix(12.0, 140.0, g));
        col += u_sun_col * sp * g * sh * 1.6;
        float fr = pow(1.0 - max(dot(N, V), 0.0), 3.0);
        vec3 R = reflect(-V, N);
        vec3 env = R.y > 0.0 ? mix(u_fog_col, u_sky_top, clamp(R.y * 1.4, 0.0, 1.0)) : u_gnd_amb * 0.6;
        col = mix(col, env, clamp(fr * g * 0.9 + g * 0.1, 0.0, 1.0));
    }
    col = mix(col, alb * 1.3, u_emit);
    col += vec3(1.0, 0.78, 0.48) * lit_win * u_night * 1.1;

    float dist = length(v_wpos - u_cam_pos);
    float f = 1.0 - exp(-pow(dist * u_fog, 1.6));
    col = mix(col, u_fog_col, clamp(f, 0.0, 1.0));
    o_color = vec4(col, p3d_ColorScale.a);
}
'''

SKY_VERT = '''#version 330
uniform mat4 p3d_ModelViewProjectionMatrix;
in vec4 p3d_Vertex;
out vec3 v_dir;
void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    v_dir = p3d_Vertex.xyz;
}
'''

SKY_FRAG = '''#version 330
uniform vec3 u_sky_top;
uniform vec3 u_fog_col;
uniform vec3 u_sun_dir;
uniform vec3 u_sun_col;
uniform float u_night;
uniform float u_time;
in vec3 v_dir;
out vec4 o_color;

float hash(vec3 p) { return fract(sin(dot(p, vec3(127.1, 311.7, 74.7))) * 43758.5453); }
float hash2(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p) {
    vec2 i = floor(p); vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash2(i), hash2(i + vec2(1, 0)), f.x), mix(hash2(i + vec2(0, 1)), hash2(i + vec2(1, 1)), f.x), f.y);
}
float fbm(vec2 p) {
    float v = 0.0; float a = 0.5;
    for (int i = 0; i < 5; i++) { v += a * noise(p); p *= 2.03; a *= 0.5; }
    return v;
}

void main() {
    vec3 d = normalize(v_dir);
    float h = d.y;
    vec3 col = mix(u_fog_col, u_sky_top, pow(clamp(h, 0.0, 1.0), 0.55));
    if (h < 0.0) col = u_fog_col * 0.9;
    vec3 sd = -u_sun_dir;
    float s = max(dot(d, sd), 0.0);
    if (u_night > 0.9) {
        col += vec3(0.8, 0.85, 1.0) * smoothstep(0.9993, 0.9996, s) * 1.2;
        col += vec3(0.2, 0.25, 0.4) * pow(s, 60.0) * 0.5;
    } else {
        col += u_sun_col * (smoothstep(0.9990, 0.9994, s) * 2.5 + pow(s, 10.0) * 0.35 + pow(s, 200.0) * 0.8);
    }
    if (h > 0.0) {
        vec3 p = d * 260.0;
        vec3 c = floor(p);
        float st = step(0.9975, hash(c)) * smoothstep(0.42, 0.0, length(fract(p) - 0.5));
        col += vec3(st) * u_night * smoothstep(0.0, 0.25, h) * (0.6 + 0.4 * sin(u_time * 3.0 + hash(c) * 40.0));
        vec2 cp = d.xz / (h + 0.12) * 1.3 + vec2(u_time * 0.006, 0.0);
        float cl = smoothstep(0.5, 0.85, fbm(cp)) * smoothstep(0.0, 0.25, h);
        vec3 cloud_col = mix(u_fog_col * 1.1 + u_sun_col * 0.25, vec3(0.08, 0.09, 0.13), u_night * 0.85);
        col = mix(col, cloud_col, cl * 0.75);
    }
    o_color = vec4(col, 1.0);
}
'''

POST_FRAG = '''#version 330
uniform sampler2D tex;
uniform float u_bloom;
uniform float u_blur;
uniform float u_vig;
uniform float u_flash;
uniform float u_sat;
uniform float u_aberr;
in vec2 uv;
out vec4 o_color;

vec3 bright(vec2 p) {
    vec3 c = texture(tex, p).rgb;
    float l = max(max(c.r, c.g), c.b);
    return c * smoothstep(0.8, 1.3, l);
}

void main() {
    vec2 px = 1.0 / vec2(textureSize(tex, 0));
    vec2 d = uv - 0.5;
    vec3 col;
    if (u_blur > 0.002) {
        col = vec3(0.0);
        for (int i = 0; i < 8; i++) col += texture(tex, uv - d * u_blur * 0.035 * float(i)).rgb;
        col /= 8.0;
    } else {
        col = texture(tex, uv).rgb;
    }
    if (u_aberr > 0.001) {
        col.r = mix(col.r, texture(tex, uv + d * u_aberr * 0.012).r, 0.8);
        col.b = mix(col.b, texture(tex, uv - d * u_aberr * 0.012).b, 0.8);
    }
    vec3 b = vec3(0.0);
    for (int r = 1; r <= 3; r++) {
        float rad = float(r * r) * 5.0 + 2.0;
        for (int k = 0; k < 8; k++) {
            float a = 6.2831 * (float(k) + 0.37 * float(r)) / 8.0;
            b += bright(uv + vec2(cos(a), sin(a)) * rad * px) / float(r);
        }
    }
    col += b * u_bloom * 0.06;
    float l = dot(col, vec3(0.299, 0.587, 0.114));
    col = mix(vec3(l), col, u_sat);
    col = col * (1.0 + 0.1 * (col - 0.5));
    col *= 1.0 - dot(d, d) * u_vig;
    col = mix(col, vec3(1.0), u_flash);
    o_color = vec4(col, 1.0);
}
'''

world_shader = Shader(language=Shader.GLSL, vertex=WORLD_VERT, fragment=WORLD_FRAG,
                      default_input={'u_emit': 0.0, 'u_gloss': 1.0})
sky_shader = Shader(language=Shader.GLSL, vertex=SKY_VERT, fragment=SKY_FRAG)
post_shader = Shader(language=Shader.GLSL, fragment=POST_FRAG, default_input={
    'u_bloom': 1.0, 'u_blur': 0.0, 'u_vig': 1.1, 'u_flash': 0.0, 'u_sat': 1.12, 'u_aberr': 0.0})


# ---------------------------------------------------------------------------
#   MESH BUILDER
# ---------------------------------------------------------------------------

def _norm(v):
    l = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) or 1.0
    return (v[0] / l, v[1] / l, v[2] / l)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


class MeshBuilder:
    """Accumulates geometry into flat buffers. Colors are (r, g, b, gloss)."""

    def __init__(self):
        self.v = array('f')
        self.n = array('f')
        self.c = array('f')
        self.t = array('f')
        self.i = array('I')

    def __len__(self):
        return len(self.v) // 3

    def vert(self, p, n, c, uv=(0.0, 0.0)):
        self.v.extend(p)
        self.n.extend(n)
        self.c.extend(c)
        self.t.extend(uv)
        return len(self.v) // 3 - 1

    def quad(self, p0, p1, p2, p3, col, n=None, uvs=None):
        if n is None:
            n = _norm(_cross(_sub(p1, p0), _sub(p3, p0)))
        b = len(self.v) // 3
        uvs = uvs or ((0, 0), (1, 0), (1, 1), (0, 1))
        for p, uv in zip((p0, p1, p2, p3), uvs):
            self.v.extend(p)
            self.n.extend(n)
            self.c.extend(col)
            self.t.extend(uv)
        self.i.extend((b, b + 1, b + 2, b, b + 2, b + 3))

    def tri(self, p0, p1, p2, col, n=None):
        if n is None:
            n = _norm(_cross(_sub(p1, p0), _sub(p2, p0)))
        b = len(self.v) // 3
        for p in (p0, p1, p2):
            self.v.extend(p)
            self.n.extend(n)
            self.c.extend(col)
            self.t.extend((0.0, 0.0))
        self.i.extend((b, b + 1, b + 2))

    def flat(self, x0, z0, x1, z1, y, col, uv_scale=None):
        """Horizontal rectangle facing up; uv from world xz when uv_scale is given."""
        if uv_scale:
            s = uv_scale
            uvs = ((x0 / s, z0 / s), (x1 / s, z0 / s), (x1 / s, z1 / s), (x0 / s, z1 / s))
        else:
            uvs = None
        self.quad((x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1), col, (0, 1, 0), uvs)

    def box(self, cx, cy, cz, sx, sy, sz, col, ry=0.0, top=None, bottom=False):
        """Box centered at (cx, cy, cz), rotated ry degrees around Y (ursina convention)."""
        a = math.radians(ry)
        ca, sa = math.cos(a), math.sin(a)
        ax = (ca * sx / 2, 0, -sa * sx / 2)
        az = (sa * sz / 2, 0, ca * sz / 2)
        hy = sy / 2
        nx = (ca, 0, -sa)
        nz = (sa, 0, ca)

        def P(i, j, k):
            return (cx + ax[0] * i + az[0] * k, cy + hy * j, cz + ax[2] * i + az[2] * k)

        top_col = top or col
        self.quad(P(-1, 1, -1), P(1, 1, -1), P(1, 1, 1), P(-1, 1, 1), top_col, (0, 1, 0))
        self.quad(P(1, -1, -1), P(1, -1, 1), P(1, 1, 1), P(1, 1, -1), col, nx)
        self.quad(P(-1, -1, 1), P(-1, -1, -1), P(-1, 1, -1), P(-1, 1, 1), col, (-nx[0], 0, -nx[2]))
        self.quad(P(1, -1, 1), P(-1, -1, 1), P(-1, 1, 1), P(1, 1, 1), col, nz)
        self.quad(P(-1, -1, -1), P(1, -1, -1), P(1, 1, -1), P(-1, 1, -1), col, (-nz[0], 0, -nz[2]))
        if bottom:
            self.quad(P(-1, -1, -1), P(-1, -1, 1), P(1, -1, 1), P(1, -1, -1), col, (0, -1, 0))

    def facade(self, x0, z0, x1, z1, y0, y1, col, uoff=0.0, voff=0.0, cell_w=3.2, cell_h=3.6):
        """Four walls with tiled window UVs (texture holds 8x8 window cells)."""
        su, sv = cell_w * 8, cell_h * 8
        v0, v1 = voff + y0 / sv, voff + y1 / sv
        walls = (
            ((x0, z1), (x1, z1), (0, 0, 1)),
            ((x1, z1), (x1, z0), (1, 0, 0)),
            ((x1, z0), (x0, z0), (0, 0, -1)),
            ((x0, z0), (x0, z1), (-1, 0, 0)),
        )
        u = uoff
        for (ax_, az_), (bx_, bz_), n in walls:
            w = math.hypot(bx_ - ax_, bz_ - az_)
            u1 = u + round(w / cell_w) / 8
            self.quad((ax_, y0, az_), (bx_, y0, bz_), (bx_, y1, bz_), (ax_, y1, az_), col, n,
                      ((u, v0), (u1, v0), (u1, v1), (u, v1)))
            u = u1

    def cyl(self, cx, cy, cz, r0, r1, h, col, segs=8, cap=True):
        """Vertical (optionally tapered) cylinder standing on (cx, cy, cz)."""
        for s in range(segs):
            a0 = math.tau * s / segs
            a1 = math.tau * (s + 1) / segs
            c0, s0, c1, s1 = math.cos(a0), math.sin(a0), math.cos(a1), math.sin(a1)
            b = len(self.v) // 3
            for (c_, s_, r, y) in ((c0, s0, r0, 0), (c1, s1, r0, 0), (c1, s1, r1, h), (c0, s0, r1, h)):
                self.v.extend((cx + c_ * r, cy + y, cz + s_ * r))
                self.n.extend((c_, 0.0, s_))
                self.c.extend(col)
                self.t.extend((0.0, 0.0))
            self.i.extend((b, b + 1, b + 2, b, b + 2, b + 3))
            if cap:
                self.tri((cx, cy + h, cz), (cx + c1 * r1, cy + h, cz + s1 * r1), (cx + c0 * r1, cy + h, cz + s0 * r1), col, (0, 1, 0))

    def cyl_x(self, cx, cy, cz, r, w, col, segs=16, cap_col=None, caps=(True, True)):
        """Cylinder along the X axis centered at (cx, cy, cz)."""
        x0, x1 = cx - w / 2, cx + w / 2
        for s in range(segs):
            a0 = math.tau * s / segs
            a1 = math.tau * (s + 1) / segs
            c0, s0, c1, s1 = math.cos(a0), math.sin(a0), math.cos(a1), math.sin(a1)
            b = len(self.v) // 3
            for (x, c_, s_) in ((x0, c0, s0), (x1, c0, s0), (x1, c1, s1), (x0, c1, s1)):
                self.v.extend((x, cy + c_ * r, cz + s_ * r))
                self.n.extend((0.0, c_, s_))
                self.c.extend(col)
                self.t.extend((0.0, 0.0))
            self.i.extend((b, b + 1, b + 2, b, b + 2, b + 3))
            cc = cap_col or col
            if caps[1]:
                self.tri((x1, cy, cz), (x1, cy + c0 * r, cz + s0 * r), (x1, cy + c1 * r, cz + s1 * r), cc, (1, 0, 0))
            if caps[0]:
                self.tri((x0, cy, cz), (x0, cy + c1 * r, cz + s1 * r), (x0, cy + c0 * r, cz + s0 * r), cc, (-1, 0, 0))

    def ball(self, cx, cy, cz, rx, ry, rz, col, segs=8, rings=5, rnd=None, jitter=0.0):
        pts = []
        for j in range(rings + 1):
            phi = math.pi * j / rings
            row = []
            for s in range(segs):
                th = math.tau * s / segs
                k = 1.0 + (rnd.uniform(-jitter, jitter) if rnd and 0 < j < rings else 0.0)
                n = (math.sin(phi) * math.cos(th), math.cos(phi), math.sin(phi) * math.sin(th))
                row.append(((cx + n[0] * rx * k, cy + n[1] * ry * k, cz + n[2] * rz * k), n))
            pts.append(row)
        for j in range(rings):
            for s in range(segs):
                s2 = (s + 1) % segs
                a, b, c, d = pts[j][s], pts[j][s2], pts[j + 1][s2], pts[j + 1][s]
                base = len(self.v) // 3
                for p, n in (a, b, c, d):
                    self.v.extend(p)
                    self.n.extend(n)
                    self.c.extend(col)
                    self.t.extend((0.0, 0.0))
                self.i.extend((base, base + 1, base + 2, base, base + 2, base + 3))

    def build(self):
        if not self.v:
            return None
        return Mesh(vertices=self.v, triangles=self.i, colors=self.c, normals=self.n, uvs=self.t)


# ---------------------------------------------------------------------------
#   PROCEDURAL TEXTURES
# ---------------------------------------------------------------------------

def _to_texture(img, mipmap=True):
    tex = Texture(img)
    t = tex._texture
    if mipmap:
        t.set_minfilter(SamplerState.FT_linear_mipmap_linear)
        t.set_anisotropic_degree(8)
    else:
        t.set_minfilter(SamplerState.FT_linear)
        t.set_wrap_u(SamplerState.WM_clamp)
        t.set_wrap_v(SamplerState.WM_clamp)
    t.set_magfilter(SamplerState.FT_linear)
    return tex


def make_facade_texture(seed=7):
    """8x8 window cells. Wall alpha=1 (tinted by vertex color); window alpha<1 (0.75 dark .. 0 fully lit)."""
    rnd = random.Random(seed)
    S, cell = 512, 64
    img = Image.new('RGBA', (S, S), (236, 236, 236, 255))
    d = ImageDraw.Draw(img)
    for cy in range(8):
        d.rectangle([0, cy * cell + cell - 6, S, cy * cell + cell - 3], fill=(205, 205, 205, 255))
        for cx in range(8):
            x0, x1 = cx * cell + 10, cx * cell + cell - 10
            y0, y1 = cy * cell + 10, cy * cell + cell - 16
            lit = rnd.random() < 0.42
            a = rnd.randint(0, 60) if lit else 191
            base = (70, 88, 110) if not lit else (110, 105, 95)
            for yy in range(y0, y1):
                k = (yy - y0) / max(1, y1 - y0)
                c = tuple(int(v * (1.15 - 0.4 * k)) for v in base)
                d.line([x0, yy, x1, yy], fill=c + (a,))
            if rnd.random() < 0.3:
                d.rectangle([x0, y0, x1, y0 + rnd.randint(4, 20)], fill=(190, 185, 170, a))
            d.line([(x0 + x1) // 2, y0, (x0 + x1) // 2, y1], fill=(150, 150, 150, 255), width=2)
            d.rectangle([x0 - 3, y1, x1 + 3, y1 + 3], fill=(215, 215, 215, 255))
    return _to_texture(img)


def make_ground_texture(seed=3):
    rnd = random.Random(seed)
    S = 256
    img = Image.new('L', (S, S), 220)
    px = img.load()
    for y in range(S):
        for x in range(S):
            px[x, y] = 200 + rnd.randint(0, 55)
    img = img.filter(ImageFilter.GaussianBlur(0.8))
    d = ImageDraw.Draw(img)
    for _ in range(14):
        x, y = rnd.randint(0, S), rnd.randint(0, S)
        pts = [(x, y)]
        for _ in range(6):
            x += rnd.randint(-14, 14)
            y += rnd.randint(-14, 14)
            pts.append((x, y))
        d.line(pts, fill=160, width=1)
    for _ in range(12):
        x, y, r = rnd.randint(0, S), rnd.randint(0, S), rnd.randint(3, 9)
        d.ellipse([x - r, y - r, x + r, y + r], fill=rnd.randint(212, 228))
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    return _to_texture(Image.merge('RGBA', (img, img, img, Image.new('L', (S, S), 255))))


def make_soft_texture(size=64, power=1.6):
    img = Image.new('RGBA', (size, size))
    px = img.load()
    c = (size - 1) / 2
    for y in range(size):
        for x in range(size):
            r = math.hypot(x - c, y - c) / c
            a = max(0.0, 1.0 - r) ** power
            px[x, y] = (255, 255, 255, int(a * 255))
    return _to_texture(img, mipmap=False)


def make_gauge_texture(redline_frac=0.82, size=512):
    """Tachometer face drawn at 2x and downsampled for anti-aliasing."""
    S = size * 2
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = S / 2
    d.ellipse([8, 8, S - 8, S - 8], fill=(8, 10, 16, 205))
    d.ellipse([8, 8, S - 8, S - 8], outline=(255, 255, 255, 40), width=6)
    start, sweep = 135, 270
    r_out, r_in = c - 40, c - 64
    rl = start + sweep * redline_frac
    d.arc([c - r_out, c - r_out, c + r_out, c + r_out], rl, start + sweep, fill=(255, 40, 40, 230), width=22)
    try:
        font = ImageFont.truetype(FONT_UI_FILE, 64)
    except OSError:
        font = ImageFont.load_default()
    for i in range(0, 81):
        a = math.radians(start + sweep * i / 80)
        major = i % 10 == 0
        r1 = r_out - (46 if major else 22)
        col = (255, 70, 60, 255) if i / 80 >= redline_frac else (235, 240, 255, 230 if major else 120)
        d.line([c + math.cos(a) * r1, c + math.sin(a) * r1, c + math.cos(a) * r_out, c + math.sin(a) * r_out],
               fill=col, width=9 if major else 4)
        if major:
            rt = r_out - 100
            label = str(i // 10)
            tw = d.textlength(label, font=font)
            d.text((c + math.cos(a) * rt - tw / 2, c + math.sin(a) * rt - 38), label, font=font, fill=col)
    img = img.resize((size, size), Image.LANCZOS)
    return _to_texture(img, mipmap=False)


def make_ring_texture(size=256, width=0.16):
    """Anti-aliased ring (for UI badges / glow)."""
    S = size * 2
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w = int(S * width / 2)
    d.ellipse([4, 4, S - 4, S - 4], outline=(255, 255, 255, 255), width=w)
    return _to_texture(img.resize((size, size), Image.LANCZOS), mipmap=False)


def make_gradient_texture(w=256, h=8, horizontal=True):
    """White with alpha fading from 1 to 0 (for panels)."""
    img = Image.new('RGBA', (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            t = x / (w - 1) if horizontal else y / (h - 1)
            px[x, y] = (255, 255, 255, int(255 * (1 - t) ** 1.4))
    return _to_texture(img, mipmap=False)
