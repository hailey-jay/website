"""Generate small looping wireframe MP4s for the sidebar 'lately' slot.

Usage: python3 scripts/gen_wireframes.py [name ...]
With no arguments, (re)generates every shape into images/wireframes/.
Requires ffmpeg on PATH.
"""
import subprocess
import sys
import tempfile
from itertools import combinations
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

VARIANTS = {
    "": dict(pink="#f8a7b6", paper="#f9f6f1"),
    "-dark": dict(pink="#f2a3b5", paper="#171421"),
}
SIZE_PX = 360
FRAMES = 130
FPS = 12
OUT_DIR = Path(__file__).resolve().parent.parent / "images" / "wireframes"

PHI = (1 + 5 ** 0.5) / 2


def _normalize(verts):
    verts = np.array(verts, dtype=float)
    return verts / np.max(np.linalg.norm(verts, axis=1))


def _edges_by_distance(verts, tol=1e-3):
    dists = [np.linalg.norm(verts[i] - verts[j])
              for i, j in combinations(range(len(verts)), 2)]
    edge_len = min(dists)
    return [(i, j) for i, j in combinations(range(len(verts)), 2)
            if abs(np.linalg.norm(verts[i] - verts[j]) - edge_len) < tol]


def polyhedron_segments(verts):
    verts = _normalize(verts)
    return [(verts[i], verts[j]) for i, j in _edges_by_distance(verts)]


def tetrahedron():
    return polyhedron_segments([
        (1, 1, 1), (1, -1, -1), (-1, 1, -1), (-1, -1, 1),
    ])


def cube():
    return polyhedron_segments([
        (x, y, z) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)
    ])


def octahedron():
    return polyhedron_segments([
        (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1),
    ])


def dodecahedron():
    verts = [(x, y, z) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
    verts += [(0, y / PHI, z * PHI) for y in (-1, 1) for z in (-1, 1)]
    verts += [(x / PHI, y * PHI, 0) for x in (-1, 1) for y in (-1, 1)]
    verts += [(x * PHI, 0, z / PHI) for x in (-1, 1) for z in (-1, 1)]
    return polyhedron_segments(verts)


def icosahedron():
    verts = [(0, y, z * PHI) for y in (-1, 1) for z in (-1, 1)]
    verts += [(y, z * PHI, 0) for y in (-1, 1) for z in (-1, 1)]
    verts += [(z * PHI, 0, y) for y in (-1, 1) for z in (-1, 1)]
    return polyhedron_segments(verts)


def _grid_segments(x, y, z):
    """Wireframe grid lines from 2D parameter arrays x,y,z (u rows, v cols)."""
    segs = []
    nu, nv = x.shape
    for i in range(nu):
        segs.append((np.stack([x[i], y[i], z[i]], axis=1)))
    for j in range(nv):
        segs.append((np.stack([x[:, j], y[:, j], z[:, j]], axis=1)))
    return segs


def sphere():
    u = np.linspace(0, 2 * np.pi, 18)
    v = np.linspace(0, np.pi, 10)
    uu, vv = np.meshgrid(u, v)
    x = np.cos(uu) * np.sin(vv)
    y = np.sin(uu) * np.sin(vv)
    z = np.cos(vv)
    return _grid_segments(x, y, z)


def torus():
    R, r = 1.0, 0.4
    u = np.linspace(0, 2 * np.pi, 20)
    v = np.linspace(0, 2 * np.pi, 8)
    uu, vv = np.meshgrid(u, v)
    x = (R + r * np.cos(vv)) * np.cos(uu)
    y = (R + r * np.cos(vv)) * np.sin(uu)
    z = r * np.sin(vv)
    return _grid_segments(x, y, z)


def mobius():
    u = np.linspace(0, 2 * np.pi, 28)
    v = np.linspace(-1, 1, 6)
    uu, vv = np.meshgrid(u, v)
    x = (1 + (vv / 2) * np.cos(uu / 2)) * np.cos(uu)
    y = (1 + (vv / 2) * np.cos(uu / 2)) * np.sin(uu)
    z = (vv / 2) * np.sin(uu / 2)
    return _grid_segments(x, y, z)


def klein_bottle():
    a = 2.0
    u = np.linspace(0, 2 * np.pi, 24)
    v = np.linspace(0, 2 * np.pi, 10)
    uu, vv = np.meshgrid(u, v)
    x = (a + np.cos(uu / 2) * np.sin(vv) - np.sin(uu / 2) * np.sin(2 * vv)) * np.cos(uu)
    y = (a + np.cos(uu / 2) * np.sin(vv) - np.sin(uu / 2) * np.sin(2 * vv)) * np.sin(uu)
    z = np.sin(uu / 2) * np.sin(vv) + np.cos(uu / 2) * np.sin(2 * vv)
    return _grid_segments(x, y, z)


SHAPES = {
    "tetrahedron": (tetrahedron, dict(zoom=1.15)),
    "cube": (cube, dict(zoom=1.9)),
    "octahedron": (octahedron, dict(zoom=1.15)),
    "dodecahedron": (dodecahedron, dict(zoom=1.6)),
    "icosahedron": (icosahedron, dict(zoom=1.6)),
    "sphere": (sphere, dict(zoom=1.1)),
    "torus": (torus, dict(zoom=1.6)),
    "mobius": (mobius, dict(zoom=1.6)),
    "klein_bottle": (klein_bottle, dict(zoom=3.4)),
}

# Two fixed rotation axes, 45 degrees apart, applied to the geometry
# itself (not the camera). Composing two real rotation matrices gives
# constant angular velocity on both axes -- no gimbal wobble, and
# because AXIS_B isn't vertical, shapes that are rotationally symmetric
# about a vertical axis (torus, Klein bottle, Mobius band) still get
# carried through genuinely diagonal orientations.
AXIS_A = np.array([0.0, 0.0, 1.0])
AXIS_B = np.array([np.sin(np.radians(45)), 0.0, np.cos(np.radians(45))])
CYCLES_A = 2
CYCLES_B = 1
CAM_ELEV = 18
CAM_AZIM = -60


def _rotation_matrix(axis, angle_deg):
    axis = axis / np.linalg.norm(axis)
    theta = np.radians(angle_deg)
    k = np.array([[0, -axis[2], axis[1]],
                  [axis[2], 0, -axis[0]],
                  [-axis[1], axis[0], 0]])
    return np.eye(3) + np.sin(theta) * k + (1 - np.cos(theta)) * (k @ k)


def render_mp4(name, segments_fn, zoom=1.2, frames=FRAMES, suffix="", pink=None, paper=None):
    """Rotate the geometry (not the camera) around two fixed axes 45
    degrees apart, then render with a fixed camera. See AXIS_A/AXIS_B
    above for why this replaced sweeping elev/azim/roll directly."""
    segments = [np.asarray(seg) for seg in segments_fn()]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for i in range(frames):
            t = i / frames
            r_a = _rotation_matrix(AXIS_A, 360 * CYCLES_A * t)
            r_b = _rotation_matrix(AXIS_B, 360 * CYCLES_B * t)
            r = r_a @ r_b
            fig = plt.figure(figsize=(SIZE_PX / 100, SIZE_PX / 100), dpi=100)
            ax = fig.add_axes([0, 0, 1, 1], projection="3d")
            fig.patch.set_facecolor(paper)
            ax.set_facecolor(paper)
            for seg in segments:
                seg_rot = seg @ r.T
                ax.plot(seg_rot[:, 0], seg_rot[:, 1], seg_rot[:, 2],
                        color=pink, linewidth=0.9, alpha=0.9, solid_capstyle="round")
            ax.set_xlim(-zoom, zoom)
            ax.set_ylim(-zoom, zoom)
            ax.set_zlim(-zoom, zoom)
            ax.set_box_aspect((1, 1, 1))
            ax.view_init(elev=CAM_ELEV, azim=CAM_AZIM)
            ax.set_axis_off()
            fig.savefig(tmp / f"f{i:04d}.png", facecolor=paper)
            plt.close(fig)

        path = OUT_DIR / f"{name}{suffix}.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-framerate", str(FPS),
            "-i", str(tmp / "f%04d.png"),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-crf", "20", "-movflags", "+faststart",
            str(path),
        ], check=True, capture_output=True)

    print(f"wrote {path} ({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    names = sys.argv[1:] or list(SHAPES.keys())
    for name in names:
        fn, kwargs = SHAPES[name]
        for suffix, colors in VARIANTS.items():
            render_mp4(name, fn, suffix=suffix, **colors, **kwargs)
