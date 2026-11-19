#pragma once
#include "geometry.h"
#include <vector>
#include <cstdint>

// n random small triangles uniformly distributed in the unit cube.
std::vector<Triangle> uniformScene(int n, uint32_t seed);
// n triangles in k Gaussian clusters inside the unit cube.
std::vector<Triangle> clusteredScene(int n, int k, uint32_t seed);
// Point cloud sampled on a sphere; each point becomes a tiny triangle.
std::vector<Triangle> pointCloudScene(int n, uint32_t seed);
// Dense UV-sphere triangle mesh (slices x stacks quads -> 2 tris each).
std::vector<Triangle> denseMeshScene(int slices, int stacks);
// Triangles lying exactly on the planes x/y/z = 0.5 (split-plane overlap
// stress test) plus a symmetric background so a median split lands exactly
// on the planes.
std::vector<Triangle> planarScene(uint32_t seed);
// Random rays: origins on a sphere around the scene, aimed into the bbox.
std::vector<Ray> makeRays(int n, const AABB& sceneBounds, uint32_t seed);
// O(n) reference intersection for correctness checks.
Hit bruteForce(const std::vector<Triangle>& tris, const Ray& ray, float tMin);
