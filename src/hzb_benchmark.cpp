#include "hzb_benchmark.hpp"

#include "gl_context.hpp"
#include "shaders.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <string>
#include <vector>

namespace hzb {
namespace {

constexpr GLenum kGlDepthTest = 0x0B71;
constexpr GLenum kGlCullFace = 0x0B44;
constexpr GLenum kGlLess = 0x0201;
constexpr GLenum kGlLequal = 0x0203;
constexpr GLenum kGlDepthBufferBit = 0x00000100;
constexpr GLenum kGlTriangles = 0x0004;
constexpr GLenum kGlArrayBuffer = 0x8892;
constexpr GLenum kGlStaticDraw = 0x88E4;
constexpr GLenum kGlShaderStorageBuffer = 0x90D2;
constexpr GLenum kGlTexture2D = 0x0DE1;
constexpr GLenum kGlTexture0 = 0x84C0;
constexpr GLenum kGlTextureMinFilter = 0x2801;
constexpr GLenum kGlTextureMagFilter = 0x2800;
constexpr GLenum kGlTextureWrapS = 0x2802;
constexpr GLenum kGlTextureWrapT = 0x2803;
constexpr GLenum kGlTextureBaseLevel = 0x813C;
constexpr GLenum kGlTextureMaxLevel = 0x813D;
constexpr GLenum kGlNearest = 0x2600;
constexpr GLenum kGlClampToEdge = 0x812F;
constexpr GLenum kGlDepthComponent24 = 0x81A6;
constexpr GLenum kGlDepthComponent = 0x1902;
constexpr GLenum kGlUnsignedInt = 0x1405;
constexpr GLenum kGlRed = 0x1903;
constexpr GLenum kGlFloat = 0x1406;
constexpr GLenum kGlR32F = 0x822E;
constexpr GLenum kGlFramebuffer = 0x8D40;
constexpr GLenum kGlDepthAttachment = 0x8D00;
constexpr GLenum kGlFramebufferComplete = 0x8CD5;
constexpr GLenum kGlNone = 0;
constexpr GLenum kGlWriteOnly = 0x88B9;
constexpr GLenum kGlAnySamplesPassed = 0x8C2F;
constexpr GLenum kGlQueryResult = 0x8866;
constexpr GLbitfield kGlTextureFetchBarrier = 0x00000008;
constexpr GLbitfield kGlShaderImageBarrier = 0x00000020;
constexpr GLbitfield kGlAllBarriers = 0xFFFFFFFF;
constexpr float kDepthBias = 0.00002f;

double secondsSince(std::chrono::steady_clock::time_point start) {
    return std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
}

double median(std::vector<double> samples) {
    if (samples.empty()) {
        return 0.0;
    }
    std::sort(samples.begin(), samples.end());
    const std::size_t middle = samples.size() / 2;
    if (samples.size() % 2 == 0) {
        return 0.5 * (samples[middle - 1] + samples[middle]);
    }
    return samples[middle];
}

int mipLevelCount(int width, int height) {
    int levels = 1;
    int size = std::max(width, height);
    while (size > 1) {
        size /= 2;
        ++levels;
    }
    return levels;
}

struct PipelineUniforms {
    GLint depthViewProj = -1;
    GLint buildSource = -1;
    GLint buildSourceLevel = -1;
    GLint buildCopyMode = -1;
    GLint buildSourceSize = -1;
    GLint buildDestSize = -1;
    GLint testViewProj = -1;
    GLint testHzb = -1;
    GLint testFullSize = -1;
    GLint testMaxLevel = -1;
    GLint testDepthBias = -1;
};

struct SharedPipeline {
    const GlApi* gl = nullptr;
    GLuint depthProgram = 0;
    GLuint buildProgram = 0;
    GLuint testProgram = 0;
    GLuint vao = 0;
    GLuint vbo = 0;
    GLuint boxBuffer = 0;
    GLuint resultBuffer = 0;
    std::vector<GLuint> queries;
    PipelineUniforms uniforms;

    void destroy() {
        if (gl == nullptr) {
            return;
        }
        if (!queries.empty()) {
            gl->DeleteQueries(static_cast<GLsizei>(queries.size()), queries.data());
            queries.clear();
        }
        if (boxBuffer != 0) {
            gl->DeleteBuffers(1, &boxBuffer);
        }
        if (resultBuffer != 0) {
            gl->DeleteBuffers(1, &resultBuffer);
        }
        if (vbo != 0) {
            gl->DeleteBuffers(1, &vbo);
        }
        if (vao != 0) {
            gl->DeleteVertexArrays(1, &vao);
        }
        if (depthProgram != 0) {
            gl->DeleteProgram(depthProgram);
        }
        if (buildProgram != 0) {
            gl->DeleteProgram(buildProgram);
        }
        if (testProgram != 0) {
            gl->DeleteProgram(testProgram);
        }
        *this = {};
    }

    ~SharedPipeline() { destroy(); }
};

struct ResolutionTargets {
    const GlApi* gl = nullptr;
    GLuint framebuffer = 0;
    GLuint depthTexture = 0;
    GLuint hzbTexture = 0;
    int width = 0;
    int height = 0;
    int levels = 0;

    void destroy() {
        if (gl == nullptr) {
            return;
        }
        if (hzbTexture != 0) {
            gl->DeleteTextures(1, &hzbTexture);
        }
        if (depthTexture != 0) {
            gl->DeleteTextures(1, &depthTexture);
        }
        if (framebuffer != 0) {
            gl->DeleteFramebuffers(1, &framebuffer);
        }
        *this = {};
    }

    ~ResolutionTargets() { destroy(); }
};

bool checkGl(const GlApi& gl, const char* stage, std::string& error) {
    const GLenum code = gl.GetError();
    if (code == 0) {
        return true;
    }
    error = std::string(stage) + " failed with OpenGL error 0x";
    constexpr char digits[] = "0123456789ABCDEF";
    for (int shift = 12; shift >= 0; shift -= 4) {
        error.push_back(digits[(code >> shift) & 0xF]);
    }
    return false;
}

}  // namespace

namespace {

bool initializePipeline(const GlApi& gl, const Scene& scene, SharedPipeline& pipeline,
                        std::string& error) {
    pipeline.gl = &gl;
    pipeline.depthProgram = compileProgram(gl, kDepthVertexShader, kDepthFragmentShader, nullptr,
                                           error);
    if (pipeline.depthProgram == 0) {
        return false;
    }
    pipeline.buildProgram = compileCompute(gl, kHzbBuildShader, error);
    if (pipeline.buildProgram == 0) {
        return false;
    }
    pipeline.testProgram = compileCompute(gl, kHzbTestShader, error);
    if (pipeline.testProgram == 0) {
        return false;
    }

    auto& u = pipeline.uniforms;
    u.depthViewProj = gl.GetUniformLocation(pipeline.depthProgram, "uViewProj");
    u.buildSource = gl.GetUniformLocation(pipeline.buildProgram, "uSource");
    u.buildSourceLevel = gl.GetUniformLocation(pipeline.buildProgram, "uSourceLevel");
    u.buildCopyMode = gl.GetUniformLocation(pipeline.buildProgram, "uCopyMode");
    u.buildSourceSize = gl.GetUniformLocation(pipeline.buildProgram, "uSourceSize");
    u.buildDestSize = gl.GetUniformLocation(pipeline.buildProgram, "uDestSize");
    u.testViewProj = gl.GetUniformLocation(pipeline.testProgram, "uViewProj");
    u.testHzb = gl.GetUniformLocation(pipeline.testProgram, "uHzb");
    u.testFullSize = gl.GetUniformLocation(pipeline.testProgram, "uFullSize");
    u.testMaxLevel = gl.GetUniformLocation(pipeline.testProgram, "uMaxLevel");
    u.testDepthBias = gl.GetUniformLocation(pipeline.testProgram, "uDepthBias");

    gl.GenVertexArrays(1, &pipeline.vao);
    gl.GenBuffers(1, &pipeline.vbo);
    gl.BindVertexArray(pipeline.vao);
    gl.BindBuffer(kGlArrayBuffer, pipeline.vbo);
    gl.BufferData(kGlArrayBuffer,
                  static_cast<GLsizeiptr>(scene.vertices.size() * sizeof(float)),
                  scene.vertices.data(), kGlStaticDraw);
    gl.EnableVertexAttribArray(0);
    gl.VertexAttribPointer(0, 3, kGlFloat, 0, 3 * sizeof(float), nullptr);
    gl.BindVertexArray(0);

    std::vector<float> boxes;
    boxes.reserve(scene.objects.size() * 6);
    for (const Aabb& box : scene.objects) {
        boxes.insert(boxes.end(), {box.min.x, box.min.y, box.min.z,
                                   box.max.x, box.max.y, box.max.z});
    }
    gl.GenBuffers(1, &pipeline.boxBuffer);
    gl.BindBuffer(kGlShaderStorageBuffer, pipeline.boxBuffer);
    gl.BufferData(kGlShaderStorageBuffer,
                  static_cast<GLsizeiptr>(boxes.size() * sizeof(float)), boxes.data(),
                  kGlStaticDraw);

    std::vector<GLuint> emptyFlags(scene.objects.size(), 0u);
    gl.GenBuffers(1, &pipeline.resultBuffer);
    gl.BindBuffer(kGlShaderStorageBuffer, pipeline.resultBuffer);
    gl.BufferData(kGlShaderStorageBuffer,
                  static_cast<GLsizeiptr>(emptyFlags.size() * sizeof(GLuint)),
                  emptyFlags.data(), kGlStaticDraw);
    gl.BindBuffer(kGlShaderStorageBuffer, 0);

    pipeline.queries.resize(scene.objects.size());
    gl.GenQueries(static_cast<GLsizei>(pipeline.queries.size()), pipeline.queries.data());
    return checkGl(gl, "pipeline initialization", error);
}

bool createTargets(const GlApi& gl, int width, int height, ResolutionTargets& targets,
                   std::string& error) {
    targets.gl = &gl;
    targets.width = width;
    targets.height = height;
    targets.levels = mipLevelCount(width, height);

    gl.GenTextures(1, &targets.depthTexture);
    gl.BindTexture(kGlTexture2D, targets.depthTexture);
    gl.TexParameteri(kGlTexture2D, kGlTextureMinFilter, kGlNearest);
    gl.TexParameteri(kGlTexture2D, kGlTextureMagFilter, kGlNearest);
    gl.TexParameteri(kGlTexture2D, kGlTextureWrapS, kGlClampToEdge);
    gl.TexParameteri(kGlTexture2D, kGlTextureWrapT, kGlClampToEdge);
    gl.TexParameteri(kGlTexture2D, kGlTextureBaseLevel, 0);
    gl.TexParameteri(kGlTexture2D, kGlTextureMaxLevel, 0);
    gl.TexImage2D(kGlTexture2D, 0, static_cast<GLint>(kGlDepthComponent24), width, height, 0,
                  kGlDepthComponent, kGlUnsignedInt, nullptr);

    gl.GenFramebuffers(1, &targets.framebuffer);
    gl.BindFramebuffer(kGlFramebuffer, targets.framebuffer);
    gl.FramebufferTexture2D(kGlFramebuffer, kGlDepthAttachment, kGlTexture2D,
                            targets.depthTexture, 0);
    gl.DrawBuffer(kGlNone);
    gl.ReadBuffer(kGlNone);
    if (gl.CheckFramebufferStatus(kGlFramebuffer) != kGlFramebufferComplete) {
        error = "depth framebuffer is incomplete";
        return false;
    }

    gl.GenTextures(1, &targets.hzbTexture);
    gl.BindTexture(kGlTexture2D, targets.hzbTexture);
    gl.TexParameteri(kGlTexture2D, kGlTextureMinFilter, kGlNearest);
    gl.TexParameteri(kGlTexture2D, kGlTextureMagFilter, kGlNearest);
    gl.TexParameteri(kGlTexture2D, kGlTextureWrapS, kGlClampToEdge);
    gl.TexParameteri(kGlTexture2D, kGlTextureWrapT, kGlClampToEdge);
    gl.TexParameteri(kGlTexture2D, kGlTextureBaseLevel, 0);
    gl.TexParameteri(kGlTexture2D, kGlTextureMaxLevel, targets.levels - 1);
    for (int level = 0; level < targets.levels; ++level) {
        const int levelWidth = std::max(1, width >> level);
        const int levelHeight = std::max(1, height >> level);
        gl.TexImage2D(kGlTexture2D, level, static_cast<GLint>(kGlR32F), levelWidth, levelHeight,
                      0, kGlRed, kGlFloat, nullptr);
    }
    gl.BindTexture(kGlTexture2D, 0);
    gl.BindFramebuffer(kGlFramebuffer, 0);
    return checkGl(gl, "render target creation", error);
}

void renderPreviousDepth(const GlApi& gl, const Scene& scene, const SharedPipeline& pipeline,
                         const ResolutionTargets& targets, const Mat4& viewProjection) {
    gl.BindFramebuffer(kGlFramebuffer, targets.framebuffer);
    gl.Viewport(0, 0, targets.width, targets.height);
    gl.Enable(kGlDepthTest);
    gl.DepthFunc(kGlLess);
    gl.DepthMask(1);
    gl.Disable(kGlCullFace);
    gl.ClearDepth(1.0);
    gl.Clear(kGlDepthBufferBit);

    gl.UseProgram(pipeline.depthProgram);
    gl.UniformMatrix4fv(pipeline.uniforms.depthViewProj, 1, 0,
                        viewProjection.value.data());
    gl.BindVertexArray(pipeline.vao);
    gl.DrawArrays(kGlTriangles, 0, static_cast<GLsizei>(scene.vertices.size() / 3));
    gl.BindVertexArray(0);
    gl.Finish();
}

void buildHzb(const GlApi& gl, const SharedPipeline& pipeline,
              const ResolutionTargets& targets) {
    gl.UseProgram(pipeline.buildProgram);
    for (int level = 0; level < targets.levels; ++level) {
        const int destWidth = std::max(1, targets.width >> level);
        const int destHeight = std::max(1, targets.height >> level);
        const bool copyDepth = level == 0;
        const int sourceLevel = copyDepth ? 0 : level - 1;
        const int sourceWidth = copyDepth ? targets.width : std::max(1, targets.width >> sourceLevel);
        const int sourceHeight =
            copyDepth ? targets.height : std::max(1, targets.height >> sourceLevel);
        const GLuint sourceTexture = copyDepth ? targets.depthTexture : targets.hzbTexture;

        gl.ActiveTexture(kGlTexture0);
        gl.BindTexture(kGlTexture2D, sourceTexture);
        gl.Uniform1i(pipeline.uniforms.buildSource, 0);
        gl.Uniform1i(pipeline.uniforms.buildSourceLevel, sourceLevel);
        gl.Uniform1i(pipeline.uniforms.buildCopyMode, copyDepth ? 1 : 0);
        gl.Uniform2i(pipeline.uniforms.buildSourceSize, sourceWidth, sourceHeight);
        gl.Uniform2i(pipeline.uniforms.buildDestSize, destWidth, destHeight);
        gl.BindImageTexture(0, targets.hzbTexture, level, 0, 0, kGlWriteOnly, kGlR32F);
        gl.DispatchCompute(static_cast<GLuint>((destWidth + 7) / 8),
                           static_cast<GLuint>((destHeight + 7) / 8), 1);
        gl.MemoryBarrier(kGlTextureFetchBarrier | kGlShaderImageBarrier);
    }
}

void testHzb(const GlApi& gl, const Scene& scene, const SharedPipeline& pipeline,
             const ResolutionTargets& targets, const Mat4& viewProjection,
             std::vector<GLuint>& culledFlags) {
    gl.UseProgram(pipeline.testProgram);
    gl.UniformMatrix4fv(pipeline.uniforms.testViewProj, 1, 0, viewProjection.value.data());
    gl.Uniform2ui(pipeline.uniforms.testFullSize, static_cast<GLuint>(targets.width),
                  static_cast<GLuint>(targets.height));
    gl.Uniform1i(pipeline.uniforms.testMaxLevel, targets.levels - 1);
    gl.Uniform1f(pipeline.uniforms.testDepthBias, kDepthBias);
    gl.ActiveTexture(kGlTexture0);
    gl.BindTexture(kGlTexture2D, targets.hzbTexture);
    gl.Uniform1i(pipeline.uniforms.testHzb, 0);
    gl.BindBufferBase(kGlShaderStorageBuffer, 0, pipeline.boxBuffer);
    gl.BindBufferBase(kGlShaderStorageBuffer, 1, pipeline.resultBuffer);
    gl.DispatchCompute(static_cast<GLuint>((scene.objects.size() + 63) / 64), 1, 1);
    gl.MemoryBarrier(kGlAllBarriers);

    culledFlags.resize(scene.objects.size());
    gl.BindBuffer(kGlShaderStorageBuffer, pipeline.resultBuffer);
    gl.GetBufferSubData(
        kGlShaderStorageBuffer, 0,
        static_cast<GLsizeiptr>(culledFlags.size() * sizeof(GLuint)), culledFlags.data());
}

void queryObjectVisibility(const GlApi& gl, const Scene& scene, const SharedPipeline& pipeline,
                           const ResolutionTargets& targets, const Mat4& viewProjection,
                           std::vector<GLuint>& visibleFlags) {
    gl.BindFramebuffer(kGlFramebuffer, targets.framebuffer);
    gl.Viewport(0, 0, targets.width, targets.height);
    gl.Enable(kGlDepthTest);
    gl.DepthFunc(kGlLequal);
    gl.DepthMask(0);
    gl.UseProgram(pipeline.depthProgram);
    gl.UniformMatrix4fv(pipeline.uniforms.depthViewProj, 1, 0, viewProjection.value.data());
    gl.BindVertexArray(pipeline.vao);

    for (std::size_t index = 0; index < scene.objects.size(); ++index) {
        const GLint first = static_cast<GLint>(scene.objectVertexOffset(index));
        gl.BeginQuery(kGlAnySamplesPassed, pipeline.queries[index]);
        gl.DrawArrays(kGlTriangles, first, 36);
        gl.EndQuery(kGlAnySamplesPassed);
    }

    visibleFlags.resize(scene.objects.size());
    for (std::size_t index = 0; index < scene.objects.size(); ++index) {
        GLuint result = 0;
        gl.GetQueryObjectuiv(pipeline.queries[index], kGlQueryResult, &result);
        visibleFlags[index] = result != 0 ? 1u : 0u;
    }
    gl.BindVertexArray(0);
    gl.DepthMask(1);
}

}  // namespace

BenchmarkReport runHZBBenchmark(const Scene& scene, int timedFrames, std::string& error) {
    BenchmarkReport report;
    report.architectureCount = scene.architecture.size();
    report.objectCount = scene.objects.size();
    report.timedFrames = std::max(3, timedFrames);

    GlContext context;
    if (!context.create(error)) {
        return report;
    }
    const GlApi& gl = context.api();
    report.renderer = context.renderer();
    report.glVersion = context.version();

    SharedPipeline pipeline;
    if (!initializePipeline(gl, scene, pipeline, error)) {
        return report;
    }

    const std::array<std::array<int, 2>, 6> resolutions = {{
        {1280, 720},
        {960, 540},
        {640, 360},
        {480, 270},
        {320, 180},
        {160, 90},
    }};

    for (const auto& resolution : resolutions) {
        ResolutionTargets targets;
        if (!createTargets(gl, resolution[0], resolution[1], targets, error)) {
            return report;
        }
        const float aspect = static_cast<float>(targets.width) /
                             static_cast<float>(targets.height);
        const Mat4 viewProjection = scene.camera.viewProjection(aspect);

        renderPreviousDepth(gl, scene, pipeline, targets, viewProjection);
        if (!checkGl(gl, "previous-frame depth pass", error)) {
            return report;
        }

        std::vector<double> hzbSamples;
        hzbSamples.reserve(static_cast<std::size_t>(report.timedFrames));
        std::vector<double> querySamples;
        querySamples.reserve(static_cast<std::size_t>(report.timedFrames));
        std::vector<GLuint> hzbFlags;
        std::vector<GLuint> exactVisible;
        for (int frame = -2; frame < report.timedFrames; ++frame) {
            gl.Finish();
            auto start = std::chrono::steady_clock::now();
            buildHzb(gl, pipeline, targets);
            testHzb(gl, scene, pipeline, targets, viewProjection, hzbFlags);
            gl.Finish();
            if (frame >= 0) {
                hzbSamples.push_back(secondsSince(start) * 1000.0);
            }

            gl.Finish();
            start = std::chrono::steady_clock::now();
            queryObjectVisibility(gl, scene, pipeline, targets, viewProjection, exactVisible);
            gl.Finish();
            if (frame >= 0) {
                querySamples.push_back(secondsSince(start) * 1000.0);
            }
        }
        if (!checkGl(gl, "interleaved HZB/query passes", error)) {
            return report;
        }

        ResolutionResult result;
        result.width = targets.width;
        result.height = targets.height;
        result.mipLevels = targets.levels;
        result.objectTestsPerFrame = scene.objects.size();
        result.queryCountPerFrame = scene.objects.size();
        result.hzbDispatchCountPerFrame = 1;
        result.hzbBuildAndTestMs = median(hzbSamples);
        result.perObjectQueryMs = median(querySamples);
        result.speedup = result.hzbBuildAndTestMs > 0.0
                             ? result.perObjectQueryMs / result.hzbBuildAndTestMs
                             : 0.0;

        std::size_t visibleCount = 0;
        std::size_t trueCulled = 0;
        for (std::size_t index = 0; index < scene.objects.size(); ++index) {
            const bool visible = exactVisible[index] != 0;
            const bool culled = hzbFlags[index] != 0;
            visibleCount += visible ? 1 : 0;
            if (culled) {
                ++result.culledObjects;
                if (visible) {
                    ++result.falseCulledObjects;
                } else {
                    ++trueCulled;
                }
            }
        }
        result.exactOccludedObjects = scene.objects.size() - visibleCount;
        const double objectCount = static_cast<double>(scene.objects.size());
        result.cullRate = objectCount > 0.0
                              ? static_cast<double>(result.culledObjects) / objectCount
                              : 0.0;
        result.exactOcclusionRate =
            objectCount > 0.0
                ? static_cast<double>(result.exactOccludedObjects) / objectCount
                : 0.0;
        result.precision = result.culledObjects > 0
                               ? static_cast<double>(trueCulled) /
                                     static_cast<double>(result.culledObjects)
                               : 1.0;
        result.recall = result.exactOccludedObjects > 0
                            ? static_cast<double>(trueCulled) /
                                  static_cast<double>(result.exactOccludedObjects)
                            : 0.0;
        result.falseCullRate =
            visibleCount > 0
                ? static_cast<double>(result.falseCulledObjects) /
                      static_cast<double>(visibleCount)
                : 0.0;
        report.resolutions.push_back(result);
    }
    return report;
}

}  // namespace hzb
