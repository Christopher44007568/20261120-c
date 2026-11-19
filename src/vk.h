#pragma once
#include <vulkan/vulkan.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <string>
#include <stdexcept>

#define VK_CHECK(x) do { VkResult r_ = (x); if (r_ != VK_SUCCESS) { \
    fprintf(stderr, "VK_CHECK failed (%d) at %s:%d\n", (int)r_, __FILE__, __LINE__); \
    exit(1); } } while (0)

struct VkCtx {
    VkInstance instance = VK_NULL_HANDLE;
    VkPhysicalDevice phys = VK_NULL_HANDLE;
    VkDevice device = VK_NULL_HANDLE;
    VkQueue queue = VK_NULL_HANDLE;
    uint32_t queueFamily = 0;
    VkCommandPool cmdPool = VK_NULL_HANDLE;
    VkPhysicalDeviceProperties props{};
    VkPhysicalDeviceMemoryProperties memProps{};
};

static inline void vkCtxInit(VkCtx& c) {
    VkApplicationInfo ai{VK_STRUCTURE_TYPE_APPLICATION_INFO};
    ai.pApplicationName = "msaa-cutout-lab";
    ai.apiVersion = VK_API_VERSION_1_1;
    VkInstanceCreateInfo ici{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};
    ici.pApplicationInfo = &ai;
    VK_CHECK(vkCreateInstance(&ici, nullptr, &c.instance));
    uint32_t n = 0;
    vkEnumeratePhysicalDevices(c.instance, &n, nullptr);
    if (n == 0) { fprintf(stderr, "no Vulkan device\n"); exit(1); }
    std::vector<VkPhysicalDevice> devs(n);
    vkEnumeratePhysicalDevices(c.instance, &n, devs.data());
    c.phys = devs[0];
    vkGetPhysicalDeviceProperties(c.phys, &c.props);
    vkGetPhysicalDeviceMemoryProperties(c.phys, &c.memProps);
    uint32_t qn = 0;
    vkGetPhysicalDeviceQueueFamilyProperties(c.phys, &qn, nullptr);
    std::vector<VkQueueFamilyProperties> qp(qn);
    vkGetPhysicalDeviceQueueFamilyProperties(c.phys, &qn, qp.data());
    for (uint32_t i = 0; i < qn; i++)
        if (qp[i].queueFlags & VK_QUEUE_GRAPHICS_BIT) { c.queueFamily = i; break; }
    float prio = 1.0f;
    VkDeviceQueueCreateInfo qci{VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO};
    qci.queueFamilyIndex = c.queueFamily;
    qci.queueCount = 1;
    qci.pQueuePriorities = &prio;
    VkDeviceCreateInfo dci{VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO};
    dci.queueCreateInfoCount = 1;
    dci.pQueueCreateInfos = &qci;
    VK_CHECK(vkCreateDevice(c.phys, &dci, nullptr, &c.device));
    vkGetDeviceQueue(c.device, c.queueFamily, 0, &c.queue);
    VkCommandPoolCreateInfo cpi{VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO};
    cpi.queueFamilyIndex = c.queueFamily;
    cpi.flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT;
    VK_CHECK(vkCreateCommandPool(c.device, &cpi, nullptr, &c.cmdPool));
}

static inline uint32_t findMemType(const VkCtx& c, uint32_t bits, VkMemoryPropertyFlags fl) {
    for (uint32_t i = 0; i < c.memProps.memoryTypeCount; i++)
        if ((bits & (1u << i)) && (c.memProps.memoryTypes[i].propertyFlags & fl) == fl)
            return i;
    fprintf(stderr, "no memory type\n"); exit(1);
}

struct GpuBuffer { VkBuffer buf = VK_NULL_HANDLE; VkDeviceMemory mem = VK_NULL_HANDLE; VkDeviceSize size = 0; };

static inline GpuBuffer createBuffer(const VkCtx& c, VkDeviceSize size, VkBufferUsageFlags usage,
                                     VkMemoryPropertyFlags props) {
    GpuBuffer b; b.size = size;
    VkBufferCreateInfo bi{VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO};
    bi.size = size; bi.usage = usage;
    VK_CHECK(vkCreateBuffer(c.device, &bi, nullptr, &b.buf));
    VkMemoryRequirements req;
    vkGetBufferMemoryRequirements(c.device, b.buf, &req);
    VkMemoryAllocateInfo mai{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};
    mai.allocationSize = req.size;
    mai.memoryTypeIndex = findMemType(c, req.memoryTypeBits, props);
    VK_CHECK(vkAllocateMemory(c.device, &mai, nullptr, &b.mem));
    VK_CHECK(vkBindBufferMemory(c.device, b.buf, b.mem, 0));
    return b;
}

static inline void destroyBuffer(const VkCtx& c, GpuBuffer& b) {
    if (b.buf) vkDestroyBuffer(c.device, b.buf, nullptr);
    if (b.mem) vkFreeMemory(c.device, b.mem, nullptr);
    b = {};
}

struct GpuImage {
    VkImage img = VK_NULL_HANDLE; VkDeviceMemory mem = VK_NULL_HANDLE;
    VkImageView view = VK_NULL_HANDLE; VkFormat format; uint32_t w, h;
};

static inline GpuImage createImage(const VkCtx& c, uint32_t w, uint32_t h, VkFormat fmt,
                                   VkSampleCountFlagBits samples, VkImageUsageFlags usage) {
    GpuImage im; im.format = fmt; im.w = w; im.h = h;
    VkImageCreateInfo ii{VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO};
    ii.imageType = VK_IMAGE_TYPE_2D;
    ii.format = fmt; ii.extent = {w, h, 1};
    ii.mipLevels = 1; ii.arrayLayers = 1;
    ii.samples = samples; ii.tiling = VK_IMAGE_TILING_OPTIMAL;
    ii.usage = usage; ii.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
    VK_CHECK(vkCreateImage(c.device, &ii, nullptr, &im.img));
    VkMemoryRequirements req;
    vkGetImageMemoryRequirements(c.device, im.img, &req);
    VkMemoryAllocateInfo mai{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};
    mai.allocationSize = req.size;
    mai.memoryTypeIndex = findMemType(c, req.memoryTypeBits, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT);
    VK_CHECK(vkAllocateMemory(c.device, &mai, nullptr, &im.mem));
    VK_CHECK(vkBindImageMemory(c.device, im.img, im.mem, 0));
    VkImageViewCreateInfo vi{VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO};
    vi.image = im.img; vi.viewType = VK_IMAGE_VIEW_TYPE_2D; vi.format = fmt;
    bool depth = (fmt == VK_FORMAT_D32_SFLOAT);
    vi.subresourceRange = {depth ? VK_IMAGE_ASPECT_DEPTH_BIT : VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
    VK_CHECK(vkCreateImageView(c.device, &vi, nullptr, &im.view));
    return im;
}

static inline void destroyImage(const VkCtx& c, GpuImage& im) {
    if (im.view) vkDestroyImageView(c.device, im.view, nullptr);
    if (im.img) vkDestroyImage(c.device, im.img, nullptr);
    if (im.mem) vkFreeMemory(c.device, im.mem, nullptr);
    im = {};
}

static inline VkCommandBuffer beginCmd(const VkCtx& c) {
    VkCommandBufferAllocateInfo ai{VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO};
    ai.commandPool = c.cmdPool; ai.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY; ai.commandBufferCount = 1;
    VkCommandBuffer cmd;
    VK_CHECK(vkAllocateCommandBuffers(c.device, &ai, &cmd));
    VkCommandBufferBeginInfo bi{VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};
    bi.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
    VK_CHECK(vkBeginCommandBuffer(cmd, &bi));
    return cmd;
}

static inline void submitCmd(const VkCtx& c, VkCommandBuffer cmd) {
    VK_CHECK(vkEndCommandBuffer(cmd));
    VkSubmitInfo si{VK_STRUCTURE_TYPE_SUBMIT_INFO};
    si.commandBufferCount = 1; si.pCommandBuffers = &cmd;
    VK_CHECK(vkQueueSubmit(c.queue, 1, &si, VK_NULL_HANDLE));
    VK_CHECK(vkQueueWaitIdle(c.queue));
    vkFreeCommandBuffers(c.device, c.cmdPool, 1, &cmd);
}

static inline void transitionImage(VkCommandBuffer cmd, VkImage img, VkImageAspectFlags aspect,
                                   VkImageLayout oldL, VkImageLayout newL,
                                   VkPipelineStageFlags srcStage, VkPipelineStageFlags dstStage,
                                   VkAccessFlags srcAcc, VkAccessFlags dstAcc) {
    VkImageMemoryBarrier b{VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER};
    b.oldLayout = oldL; b.newLayout = newL;
    b.srcAccessMask = srcAcc; b.dstAccessMask = dstAcc;
    b.image = img;
    b.subresourceRange = {aspect, 0, 1, 0, 1};
    vkCmdPipelineBarrier(cmd, srcStage, dstStage, 0, 0, nullptr, 0, nullptr, 1, &b);
}

static inline VkShaderModule loadShader(const VkCtx& c, const std::string& path) {
    FILE* f = fopen(path.c_str(), "rb");
    if (!f) { fprintf(stderr, "cannot open shader %s\n", path.c_str()); exit(1); }
    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    fseek(f, 0, SEEK_SET);
    std::vector<uint32_t> code((sz + 3) / 4);
    fread(code.data(), 1, sz, f);
    fclose(f);
    VkShaderModuleCreateInfo ci{VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO};
    ci.codeSize = sz; ci.pCode = code.data();
    VkShaderModule m;
    VK_CHECK(vkCreateShaderModule(c.device, &ci, nullptr, &m));
    return m;
}
