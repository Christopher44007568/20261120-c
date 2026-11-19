#pragma once

#include <string>
#include <vector>

#include "ibl/vec3.h"

namespace ibl {

void ensureDirectory(const std::string& path);
void writePpm(const std::string& path, int width, int height,
              const std::vector<Vec3>& pixels, double exposure = 1.0);
void writeLinearF32(const std::string& path, int width, int height,
                    const std::vector<Vec3>& pixels);

}  // namespace ibl
