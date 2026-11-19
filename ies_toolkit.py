"""IES (LM-63) photometric web parsing, sampling, flux integration and
IES-texture mip mapping utilities. Pure stdlib."""

import math


class IESFile:
    """Parsed IES photometric file (Type C photometry)."""

    def __init__(self):
        self.keywords = {}
        self.tilt = None
        self.num_lamps = 0
        self.lumens_per_lamp = 0.0
        self.multiplier = 1.0
        self.n_vertical = 0
        self.n_horizontal = 0
        self.photometric_type = 1
        self.units_type = 1
        self.width = 0.0
        self.length = 0.0
        self.height = 0.0
        self.ballast_factor = 1.0
        self.input_watts = 0.0
        self.vertical_angles = []      # degrees, ascending
        self.horizontal_angles = []    # degrees, ascending
        # candela[h][v]: per horizontal plane, values along vertical angles
        self.candela = []

    @classmethod
    def parse(cls, path):
        with open(path, "r", encoding="ascii", errors="replace") as fh:
            lines = [ln.rstrip("\n") for ln in fh]
        if not lines or not lines[0].startswith("IESNA"):
            raise ValueError("not an IESNA LM-63 file: %s" % path)
        ies = cls()
        idx = 1
        while idx < len(lines):
            line = lines[idx].strip()
            idx += 1
            if line.startswith("TILT="):
                ies.tilt = line.split("=", 1)[1].strip()
                break
            if line.startswith("[") and "]" in line:
                key, _, rest = line.partition("]")
                ies.keywords[key[1:]] = rest.strip()
        if ies.tilt != "NONE":
            if ies.tilt == "INCLUDE":
                idx += 5
            else:
                raise ValueError("external TILT file not supported")
        tokens = []
        while idx < len(lines):
            tokens.extend(lines[idx].split())
            idx += 1
        pos = 0

        def take(n):
            nonlocal pos
            out = tokens[pos:pos + n]
            pos += n
            return out

        ints_floats = take(11)
        (ies.num_lamps, ies.lumens_per_lamp, ies.multiplier,
         ies.n_vertical, ies.n_horizontal, ies.photometric_type,
         ies.units_type, ies.width, ies.length, ies.height) = (
            int(ints_floats[1]), float(ints_floats[2]),
            float(ints_floats[3]), int(ints_floats[4]),
            int(ints_floats[5]), int(ints_floats[6]),
            int(ints_floats[7]), float(ints_floats[8]),
            float(ints_floats[9]), float(ints_floats[10]))
        tail = take(3)
        ies.ballast_factor, ies.input_watts = float(tail[0]), float(tail[2])
        ies.vertical_angles = [float(x) for x in take(ies.n_vertical)]
        ies.horizontal_angles = [float(x) for x in take(ies.n_horizontal)]
        flat = [float(x) for x in take(ies.n_vertical * ies.n_horizontal)]
        ies.candela = [
            flat[h * ies.n_vertical:(h + 1) * ies.n_vertical]
            for h in range(ies.n_horizontal)
        ]
        return ies

    def _interp_column(self, h_idx, theta):
        col = self.candela[h_idx]
        angles = self.vertical_angles
        if theta <= angles[0]:
            return col[0]
        if theta >= angles[-1]:
            return col[-1]
        lo, hi = 0, len(angles) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if angles[mid] <= theta:
                lo = mid
            else:
                hi = mid
        t = (theta - angles[lo]) / (angles[hi] - angles[lo])
        return col[lo] * (1.0 - t) + col[hi] * t

    def _horizontal_weight(self, phi):
        planes = self.horizontal_angles
        span = planes[-1] - planes[0]
        if len(planes) == 1 or span == 0:
            return 0, 0, 0.0
        # mirrored-repeat symmetry: pattern of length `span` alternates
        p = (phi % 360.0) % (2.0 * span)
        if p > span:
            p = 2.0 * span - p
        if p <= planes[0]:
            return 0, 0, 0.0
        if p >= planes[-1]:
            last = len(planes) - 1
            return last, last, 0.0
        for i in range(len(planes) - 1):
            if planes[i] <= p <= planes[i + 1]:
                t = (p - planes[i]) / (planes[i + 1] - planes[i])
                return i, i + 1, t
        last = len(planes) - 1
        return last, last, 0.0

    def candela_at(self, theta_deg, phi_deg, intensity_scale=1.0):
        """Candela toward (theta=angle from nadir, phi=azimuth), bilinearly
        interpolated and intensity-scaled."""
        i0, i1, t = self._horizontal_weight(phi_deg)
        c0 = self._interp_column(i0, theta_deg)
        c1 = self._interp_column(i1, theta_deg)
        return (c0 * (1.0 - t) + c1 * t) * self.multiplier * intensity_scale

    def total_flux(self):
        """Integrate candela over solid angle -> lumens (Type C)."""
        va = [math.radians(a) for a in self.vertical_angles]
        ha = self.horizontal_angles
        span = ha[-1] - ha[0]
        plane_integrals = []
        for h in range(self.n_horizontal):
            acc = 0.0
            for v in range(self.n_vertical - 1):
                f0 = self.candela[h][v] * math.sin(va[v])
                f1 = self.candela[h][v + 1] * math.sin(va[v + 1])
                acc += 0.5 * (f0 + f1) * (va[v + 1] - va[v])
            plane_integrals.append(acc)
        if self.n_horizontal == 1 or span == 0:
            return plane_integrals[0] * 2.0 * math.pi * self.multiplier
        folds = int(round(360.0 / span))
        acc = 0.0
        for h in range(self.n_horizontal - 1):
            dphi = math.radians(ha[h + 1] - ha[h])
            acc += 0.5 * (plane_integrals[h] + plane_integrals[h + 1]) * dphi
        return acc * folds * self.multiplier


class IESTexture:
    """2D candela texture (u=azimuth, v=polar) with a box-filter mip chain,
    mirroring how a GPU samples an IES profile texture."""

    def __init__(self, base):
        self.mips = [base]
        level = base
        while len(level) > 1 and len(level[0]) > 1:
            level = self._downsample(level)
            self.mips.append(level)

    @staticmethod
    def _downsample(tex):
        h, w = len(tex), len(tex[0])
        out = []
        for y in range(h // 2):
            row = []
            for x in range(w // 2):
                row.append(0.25 * (tex[2 * y][2 * x] + tex[2 * y][2 * x + 1]
                                   + tex[2 * y + 1][2 * x]
                                   + tex[2 * y + 1][2 * x + 1]))
            out.append(row)
        return out

    @staticmethod
    def _bilinear(tex, u, v):
        h, w = len(tex), len(tex[0])
        x = (u % 1.0) * w - 0.5
        y = min(max(v, 0.0), 1.0) * h - 0.5
        x0 = math.floor(x)
        y0 = math.floor(y)
        tx = x - x0
        ty = y - y0

        def texel(ix, iy):
            ix %= w
            iy = min(max(iy, 0), h - 1)
            return tex[iy][ix]

        c00 = texel(x0, y0)
        c10 = texel(x0 + 1, y0)
        c01 = texel(x0, y0 + 1)
        c11 = texel(x0 + 1, y0 + 1)
        top = c00 * (1 - tx) + c10 * tx
        bot = c01 * (1 - tx) + c11 * tx
        return top * (1 - ty) + bot * ty

    @staticmethod
    def select_lod(footprint_u, footprint_v, width, height):
        """GPU-style mip selection: lod = log2(max footprint in texels)."""
        fp = max(footprint_u * width, footprint_v * height)
        if fp <= 1.0:
            return 0.0
        return math.log2(fp)

    def sample(self, u, v, lod=0.0):
        lod = min(max(lod, 0.0), len(self.mips) - 1)
        l0 = int(math.floor(lod))
        l1 = min(l0 + 1, len(self.mips) - 1)
        t = lod - l0
        s0 = self._bilinear(self.mips[l0], u, v)
        s1 = self._bilinear(self.mips[l1], u, v)
        return s0 * (1 - t) + s1 * t
