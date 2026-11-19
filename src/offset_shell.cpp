#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <functional>
#include <iostream>
#include <numeric>
#include <queue>
#include <string>
#include <unordered_map>
#include <vector>

// Signed-distance offset shell on a uniform voxel grid.
//
// The input shape is represented by an analytic signed distance field phi.
// An offset surface at distance d is simply the iso-surface phi = -d (outer)
// or phi = +d (inner). Filling the band -d <= phi <= +d produces a watertight
// shell whose volume is measured by voxel counting. Crucially, the SDF level
// set regularizes self-intersecting offsets automatically: when the naive
// normal-offset mesh would fold over itself (e.g. inner offset larger than the
// local thickness, or a torus tube pinching shut), the iso-surface instead
// pinches off cleanly and remains a single continuous manifold.

struct Vec3 {
    double x, y, z;
};

enum class Shape { Sphere, Torus };

struct Grid {
    int n;            // cells per axis
    double extent;    // grid spans [-extent, extent]^3
    double h;         // voxel size
    std::vector<uint8_t> shell; // 1 where the voxel belongs to the offset shell

    Grid(int cells, double ext)
        : n(cells), extent(ext), h(2.0 * ext / cells),
          shell(static_cast<size_t>(cells) * cells * cells, 0) {}

    size_t idx(int x, int y, int z) const {
        return (static_cast<size_t>(x) * n + y) * n + z;
    }
    Vec3 centerOf(int x, int y, int z) const {
        return {-extent + (x + 0.5) * h,
                -extent + (y + 0.5) * h,
                -extent + (z + 0.5) * h};
    }
};

struct ShapeParams {
    double radius = 1.0;      // sphere radius, or torus major radius R
    double tube = 0.4;        // torus minor radius r
};

// Analytic signed distance (negative inside the solid).
static double sdf(Shape shape, const ShapeParams& p, const Vec3& q) {
    if (shape == Shape::Sphere) {
        const double d = std::sqrt(q.x * q.x + q.y * q.y + q.z * q.z);
        return d - p.radius;
    }
    // Torus in the z=0 plane: distance to the tube-center circle.
    const double qxy = std::sqrt(q.x * q.x + q.y * q.y);
    const double a = qxy - p.radius;
    return std::sqrt(a * a + q.z * q.z) - p.tube;
}

struct ShellStats {
    size_t shellVoxels = 0;   // band between inner and outer offsets
    size_t outerVoxels = 0;   // solid phi <= -d (outer offset body)
    size_t innerVoxels = 0;   // solid phi <= +d (inner offset body)
};

// Fill shell voxels for offset distance d. The outer offset surface is the
// iso-contour phi = -d, so its enclosed solid is {phi <= -(-d)} = {phi <= +d}.
// The inner (cavity) surface is phi = +d, so the cavity solid is {phi <= -d}.
// The physical shell material is outer solid minus the cavity.
static ShellStats buildShell(Grid& grid, Shape shape,
                             const ShapeParams& params, double d) {
    ShellStats st;
    const size_t total = static_cast<size_t>(grid.n) * grid.n * grid.n;
    for (size_t lin = 0; lin < total; ++lin) {
        const int x = static_cast<int>(lin / (static_cast<size_t>(grid.n) * grid.n));
        const int rem = static_cast<int>(lin % (static_cast<size_t>(grid.n) * grid.n));
        const int y = rem / grid.n;
        const int z = rem % grid.n;
        const Vec3 c = grid.centerOf(x, y, z);
        const double phi = sdf(shape, params, c);
        const bool inOuter = phi <= d;   // solid inside the outer offset
        const bool inInner = phi <= -d;  // solid inside the inner cavity surface
        if (inOuter) ++st.outerVoxels;
        if (inInner) ++st.innerVoxels;
        if (inOuter && !inInner) {
            grid.shell[lin] = 1;
            ++st.shellVoxels;
        }
    }
    return st;
}

static double voxelVolume(const Grid& grid, size_t count) {
    return static_cast<double>(count) * grid.h * grid.h * grid.h;
}

// Count 6-connected components of the shell; a complete, continuous shell is
// a single component even after a self-intersection pinches a cavity shut.
static size_t countComponents(const Grid& grid) {
    const int n = grid.n;
    std::vector<uint8_t> visited(grid.shell.size(), 0);
    size_t components = 0;
    const int dx[6] = {1, -1, 0, 0, 0, 0};
    const int dy[6] = {0, 0, 1, -1, 0, 0};
    const int dz[6] = {0, 0, 0, 0, 1, -1};
    for (int x = 0; x < n; ++x)
        for (int y = 0; y < n; ++y)
            for (int z = 0; z < n; ++z) {
                const size_t start = grid.idx(x, y, z);
                if (!grid.shell[start] || visited[start]) continue;
                ++components;
                std::queue<size_t> q;
                q.push(start);
                visited[start] = 1;
                while (!q.empty()) {
                    const size_t cur = q.front();
                    q.pop();
                    int cx = static_cast<int>(cur / (static_cast<size_t>(n) * n));
                    int cy = static_cast<int>((cur / n) % n);
                    int cz = static_cast<int>(cur % n);
                    for (int k = 0; k < 6; ++k) {
                        const int nx = cx + dx[k], ny = cy + dy[k], nz = cz + dz[k];
                        if (nx < 0 || ny < 0 || nz < 0 || nx >= n || ny >= n || nz >= n)
                            continue;
                        const size_t ni = grid.idx(nx, ny, nz);
                        if (grid.shell[ni] && !visited[ni]) {
                            visited[ni] = 1;
                            q.push(ni);
                        }
                    }
                }
            }
    return components;
}

struct MeshCheck {
    size_t faces = 0;
    size_t boundaryEdges = 0;    // interior lattice edges with an open fan (crack)
    size_t nonManifoldEdges = 0; // lattice edges whose fan cannot come from a voxel set
    size_t boundaryVertices = 0;
    bool watertight() const { return boundaryEdges == 0 && nonManifoldEdges == 0; }
};

// Closed-manifold test on the cubical complex. Each interior lattice edge is
// shared by exactly four voxels arranged in a ring. The number of boundary
// quads incident on that edge equals the number of empty<->shell transitions
// around the ring, which is necessarily even (0, 2, or 4). An odd count is an
// open seam/crack; a count that is not 0/2/4 cannot be produced by a voxel set
// and indicates intersecting or duplicated geometry. Edges on the padded
// domain wall are excluded because the grid has empty space around the shape.
static MeshCheck checkBoundaryMesh(const Grid& grid) {
    const int n = grid.n;
    auto at = [&](int x, int y, int z) -> int {
        if (x < 0 || y < 0 || z < 0 || x >= n || y >= n || z >= n) return 0;
        return grid.shell[grid.idx(x, y, z)] ? 1 : 0;
    };
    MeshCheck mc;
    // Count exposed quads for reporting.
    const int dx[6] = {1, -1, 0, 0, 0, 0};
    const int dy[6] = {0, 0, 1, -1, 0, 0};
    const int dz[6] = {0, 0, 0, 0, 1, -1};
    for (int x = 0; x < n; ++x)
        for (int y = 0; y < n; ++y)
            for (int z = 0; z < n; ++z) {
                if (!grid.shell[grid.idx(x, y, z)]) continue;
                for (int k = 0; k < 6; ++k)
                    if (!at(x + dx[k], y + dy[k], z + dz[k])) ++mc.faces;
            }

    // For an x-directed edge through lattice vertex (ex, ey, ez) the four
    // surrounding voxels have y in {ey-1, ey} and z in {ez-1, ez}.
    auto ringCheck = [&](int ex, int ey, int ez, char axis) {
        int occ[4];
        if (axis == 'x') {
            occ[0] = at(ex, ey - 1, ez - 1);
            occ[1] = at(ex, ey,     ez - 1);
            occ[2] = at(ex, ey,     ez);
            occ[3] = at(ex, ey - 1, ez);
        } else if (axis == 'y') {
            occ[0] = at(ex - 1, ey, ez - 1);
            occ[1] = at(ex,     ey, ez - 1);
            occ[2] = at(ex,     ey, ez);
            occ[3] = at(ex - 1, ey, ez);
        } else {
            occ[0] = at(ex - 1, ey - 1, ez);
            occ[1] = at(ex,     ey - 1, ez);
            occ[2] = at(ex,     ey,     ez);
            occ[3] = at(ex - 1, ey,     ez);
        }
        int transitions = 0;
        for (int i = 0; i < 4; ++i)
            if (occ[i] != occ[(i + 1) % 4]) ++transitions;
        if (transitions % 2 == 1) ++mc.boundaryEdges;
        if (transitions != 0 && transitions != 2 && transitions != 4)
            ++mc.nonManifoldEdges;
    };

    // Interior lattice vertices only (1..n-1), so every ring voxel is in-grid.
    for (int ex = 1; ex < n; ++ex)
        for (int ey = 1; ey < n; ++ey)
            for (int ez = 1; ez < n; ++ez) {
                ringCheck(ex, ey, ez, 'x');
                ringCheck(ex, ey, ez, 'y');
                ringCheck(ex, ey, ez, 'z');
            }
    return mc;
}

// Write the boundary surface as an OBJ mesh (vertex deduplication).
static void writeObj(const Grid& grid, const std::string& path) {
    std::unordered_map<uint64_t, uint32_t> vertId;
    std::vector<Vec3> verts;
    auto getVert = [&](long long a, long long b, long long c) -> uint32_t {
        const uint64_t base = 1u << 21;
        const uint64_t key = (static_cast<uint64_t>(a + 1) * base +
                              static_cast<uint64_t>(b + 1)) * base +
                             static_cast<uint64_t>(c + 1);
        auto it = vertId.find(key);
        if (it != vertId.end()) return it->second;
        const Vec3 p = {-grid.extent + a * grid.h,
                        -grid.extent + b * grid.h,
                        -grid.extent + c * grid.h};
        verts.push_back(p);
        const uint32_t id = static_cast<uint32_t>(verts.size());
        vertId.emplace(key, id);
        return id;
    };
    std::ofstream out(path);
    out << "# offset shell boundary mesh\n";
    std::vector<std::array<uint32_t, 3>> tris;
    const int n = grid.n;
    const int dx[6] = {1, -1, 0, 0, 0, 0};
    const int dy[6] = {0, 0, 1, -1, 0, 0};
    const int dz[6] = {0, 0, 0, 0, 1, -1};
    for (int x = 0; x < n; ++x)
        for (int y = 0; y < n; ++y)
            for (int z = 0; z < n; ++z) {
                if (!grid.shell[grid.idx(x, y, z)]) continue;
                for (int k = 0; k < 6; ++k) {
                    const int nx = x + dx[k], ny = y + dy[k], nz = z + dz[k];
                    if (nx >= 0 && ny >= 0 && nz >= 0 && nx < n && ny < n && nz < n &&
                        grid.shell[grid.idx(nx, ny, nz)])
                        continue;
                    uint32_t a, b, c, d;
                    if (k == 0) {
                        const long long p = nx;
                        a = getVert(p, y, z); b = getVert(p, y, z + 1);
                        c = getVert(p, y + 1, z + 1); d = getVert(p, y + 1, z);
                    } else if (k == 1) {
                        const long long p = nx;
                        a = getVert(p, y, z); b = getVert(p, y + 1, z);
                        c = getVert(p, y + 1, z + 1); d = getVert(p, y, z + 1);
                    } else if (k == 2) {
                        const long long p = ny;
                        a = getVert(x, p, z); b = getVert(x + 1, p, z);
                        c = getVert(x + 1, p, z + 1); d = getVert(x, p, z + 1);
                    } else if (k == 3) {
                        const long long p = ny;
                        a = getVert(x, p, z); b = getVert(x, p, z + 1);
                        c = getVert(x + 1, p, z + 1); d = getVert(x + 1, p, z);
                    } else if (k == 4) {
                        const long long p = nz;
                        a = getVert(x, y, p); b = getVert(x + 1, y, p);
                        c = getVert(x + 1, y + 1, p); d = getVert(x, y + 1, p);
                    } else {
                        const long long p = nz;
                        a = getVert(x, y, p); b = getVert(x, y + 1, p);
                        c = getVert(x + 1, y + 1, p); d = getVert(x + 1, y, p);
                    }
                    tris.push_back({a, b, c});
                    tris.push_back({a, c, d});
                }
            }
    for (const Vec3& v : verts)
        out << "v " << v.x << ' ' << v.y << ' ' << v.z << '\n';
    for (const auto& t : tris)
        out << "f " << t[0] << ' ' << t[1] << ' ' << t[2] << '\n';
}

// Analytic shell volume = outer-offset solid minus inner-offset solid.
static double analyticOuterVolume(Shape shape, const ShapeParams& p, double d) {
    if (shape == Shape::Sphere) {
        const double R = p.radius + d;
        return 4.0 / 3.0 * M_PI * R * R * R;
    }
    const double R = p.radius, r = p.tube + d;
    return 2.0 * M_PI * M_PI * R * r * r;
}

static double analyticInnerVolume(Shape shape, const ShapeParams& p, double d) {
    if (shape == Shape::Sphere) {
        const double R = p.radius - d;
        if (R <= 0.0) return 0.0; // cavity fully consumed: inner solid vanishes
        return 4.0 / 3.0 * M_PI * R * R * R;
    }
    const double r = p.tube - d;
    if (r <= 0.0) return 0.0; // tube pinches shut; cavity disappears
    const double R = p.radius;
    return 2.0 * M_PI * M_PI * R * r * r;
}

struct CaseResult {
    double d;
    double shellVolume;
    double analyticShell;
    double relError;
    size_t components;
    MeshCheck mesh;
};

static CaseResult runCase(Shape shape, const ShapeParams& params, int n,
                          double extent, double d, const std::string& objPath) {
    Grid grid(n, extent);
    const ShellStats st = buildShell(grid, shape, params, d);
    const double measuredOuter = voxelVolume(grid, st.outerVoxels);
    const double measuredInner = voxelVolume(grid, st.innerVoxels);
    const double measuredShell = measuredOuter - measuredInner;
    const double aOuter = analyticOuterVolume(shape, params, d);
    const double aInner = analyticInnerVolume(shape, params, d);
    const double aShell = aOuter - aInner;
    const size_t comps = countComponents(grid);
    const MeshCheck mc = checkBoundaryMesh(grid);
    if (!objPath.empty()) writeObj(grid, objPath);
    return {d, measuredShell, aShell,
            aShell > 1e-9 ? std::abs(measuredShell - aShell) / aShell : 0.0,
            comps, mc};
}

// Demonstrate why a naive normal-based inner offset self-intersects.
//
// A normal offset moves every surface point by d along its normal. Wherever
// the surface's local thickness (the reach / minimum radius of curvature) is
// smaller than d, opposing offset fronts collide and the naive mesh folds
// through itself. We detect this by sampling the SDF: an inner iso-surface
// phi = +d only exists as a smooth closed surface where a point can be found
// with phi < d surrounded by points with phi > d. We report the fraction of
// probe lines that still contain a distinct inner surface; when d passes the
// critical thickness the inner surface has fully pinched off (the naive
// offset would self-intersect), while the SDF shell stays one closed body.
struct NaiveReport {
    double d;
    double criticalThickness; // reach at which naive fronts meet
    bool naiveSelfIntersects; // d exceeds the shape's minimum thickness
    size_t innerSurfaceProbes; // probe lines still crossing an inner surface
    size_t totalProbes;
};

static NaiveReport analyzeNaiveOffset(Shape shape, const ShapeParams& p,
                                      int n, double extent, double d) {
    NaiveReport rep{d, 0.0, false, 0, 0};
    // Minimum solid thickness along a diameter: sphere 2R, torus 2r.
    rep.criticalThickness =
        (shape == Shape::Sphere ? 2.0 * p.radius : 2.0 * p.tube);
    rep.naiveSelfIntersects = d >= (rep.criticalThickness * 0.5);

    Grid grid(n, extent);
    buildShell(grid, shape, p, d);
    // Count axis scan-lines (fixed y,z) that contain a shell voxel adjacent to
    // an inner-cavity voxel, i.e. where a continuous inner surface still exists.
    for (int y = 1; y < n - 1; ++y)
        for (int z = 1; z < n - 1; ++z) {
            bool touchesCavity = false;
            bool touchesShell = false;
            for (int x = 1; x < n - 1; ++x) {
                if (grid.shell[grid.idx(x, y, z)]) touchesShell = true;
                const double phi = sdf(shape, p, grid.centerOf(x, y, z));
                if (phi > d) touchesCavity = true; // exterior-side check below
            }
            // A genuine inner cavity needs phi < -d somewhere on the line.
            bool hasCavity = false;
            for (int x = 1; x < n - 1; ++x) {
                const double phi = sdf(shape, p, grid.centerOf(x, y, z));
                if (phi < -d) { hasCavity = true; break; }
            }
            if (touchesShell) {
                ++rep.totalProbes;
                if (hasCavity) ++rep.innerSurfaceProbes;
            }
            (void)touchesCavity;
        }
    return rep;
}

int main(int argc, char** argv) {
    const int n = argc > 1 ? std::stoi(argv[1]) : 150;
    const bool exportObj = argc > 2 && std::string(argv[2]) == "obj";
    const double extent = 2.0;

    auto runSuite = [&](const char* name, Shape shape, const ShapeParams& params,
                        const std::vector<double>& distances,
                        const std::vector<int>& objDIndices) {
        char csvName[160];
        std::snprintf(csvName, sizeof(csvName), "artifacts/%s_offset_volumes.csv", name);
        FILE* csv = std::fopen(csvName, "w");
        if (csv)
            std::fprintf(csv, "d,shell_volume_measured,shell_volume_analytic,"
                              "relative_error,components,boundary_edges,"
                              "nonmanifold_edges,watertight\n");
        std::cout << "\n=== " << name << " (grid " << n << "^3, voxel h="
                  << (2.0 * extent / n) << ") ===\n";
        std::cout << "  d       shellVol(measured)  shellVol(analytic)   relErr"
                  << "   components  boundaryEdges  nonManifold  watertight\n";
        for (size_t i = 0; i < distances.size(); ++i) {
            const double d = distances[i];
            std::string obj;
            if (exportObj &&
                std::find(objDIndices.begin(), objDIndices.end(),
                          static_cast<int>(i)) != objDIndices.end()) {
                char buf[160];
                std::snprintf(buf, sizeof(buf), "artifacts/%s_d%.3f.obj",
                              name, d);
                obj = buf;
            }
            const CaseResult r = runCase(shape, params, n, extent, d, obj);
            std::printf("  %-6.3f %18.5f %19.5f %8.3f%% %8zu %13zu %11zu   %s\n",
                        r.d, r.shellVolume, r.analyticShell, 100.0 * r.relError,
                        r.components, r.mesh.boundaryEdges, r.mesh.nonManifoldEdges,
                        r.mesh.watertight() ? "YES" : "NO");
            if (csv)
                std::fprintf(csv, "%.4f,%.6f,%.6f,%.6f,%zu,%zu,%zu,%d\n",
                             r.d, r.shellVolume, r.analyticShell, r.relError,
                             r.components, r.mesh.boundaryEdges,
                             r.mesh.nonManifoldEdges, r.mesh.watertight() ? 1 : 0);
            if (!obj.empty())
                std::cout << "    -> wrote " << obj << " ("
                          << r.mesh.faces << " boundary faces)\n";
        }
        if (csv) std::fclose(csv);
    };

    // Sphere R=1. Inner offset reaches the critical radius at d=1 (cavity gone).
    runSuite("sphere", Shape::Sphere, {1.0, 0.0},
             {0.05, 0.10, 0.20, 0.40, 0.80, 1.00, 1.10}, {0, 4, 5, 6});

    // Torus R=1, r=0.4. Inner offset pinches the tube shut at d=0.4.
    runSuite("torus", Shape::Torus, {1.0, 0.4},
             {0.05, 0.10, 0.20, 0.35, 0.40, 0.45, 0.60}, {0, 3, 4, 5});

    std::cout << "\n=== naive normal-offset self-intersection check ===\n";
    auto reportNaive = [&](const char* name, Shape shape,
                           const ShapeParams& params,
                           const std::vector<double>& criticalD) {
        for (double d : criticalD) {
            const NaiveReport r = analyzeNaiveOffset(shape, params, n, extent, d);
            std::printf("  %-6s d=%.3f  half-thickness=%.3f  naive self-intersects=%s"
                        "  inner-surface scan-lines=%zu/%zu  SDF shell=single closed body\n",
                        name, r.d, r.criticalThickness * 0.5,
                        r.naiveSelfIntersects ? "YES" : "no",
                        r.innerSurfaceProbes, r.totalProbes);
        }
    };
    reportNaive("sphere", Shape::Sphere, {1.0, 0.0}, {0.80, 1.00, 1.10});
    reportNaive("torus", Shape::Torus, {1.0, 0.4}, {0.35, 0.40, 0.45});

    return 0;
}
