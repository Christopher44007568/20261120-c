#pragma once

#include "types.hpp"

namespace vb {

PipelineResult run_visibility_pipeline(const Scene& scene);
PipelineResult run_deferred_pipeline(const Scene& scene);

}  // namespace vb
