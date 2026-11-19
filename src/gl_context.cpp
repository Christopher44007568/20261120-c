#include "gl_context.hpp"

#include <dlfcn.h>

#include <cstring>
#include <string>
#include <vector>

namespace hzb {
namespace {

constexpr GLenum kGlVertexShader = 0x8B31;
constexpr GLenum kGlFragmentShader = 0x8B30;
constexpr GLenum kGlComputeShader = 0x91B9;
constexpr GLenum kGlCompileStatus = 0x8B81;
constexpr GLenum kGlLinkStatus = 0x8B82;
constexpr GLenum kGlInfoLogLength = 0x8B84;

constexpr unsigned kEglOpenGlApi = 0x30A2;
constexpr unsigned kEglPlatformSurfacelessMesa = 0x31DD;
constexpr int kEglContextMajorVersion = 0x3098;
constexpr int kEglContextMinorVersion = 0x30FB;
constexpr int kEglContextOpenGlProfileMask = 0x30FD;
constexpr int kEglContextOpenGlCoreProfileBit = 0x1;
constexpr int kEglRenderableType = 0x3040;
constexpr int kEglOpenGlBit = 0x8;
constexpr int kEglSurfaceType = 0x3033;
constexpr int kEglPbufferBit = 0x1;
constexpr int kEglNone = 0x3038;
constexpr int kEglVendor = 0x3053;
constexpr int kEglVersion = 0x3054;

using EGLDisplay = void*;
using EGLConfig = void*;
using EGLContext = void*;
using EGLSurface = void*;
using EGLBoolean = unsigned int;
using EGLint = int;
using EGLenum = unsigned int;
using EGLAttrib = std::intptr_t;
using EglGetPlatformDisplayFn = EGLDisplay (*)(EGLenum, void*, const EGLAttrib*);
using EglInitializeFn = EGLBoolean (*)(EGLDisplay, EGLint*, EGLint*);
using EglBindApiFn = EGLBoolean (*)(EGLenum);
using EglChooseConfigFn = EGLBoolean (*)(EGLDisplay, const EGLint*, EGLConfig*, EGLint, EGLint*);
using EglCreateContextFn = EGLContext (*)(EGLDisplay, EGLConfig, EGLContext, const EGLint*);
using EglMakeCurrentFn = EGLBoolean (*)(EGLDisplay, EGLSurface, EGLSurface, EGLContext);
using EglGetErrorFn = EGLint (*)();
using EglQueryStringFn = const char* (*)(EGLDisplay, EGLint);
using EglDestroyContextFn = EGLBoolean (*)(EGLDisplay, EGLContext);
using EglTerminateFn = EGLBoolean (*)(EGLDisplay);

struct EglApi {
    EglGetPlatformDisplayFn getPlatformDisplay = nullptr;
    EglInitializeFn initialize = nullptr;
    EglBindApiFn bindApi = nullptr;
    EglChooseConfigFn chooseConfig = nullptr;
    EglCreateContextFn createContext = nullptr;
    EglMakeCurrentFn makeCurrent = nullptr;
    EglGetErrorFn getError = nullptr;
    EglQueryStringFn queryString = nullptr;
    EglDestroyContextFn destroyContext = nullptr;
    EglTerminateFn terminate = nullptr;
};

template <typename T>
bool loadSymbol(void* handle, const char* name, T& target) {
    target = reinterpret_cast<T>(dlsym(handle, name));
    return target != nullptr;
}

std::string shaderLog(const GlApi& gl, GLuint shader) {
    GLint length = 0;
    gl.GetShaderiv(shader, kGlInfoLogLength, &length);
    std::string log(static_cast<std::size_t>(length > 1 ? length : 1), '\0');
    GLsizei written = 0;
    gl.GetShaderInfoLog(shader, static_cast<GLsizei>(log.size()), &written, log.data());
    log.resize(static_cast<std::size_t>(written));
    return log;
}

std::string programLog(const GlApi& gl, GLuint program) {
    GLint length = 0;
    gl.GetProgramiv(program, kGlInfoLogLength, &length);
    std::string log(static_cast<std::size_t>(length > 1 ? length : 1), '\0');
    GLsizei written = 0;
    gl.GetProgramInfoLog(program, static_cast<GLsizei>(log.size()), &written, log.data());
    log.resize(static_cast<std::size_t>(written));
    return log;
}

GLuint compileShader(const GlApi& gl, GLenum type, const char* source, std::string& error) {
    const GLuint shader = gl.CreateShader(type);
    gl.ShaderSource(shader, 1, &source, nullptr);
    gl.CompileShader(shader);
    GLint status = 0;
    gl.GetShaderiv(shader, kGlCompileStatus, &status);
    if (status == 0) {
        error = "shader compilation failed:\n" + shaderLog(gl, shader);
        gl.DeleteShader(shader);
        return 0;
    }
    return shader;
}

}  // namespace

template <typename T>
bool GlContext::load(T& target, const char* name, std::string& error) {
    using EglGetProcAddressFn = void* (*)(const char*);
    auto getProcAddress = reinterpret_cast<EglGetProcAddressFn>(eglGetProcAddress_);
    void* symbol = getProcAddress(name);
    if (symbol == nullptr && glHandle_ != nullptr) {
        symbol = dlsym(glHandle_, name);
    }
    target = reinterpret_cast<T>(symbol);
    if (target == nullptr) {
        error = std::string("missing OpenGL entry point: ") + name;
        return false;
    }
    return true;
}

bool GlContext::loadEgl(std::string& error) {
    eglHandle_ = dlopen("libEGL.so.1", RTLD_NOW | RTLD_LOCAL);
    if (eglHandle_ == nullptr) {
        error = "cannot load libEGL.so.1 (Mesa EGL runtime is required)";
        return false;
    }
    glHandle_ = dlopen("libGL.so.1", RTLD_NOW | RTLD_LOCAL);

    EglApi egl;
    const bool complete =
        loadSymbol(eglHandle_, "eglGetPlatformDisplay", egl.getPlatformDisplay) &&
        loadSymbol(eglHandle_, "eglInitialize", egl.initialize) &&
        loadSymbol(eglHandle_, "eglBindAPI", egl.bindApi) &&
        loadSymbol(eglHandle_, "eglChooseConfig", egl.chooseConfig) &&
        loadSymbol(eglHandle_, "eglCreateContext", egl.createContext) &&
        loadSymbol(eglHandle_, "eglMakeCurrent", egl.makeCurrent) &&
        loadSymbol(eglHandle_, "eglGetError", egl.getError) &&
        loadSymbol(eglHandle_, "eglQueryString", egl.queryString);
    loadSymbol(eglHandle_, "eglDestroyContext", egl.destroyContext);
    loadSymbol(eglHandle_, "eglTerminate", egl.terminate);
    if (!complete) {
        error = "Mesa EGL is missing required entry points";
        return false;
    }

    eglGetProcAddress_ = dlsym(eglHandle_, "eglGetProcAddress");
    if (eglGetProcAddress_ == nullptr) {
        error = "cannot resolve eglGetProcAddress";
        return false;
    }

    display_ = egl.getPlatformDisplay(kEglPlatformSurfacelessMesa, nullptr, nullptr);
    if (display_ == nullptr) {
        error = "eglGetPlatformDisplay(EGL_PLATFORM_SURFACELESS_MESA) failed";
        return false;
    }
    EGLint major = 0;
    EGLint minor = 0;
    if (!egl.initialize(display_, &major, &minor)) {
        error = "eglInitialize failed with error " + std::to_string(egl.getError());
        return false;
    }
    if (!egl.bindApi(kEglOpenGlApi)) {
        error = "eglBindAPI(EGL_OPENGL_API) failed";
        return false;
    }

    const EGLint configAttributes[] = {
        kEglRenderableType,
        kEglOpenGlBit,
        kEglSurfaceType,
        kEglPbufferBit,
        kEglNone,
    };
    EGLConfig config = nullptr;
    EGLint configCount = 0;
    const bool choseConfig =
        egl.chooseConfig(display_, configAttributes, &config, 1, &configCount) && configCount > 0;

    const EGLint context45[] = {
        kEglContextMajorVersion,
        4,
        kEglContextMinorVersion,
        5,
        kEglContextOpenGlProfileMask,
        kEglContextOpenGlCoreProfileBit,
        kEglNone,
    };
    const EGLint context43[] = {
        kEglContextMajorVersion,
        4,
        kEglContextMinorVersion,
        3,
        kEglContextOpenGlProfileMask,
        kEglContextOpenGlCoreProfileBit,
        kEglNone,
    };
    context_ = egl.createContext(display_, choseConfig ? config : nullptr, nullptr, context45);
    if (context_ == nullptr) {
        context_ = egl.createContext(display_, choseConfig ? config : nullptr, nullptr, context43);
    }
    if (context_ == nullptr) {
        error = "cannot create an OpenGL 4.5/4.3 core context";
        return false;
    }
    if (!egl.makeCurrent(display_, nullptr, nullptr, context_)) {
        error = "eglMakeCurrent failed";
        return false;
    }
    return true;
}

bool GlContext::loadGl(std::string& error) {
#define HZB_LOAD(field, name)                    \
    do {                                         \
        if (!load(api_.field, name, error)) {    \
            return false;                        \
        }                                        \
    } while (false)

    HZB_LOAD(GetString, "glGetString");
    HZB_LOAD(GetError, "glGetError");
    HZB_LOAD(GetIntegerv, "glGetIntegerv");
    HZB_LOAD(Viewport, "glViewport");
    HZB_LOAD(ClearColor, "glClearColor");
    HZB_LOAD(ClearDepth, "glClearDepth");
    HZB_LOAD(Clear, "glClear");
    HZB_LOAD(Enable, "glEnable");
    HZB_LOAD(Disable, "glDisable");
    HZB_LOAD(DepthFunc, "glDepthFunc");
    HZB_LOAD(DepthMask, "glDepthMask");
    HZB_LOAD(DrawArrays, "glDrawArrays");
    HZB_LOAD(Finish, "glFinish");

    HZB_LOAD(GenTextures, "glGenTextures");
    HZB_LOAD(BindTexture, "glBindTexture");
    HZB_LOAD(ActiveTexture, "glActiveTexture");
    HZB_LOAD(TexParameteri, "glTexParameteri");
    HZB_LOAD(TexImage2D, "glTexImage2D");
    HZB_LOAD(DeleteTextures, "glDeleteTextures");

    HZB_LOAD(GenFramebuffers, "glGenFramebuffers");
    HZB_LOAD(BindFramebuffer, "glBindFramebuffer");
    HZB_LOAD(FramebufferTexture2D, "glFramebufferTexture2D");
    HZB_LOAD(CheckFramebufferStatus, "glCheckFramebufferStatus");
    HZB_LOAD(DrawBuffer, "glDrawBuffer");
    HZB_LOAD(ReadBuffer, "glReadBuffer");
    HZB_LOAD(DeleteFramebuffers, "glDeleteFramebuffers");

    HZB_LOAD(GenBuffers, "glGenBuffers");
    HZB_LOAD(BindBuffer, "glBindBuffer");
    HZB_LOAD(BufferData, "glBufferData");
    HZB_LOAD(GetBufferSubData, "glGetBufferSubData");
    HZB_LOAD(BindBufferBase, "glBindBufferBase");
    HZB_LOAD(DeleteBuffers, "glDeleteBuffers");

    HZB_LOAD(GenVertexArrays, "glGenVertexArrays");
    HZB_LOAD(BindVertexArray, "glBindVertexArray");
    HZB_LOAD(EnableVertexAttribArray, "glEnableVertexAttribArray");
    HZB_LOAD(VertexAttribPointer, "glVertexAttribPointer");
    HZB_LOAD(DeleteVertexArrays, "glDeleteVertexArrays");

    HZB_LOAD(CreateShader, "glCreateShader");
    HZB_LOAD(ShaderSource, "glShaderSource");
    HZB_LOAD(CompileShader, "glCompileShader");
    HZB_LOAD(GetShaderiv, "glGetShaderiv");
    HZB_LOAD(GetShaderInfoLog, "glGetShaderInfoLog");
    HZB_LOAD(DeleteShader, "glDeleteShader");
    HZB_LOAD(CreateProgram, "glCreateProgram");
    HZB_LOAD(AttachShader, "glAttachShader");
    HZB_LOAD(LinkProgram, "glLinkProgram");
    HZB_LOAD(GetProgramiv, "glGetProgramiv");
    HZB_LOAD(GetProgramInfoLog, "glGetProgramInfoLog");
    HZB_LOAD(UseProgram, "glUseProgram");
    HZB_LOAD(DeleteProgram, "glDeleteProgram");

    HZB_LOAD(GetUniformLocation, "glGetUniformLocation");
    HZB_LOAD(Uniform1i, "glUniform1i");
    HZB_LOAD(Uniform1f, "glUniform1f");
    HZB_LOAD(Uniform1ui, "glUniform1ui");
    HZB_LOAD(Uniform2i, "glUniform2i");
    HZB_LOAD(Uniform2ui, "glUniform2ui");
    HZB_LOAD(UniformMatrix4fv, "glUniformMatrix4fv");

    HZB_LOAD(GenQueries, "glGenQueries");
    HZB_LOAD(DeleteQueries, "glDeleteQueries");
    HZB_LOAD(BeginQuery, "glBeginQuery");
    HZB_LOAD(EndQuery, "glEndQuery");
    HZB_LOAD(GetQueryObjectuiv, "glGetQueryObjectuiv");

    HZB_LOAD(BindImageTexture, "glBindImageTexture");
    HZB_LOAD(DispatchCompute, "glDispatchCompute");
    HZB_LOAD(MemoryBarrier, "glMemoryBarrier");

#undef HZB_LOAD

    const auto* renderer = api_.GetString(0x1F01);
    const auto* version = api_.GetString(0x1F02);
    renderer_ = renderer != nullptr ? reinterpret_cast<const char*>(renderer) : "unknown";
    version_ = version != nullptr ? reinterpret_cast<const char*>(version) : "unknown";
    return true;
}

bool GlContext::create(std::string& error) {
    if (!loadEgl(error) || !loadGl(error)) {
        destroy();
        return false;
    }
    return true;
}

void GlContext::destroy() {
    if (display_ != nullptr && eglHandle_ != nullptr) {
        using EglMakeCurrentFn = EGLBoolean (*)(EGLDisplay, EGLSurface, EGLSurface, EGLContext);
        using EglDestroyContextFn = EGLBoolean (*)(EGLDisplay, EGLContext);
        using EglTerminateFn = EGLBoolean (*)(EGLDisplay);
        auto makeCurrent =
            reinterpret_cast<EglMakeCurrentFn>(dlsym(eglHandle_, "eglMakeCurrent"));
        auto destroyContext =
            reinterpret_cast<EglDestroyContextFn>(dlsym(eglHandle_, "eglDestroyContext"));
        auto terminate = reinterpret_cast<EglTerminateFn>(dlsym(eglHandle_, "eglTerminate"));
        if (makeCurrent != nullptr) {
            makeCurrent(display_, nullptr, nullptr, nullptr);
        }
        if (context_ != nullptr && destroyContext != nullptr) {
            destroyContext(display_, context_);
        }
        if (terminate != nullptr) {
            terminate(display_);
        }
    }
    context_ = nullptr;
    display_ = nullptr;
    if (glHandle_ != nullptr) {
        dlclose(glHandle_);
        glHandle_ = nullptr;
    }
    if (eglHandle_ != nullptr) {
        dlclose(eglHandle_);
        eglHandle_ = nullptr;
    }
    api_ = {};
}

GlContext::~GlContext() {
    destroy();
}

GLuint compileProgram(const GlApi& gl, const char* vertexSource, const char* fragmentSource,
                      const char* computeSource, std::string& error) {
    if (computeSource != nullptr) {
        return compileCompute(gl, computeSource, error);
    }
    if (vertexSource == nullptr || fragmentSource == nullptr) {
        error = "vertex and fragment shaders are both required";
        return 0;
    }
    const GLuint vertex = compileShader(gl, kGlVertexShader, vertexSource, error);
    if (vertex == 0) {
        return 0;
    }
    const GLuint fragment = compileShader(gl, kGlFragmentShader, fragmentSource, error);
    if (fragment == 0) {
        gl.DeleteShader(vertex);
        return 0;
    }
    const GLuint program = gl.CreateProgram();
    gl.AttachShader(program, vertex);
    gl.AttachShader(program, fragment);
    gl.LinkProgram(program);
    gl.DeleteShader(vertex);
    gl.DeleteShader(fragment);
    GLint status = 0;
    gl.GetProgramiv(program, kGlLinkStatus, &status);
    if (status == 0) {
        error = "program link failed:\n" + programLog(gl, program);
        gl.DeleteProgram(program);
        return 0;
    }
    return program;
}

GLuint compileCompute(const GlApi& gl, const char* source, std::string& error) {
    const GLuint shader = compileShader(gl, kGlComputeShader, source, error);
    if (shader == 0) {
        return 0;
    }
    const GLuint program = gl.CreateProgram();
    gl.AttachShader(program, shader);
    gl.LinkProgram(program);
    gl.DeleteShader(shader);
    GLint status = 0;
    gl.GetProgramiv(program, kGlLinkStatus, &status);
    if (status == 0) {
        error = "compute program link failed:\n" + programLog(gl, program);
        gl.DeleteProgram(program);
        return 0;
    }
    return program;
}

}  // namespace hzb
