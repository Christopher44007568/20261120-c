#pragma once

#include <cstddef>
#include <cstdint>
#include <string>

namespace hzb {

using GLenum = unsigned int;
using GLuint = unsigned int;
using GLint = int;
using GLsizei = int;
using GLfloat = float;
using GLboolean = unsigned char;
using GLbitfield = unsigned int;
using GLchar = char;
using GLsizeiptr = std::ptrdiff_t;
using GLintptr = std::ptrdiff_t;
using GLubyte = unsigned char;

struct GlApi {
    const GLubyte* (*GetString)(GLenum) = nullptr;
    GLenum (*GetError)() = nullptr;
    void (*GetIntegerv)(GLenum, GLint*) = nullptr;
    void (*Viewport)(GLint, GLint, GLsizei, GLsizei) = nullptr;
    void (*ClearColor)(GLfloat, GLfloat, GLfloat, GLfloat) = nullptr;
    void (*ClearDepth)(double) = nullptr;
    void (*Clear)(GLbitfield) = nullptr;
    void (*Enable)(GLenum) = nullptr;
    void (*Disable)(GLenum) = nullptr;
    void (*DepthFunc)(GLenum) = nullptr;
    void (*DepthMask)(GLboolean) = nullptr;
    void (*DrawArrays)(GLenum, GLint, GLsizei) = nullptr;
    void (*Finish)() = nullptr;

    void (*GenTextures)(GLsizei, GLuint*) = nullptr;
    void (*BindTexture)(GLenum, GLuint) = nullptr;
    void (*ActiveTexture)(GLenum) = nullptr;
    void (*TexParameteri)(GLenum, GLenum, GLint) = nullptr;
    void (*TexImage2D)(GLenum, GLint, GLint, GLsizei, GLsizei, GLint, GLenum, GLenum,
                       const void*) = nullptr;
    void (*DeleteTextures)(GLsizei, const GLuint*) = nullptr;

    void (*GenFramebuffers)(GLsizei, GLuint*) = nullptr;
    void (*BindFramebuffer)(GLenum, GLuint) = nullptr;
    void (*FramebufferTexture2D)(GLenum, GLenum, GLenum, GLuint, GLint) = nullptr;
    GLenum (*CheckFramebufferStatus)(GLenum) = nullptr;
    void (*DrawBuffer)(GLenum) = nullptr;
    void (*ReadBuffer)(GLenum) = nullptr;
    void (*DeleteFramebuffers)(GLsizei, const GLuint*) = nullptr;

    void (*GenBuffers)(GLsizei, GLuint*) = nullptr;
    void (*BindBuffer)(GLenum, GLuint) = nullptr;
    void (*BufferData)(GLenum, GLsizeiptr, const void*, GLenum) = nullptr;
    void (*GetBufferSubData)(GLenum, GLintptr, GLsizeiptr, void*) = nullptr;
    void (*BindBufferBase)(GLenum, GLuint, GLuint) = nullptr;
    void (*DeleteBuffers)(GLsizei, const GLuint*) = nullptr;

    void (*GenVertexArrays)(GLsizei, GLuint*) = nullptr;
    void (*BindVertexArray)(GLuint) = nullptr;
    void (*EnableVertexAttribArray)(GLuint) = nullptr;
    void (*VertexAttribPointer)(GLuint, GLint, GLenum, GLboolean, GLsizei, const void*) = nullptr;
    void (*DeleteVertexArrays)(GLsizei, const GLuint*) = nullptr;

    GLuint (*CreateShader)(GLenum) = nullptr;
    void (*ShaderSource)(GLuint, GLsizei, const GLchar* const*, const GLint*) = nullptr;
    void (*CompileShader)(GLuint) = nullptr;
    void (*GetShaderiv)(GLuint, GLenum, GLint*) = nullptr;
    void (*GetShaderInfoLog)(GLuint, GLsizei, GLsizei*, GLchar*) = nullptr;
    void (*DeleteShader)(GLuint) = nullptr;

    GLuint (*CreateProgram)() = nullptr;
    void (*AttachShader)(GLuint, GLuint) = nullptr;
    void (*LinkProgram)(GLuint) = nullptr;
    void (*GetProgramiv)(GLuint, GLenum, GLint*) = nullptr;
    void (*GetProgramInfoLog)(GLuint, GLsizei, GLsizei*, GLchar*) = nullptr;
    void (*UseProgram)(GLuint) = nullptr;
    void (*DeleteProgram)(GLuint) = nullptr;

    GLint (*GetUniformLocation)(GLuint, const GLchar*) = nullptr;
    void (*Uniform1i)(GLint, GLint) = nullptr;
    void (*Uniform1f)(GLint, GLfloat) = nullptr;
    void (*Uniform1ui)(GLint, GLuint) = nullptr;
    void (*Uniform2i)(GLint, GLint, GLint) = nullptr;
    void (*Uniform2ui)(GLint, GLuint, GLuint) = nullptr;
    void (*UniformMatrix4fv)(GLint, GLsizei, GLboolean, const GLfloat*) = nullptr;

    void (*GenQueries)(GLsizei, GLuint*) = nullptr;
    void (*DeleteQueries)(GLsizei, const GLuint*) = nullptr;
    void (*BeginQuery)(GLenum, GLuint) = nullptr;
    void (*EndQuery)(GLenum) = nullptr;
    void (*GetQueryObjectuiv)(GLuint, GLenum, GLuint*) = nullptr;

    void (*BindImageTexture)(GLuint, GLuint, GLint, GLboolean, GLint, GLenum, GLenum) = nullptr;
    void (*DispatchCompute)(GLuint, GLuint, GLuint) = nullptr;
    void (*MemoryBarrier)(GLbitfield) = nullptr;
};

class GlContext {
public:
    GlContext() = default;
    ~GlContext();
    GlContext(const GlContext&) = delete;
    GlContext& operator=(const GlContext&) = delete;

    bool create(std::string& error);
    void destroy();
    bool valid() const { return api_.CreateProgram != nullptr; }

    const GlApi& api() const { return api_; }
    const std::string& renderer() const { return renderer_; }
    const std::string& version() const { return version_; }

private:
    template <typename T>
    bool load(T& target, const char* name, std::string& error);
    bool loadEgl(std::string& error);
    bool loadGl(std::string& error);
    void* eglHandle_ = nullptr;
    void* glHandle_ = nullptr;
    void* display_ = nullptr;
    void* context_ = nullptr;
    void* eglGetProcAddress_ = nullptr;
    GlApi api_{};
    std::string renderer_;
    std::string version_;
};

GLuint compileProgram(const GlApi& gl, const char* vertexSource, const char* fragmentSource,
                      const char* computeSource, std::string& error);

GLuint compileCompute(const GlApi& gl, const char* source, std::string& error);

}  // namespace hzb
