#include <cmath>
#include <iostream>
#include <string>
#include <vector>

#include "ibl/env_map.h"
#include "ibl/render.h"
#include "ibl/sampler.h"

namespace {

int failures = 0;

void check(bool condition, const std::string& message) {
  if (!condition) {
    std::cerr << "FAIL: " << message << '\n';
    ++failures;
  }
}

bool finiteColor(const ibl::Vec3& value) {
  return std::isfinite(value.x) && std::isfinite(value.y) &&
         std::isfinite(value.z);
}

}  // namespace

int main() {
  using namespace ibl;

  const EnvMap env = EnvMap::makeSyntheticHdr(128, 64);
  check(env.width() == 128 && env.height() == 64, "environment dimensions");
  check(env.mipCount() >= 4, "mip pyramid size");
  check(env.dynamicRange() > 100.0, "environment is high dynamic range");
  check(env.maxLuminance() > 10000.0, "environment has bright emitters");

  const EnvSampler sampler(env);
  double pdfIntegral = 0.0;
  for (int row = 0; row < env.height(); ++row) {
    for (int col = 0; col < env.width(); ++col) {
      pdfIntegral += sampler.pdfForTexel(row, col) * env.texelSolidAngle(row);
    }
  }
  check(std::abs(pdfIntegral - 1.0) < 1e-9, "environment PDF integrates to 1");

  Rng rng(424242);
  int highlightSamples = 0;
  int totalSamples = 100000;
  for (int i = 0; i < totalSamples; ++i) {
    const EnvSample sample = sampler.sample(rng.uniform(), rng.uniform());
    check(std::abs(length(sample.direction) - 1.0) < 1e-9,
          "sampled direction is normalized");
    check(std::isfinite(sample.pdf) && sample.pdf > 0.0,
          "sampled direction has a positive finite PDF");
    highlightSamples += env.isNearHighlight(sample.direction, 1.0) ? 1 : 0;
  }
  const double solidFraction = env.highlightSolidAngle(1.0) / (4.0 * kPi);
  const double sampleFraction =
      static_cast<double>(highlightSamples) / totalSamples;
  check(sampleFraction > 10.0 * solidFraction,
        "importance sampling concentrates in highlights");

  const Vec3 direction = normalize(Vec3{0.2, 0.5, 0.8});
  check(selectMipLod(MipPolicy::Base, env, 0.6, direction) == 0.0,
        "base policy selects mip 0");
  check(selectMipLod(MipPolicy::Roughness, env, 0.2, direction) <
            selectMipLod(MipPolicy::Roughness, env, 0.8, direction),
        "roughness policy increases LOD with roughness");
  check(selectMipLod(MipPolicy::LobeFootprint, env, 0.5, direction) >= 0.0,
        "lobe footprint policy returns a valid LOD");

  RenderOptions options;
  options.width = 36;
  options.height = 36;
  options.spp = 8;
  options.roughness = 0.5;
  const Renderer renderer(env);
  const RenderResult a =
      renderer.render(SamplingMethod::Importance, options, 77);
  const RenderResult b =
      renderer.render(SamplingMethod::Importance, options, 77);
  check(a.pixels.size() == b.pixels.size(), "render output size");
  bool deterministic = true;
  bool finite = true;
  int spherePixels = 0;
  for (std::size_t i = 0; i < a.pixels.size(); ++i) {
    deterministic =
        deterministic && lengthSquared(a.pixels[i] - b.pixels[i]) < 1e-24;
    finite = finite && finiteColor(a.pixels[i]) && finiteColor(b.pixels[i]);
    spherePixels += a.sphere_mask[i] ? 1 : 0;
  }
  check(deterministic, "renders are deterministic for a fixed seed");
  check(finite, "render outputs are finite");
  check(spherePixels > 0, "sphere covers some pixels");

  Vec3 normal;
  check(Renderer::isSpherePixel(18, 18, 36, 36, 0.86, normal),
        "center pixel belongs to the sphere");
  check(!Renderer::isSpherePixel(0, 0, 36, 36, 0.86, normal),
        "corner pixel is outside the sphere");

  if (failures == 0) {
    std::cout << "All IBL tests passed.\n";
  }
  return failures == 0 ? 0 : 1;
}
