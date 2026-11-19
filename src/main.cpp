// Multisampled transparency-cutout lab: fixed-threshold discard vs alpha-to-coverage.
// Headless Vulkan experiment for thin-leaf / perforated-metal geometry.
#include "util.h"
#include "vk.h"
#include <cstdarg>

static const int W = 640, H = 360;
static const int FRAMES = 96;

struct PushBlock {
    Mat4 mvp;
    float tint[4];
    float params[4];  // alphaOverride, mode(0=discard,1=a2c), isBackground, unused
    float uvXform[4]; // scale.xy, offset.zw
};

struct DrawItem {
    Mat4 model;
    float tint[4] = {1, 1, 1, 1};
    float alphaOverride = -1.0f;
    float isBackground = 0.0f;
    float uvScale[2] = {1, 1};
    float uvOffset[2] = {0, 0};
};

struct Renderer {
    VkSampleCountFlagBits samples;
    bool a2c;
    GpuImage msColor, resolve, depth;
    VkRenderPass renderPass = VK_NULL_HANDLE;
    VkFramebuffer fb = VK_NULL_HANDLE;
    VkPipeline pipeline = VK_NULL_HANDLE;
    VkPipelineLayout pipeLayout = VK_NULL_HANDLE;
    GpuBuffer readback;
};

static VkCtx g_ctx;
static VkDescriptorSetLayout g_descLayout = VK_NULL_HANDLE;
static VkDescriptorPool g_descPool = VK_NULL_HANDLE;
static VkDescriptorSet g_descSet = VK_NULL_HANDLE;
static GpuImage g_atlas;
static VkSampler g_sampler = VK_NULL_HANDLE;
static GpuBuffer g_vb, g_ib;

static void createRenderPass(Renderer& r) {
    VkAttachmentDescription att[3]{};
    att[0].format = VK_FORMAT_R8G8B8A8_UNORM;
    att[0].samples = r.samples;
    att[0].loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR;
    att[0].storeOp = VK_ATTACHMENT_STORE_OP_STORE; // kept for per-sample extraction
    att[0].initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
    att[0].finalLayout = VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL;
    att[1].format = VK_FORMAT_R8G8B8A8_UNORM;
    att[1].samples = VK_SAMPLE_COUNT_1_BIT;
    att[1].loadOp = VK_ATTACHMENT_LOAD_OP_DONT_CARE;
    att[1].storeOp = VK_ATTACHMENT_STORE_OP_STORE;
    att[1].initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
    att[1].finalLayout = VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL;
    att[2].format = VK_FORMAT_D32_SFLOAT;
    att[2].samples = r.samples;
    att[2].loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR;
    att[2].storeOp = VK_ATTACHMENT_STORE_OP_DONT_CARE;
    att[2].initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
    att[2].finalLayout = VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL;
    VkAttachmentReference colorRef{0, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL};
    VkAttachmentReference resolveRef{1, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL};
    VkAttachmentReference depthRef{2, VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL};
    VkSubpassDescription sub{};
    sub.pipelineBindPoint = VK_PIPELINE_BIND_POINT_GRAPHICS;
    sub.colorAttachmentCount = 1;
    sub.pColorAttachments = &colorRef;
    sub.pResolveAttachments = &resolveRef;
    sub.pDepthStencilAttachment = &depthRef;
    VkRenderPassCreateInfo ri{VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO};
    ri.attachmentCount = 3;
    ri.pAttachments = att;
    ri.subpassCount = 1;
    ri.pSubpasses = &sub;
    VK_CHECK(vkCreateRenderPass(g_ctx.device, &ri, nullptr, &r.renderPass));
}

static void createPipeline(Renderer& r, VkShaderModule vert, VkShaderModule frag) {
    VkPushConstantRange pcr{VK_SHADER_STAGE_VERTEX_BIT | VK_SHADER_STAGE_FRAGMENT_BIT, 0,
                            sizeof(PushBlock)};
    VkPipelineLayoutCreateInfo pli{VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO};
    pli.setLayoutCount = 1;
    pli.pSetLayouts = &g_descLayout;
    pli.pushConstantRangeCount = 1;
    pli.pPushConstantRanges = &pcr;
    VK_CHECK(vkCreatePipelineLayout(g_ctx.device, &pli, nullptr, &r.pipeLayout));

    VkPipelineShaderStageCreateInfo stages[2]{};
    stages[0].sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO;
    stages[0].stage = VK_SHADER_STAGE_VERTEX_BIT;
    stages[0].module = vert;
    stages[0].pName = "main";
    stages[1].sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO;
    stages[1].stage = VK_SHADER_STAGE_FRAGMENT_BIT;
    stages[1].module = frag;
    stages[1].pName = "main";

    VkVertexInputBindingDescription binding{0, sizeof(float) * 5, VK_VERTEX_INPUT_RATE_VERTEX};
    VkVertexInputAttributeDescription attrs[2] = {
        {0, 0, VK_FORMAT_R32G32B32_SFLOAT, 0},
        {1, 0, VK_FORMAT_R32G32_SFLOAT, sizeof(float) * 3}};
    VkPipelineVertexInputStateCreateInfo vin{VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO};
    vin.vertexBindingDescriptionCount = 1;
    vin.pVertexBindingDescriptions = &binding;
    vin.vertexAttributeDescriptionCount = 2;
    vin.pVertexAttributeDescriptions = attrs;
    VkPipelineInputAssemblyStateCreateInfo ia{VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO};
    ia.topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST;
    VkViewport vp{0, (float)H, (float)W, -(float)H, 0, 1}; // negative height: y-up NDC
    VkRect2D sc{{0, 0}, {(uint32_t)W, (uint32_t)H}};
    VkPipelineViewportStateCreateInfo vps{VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO};
    vps.viewportCount = 1; vps.pViewports = &vp;
    vps.scissorCount = 1; vps.pScissors = &sc;
    VkPipelineRasterizationStateCreateInfo rs{VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO};
    rs.polygonMode = VK_POLYGON_MODE_FILL;
    rs.cullMode = VK_CULL_MODE_NONE;
    rs.lineWidth = 1.0f;
    VkPipelineMultisampleStateCreateInfo ms{VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO};
    ms.rasterizationSamples = r.samples;
    ms.alphaToCoverageEnable = r.a2c ? VK_TRUE : VK_FALSE;
    VkPipelineDepthStencilStateCreateInfo ds{VK_STRUCTURE_TYPE_PIPELINE_DEPTH_STENCIL_STATE_CREATE_INFO};
    ds.depthTestEnable = VK_TRUE;
    ds.depthWriteEnable = VK_TRUE;
    ds.depthCompareOp = VK_COMPARE_OP_LESS;
    VkPipelineColorBlendAttachmentState cba{};
    cba.colorWriteMask = VK_COLOR_COMPONENT_R_BIT | VK_COLOR_COMPONENT_G_BIT |
                         VK_COLOR_COMPONENT_B_BIT | VK_COLOR_COMPONENT_A_BIT;
    cba.blendEnable = VK_FALSE; // cutout: no blending, coverage comes from sample mask
    VkPipelineColorBlendStateCreateInfo cb{VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO};
    cb.attachmentCount = 1;
    cb.pAttachments = &cba;
    VkGraphicsPipelineCreateInfo pi{VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO};
    pi.stageCount = 2;
    pi.pStages = stages;
    pi.pVertexInputState = &vin;
    pi.pInputAssemblyState = &ia;
    pi.pViewportState = &vps;
    pi.pRasterizationState = &rs;
    pi.pMultisampleState = &ms;
    pi.pDepthStencilState = &ds;
    pi.pColorBlendState = &cb;
    pi.layout = r.pipeLayout;
    pi.renderPass = r.renderPass;
    VK_CHECK(vkCreateGraphicsPipelines(g_ctx.device, VK_NULL_HANDLE, 1, &pi, nullptr, &r.pipeline));
}

static void createRenderer(Renderer& r, VkSampleCountFlagBits samples, bool a2c,
                           VkShaderModule vert, VkShaderModule frag) {
    r.samples = samples;
    r.a2c = a2c;
    VkImageUsageFlags msUsage = VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | VK_IMAGE_USAGE_SAMPLED_BIT;
    r.msColor = createImage(g_ctx, W, H, VK_FORMAT_R8G8B8A8_UNORM, samples, msUsage);
    r.resolve = createImage(g_ctx, W, H, VK_FORMAT_R8G8B8A8_UNORM, VK_SAMPLE_COUNT_1_BIT,
                            VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT);
    r.depth = createImage(g_ctx, W, H, VK_FORMAT_D32_SFLOAT, samples,
                          VK_IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT);
    createRenderPass(r);
    VkImageView views[3] = {r.msColor.view, r.resolve.view, r.depth.view};
    VkFramebufferCreateInfo fi{VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO};
    fi.renderPass = r.renderPass;
    fi.attachmentCount = 3;
    fi.pAttachments = views;
    fi.width = W; fi.height = H; fi.layers = 1;
    VK_CHECK(vkCreateFramebuffer(g_ctx.device, &fi, nullptr, &r.fb));
    createPipeline(r, vert, frag);
    r.readback = createBuffer(g_ctx, (VkDeviceSize)W * H * 4, VK_BUFFER_USAGE_TRANSFER_DST_BIT,
                              VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT |
                              VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
}

static void destroyRenderer(Renderer& r) {
    vkDestroyPipeline(g_ctx.device, r.pipeline, nullptr);
    vkDestroyPipelineLayout(g_ctx.device, r.pipeLayout, nullptr);
    vkDestroyFramebuffer(g_ctx.device, r.fb, nullptr);
    vkDestroyRenderPass(g_ctx.device, r.renderPass, nullptr);
    destroyImage(g_ctx, r.msColor);
    destroyImage(g_ctx, r.resolve);
    destroyImage(g_ctx, r.depth);
    destroyBuffer(g_ctx, r.readback);
}

// Renders one frame and reads back the resolved image (RGBA8, row 0 = top).
static void renderFrame(Renderer& r, const Mat4& vp, const std::vector<DrawItem>& draws,
                        std::vector<uint8_t>& outRGBA) {
    VkCommandBuffer cmd = beginCmd(g_ctx);
    VkClearValue clears[3]{};
    clears[0].color = {{0, 0, 0, 1}};
    clears[2].depthStencil = {1.0f, 0};
    VkRenderPassBeginInfo rbi{VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO};
    rbi.renderPass = r.renderPass;
    rbi.framebuffer = r.fb;
    rbi.renderArea = {{0, 0}, {(uint32_t)W, (uint32_t)H}};
    rbi.clearValueCount = 3;
    rbi.pClearValues = clears;
    vkCmdBeginRenderPass(cmd, &rbi, VK_SUBPASS_CONTENTS_INLINE);
    vkCmdBindPipeline(cmd, VK_PIPELINE_BIND_POINT_GRAPHICS, r.pipeline);
    vkCmdBindDescriptorSets(cmd, VK_PIPELINE_BIND_POINT_GRAPHICS, r.pipeLayout, 0, 1,
                            &g_descSet, 0, nullptr);
    VkDeviceSize off = 0;
    vkCmdBindVertexBuffers(cmd, 0, 1, &g_vb.buf, &off);
    vkCmdBindIndexBuffer(cmd, g_ib.buf, 0, VK_INDEX_TYPE_UINT16);
    for (const DrawItem& d : draws) {
        PushBlock pc{};
        pc.mvp = mat4Mul(vp, d.model);
        memcpy(pc.tint, d.tint, sizeof(pc.tint));
        pc.params[0] = d.alphaOverride;
        pc.params[1] = r.a2c ? 1.0f : 0.0f;
        pc.params[2] = d.isBackground;
        pc.uvXform[0] = d.uvScale[0]; pc.uvXform[1] = d.uvScale[1];
        pc.uvXform[2] = d.uvOffset[0]; pc.uvXform[3] = d.uvOffset[1];
        vkCmdPushConstants(cmd, r.pipeLayout,
                           VK_SHADER_STAGE_VERTEX_BIT | VK_SHADER_STAGE_FRAGMENT_BIT,
                           0, sizeof(pc), &pc);
        vkCmdDrawIndexed(cmd, 6, 1, 0, 0, 0);
    }
    vkCmdEndRenderPass(cmd);
    transitionImage(cmd, r.resolve.img, VK_IMAGE_ASPECT_COLOR_BIT,
                    VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
                    VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT,
                    VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT, VK_ACCESS_TRANSFER_READ_BIT);
    VkBufferImageCopy copy{};
    copy.imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};
    copy.imageExtent = {(uint32_t)W, (uint32_t)H, 1};
    vkCmdCopyImageToBuffer(cmd, r.resolve.img, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
                           r.readback.buf, 1, &copy);
    submitCmd(g_ctx, cmd);
    // restore layout for next frame
    VkCommandBuffer cmd2 = beginCmd(g_ctx);
    transitionImage(cmd2, r.resolve.img, VK_IMAGE_ASPECT_COLOR_BIT,
                    VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL,
                    VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT,
                    VK_ACCESS_TRANSFER_READ_BIT, VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT);
    submitCmd(g_ctx, cmd2);
    outRGBA.resize((size_t)W * H * 4);
    void* p;
    VK_CHECK(vkMapMemory(g_ctx.device, r.readback.mem, 0, VK_WHOLE_SIZE, 0, &p));
    memcpy(outRGBA.data(), p, outRGBA.size());
    vkUnmapMemory(g_ctx.device, r.readback.mem);
}

// ---------------- global resources ----------------

static void uploadAtlas() {
    std::vector<uint8_t> px = buildAtlas();
    g_atlas = createImage(g_ctx, 512, 512, VK_FORMAT_R8G8B8A8_UNORM, VK_SAMPLE_COUNT_1_BIT,
                          VK_IMAGE_USAGE_SAMPLED_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT);
    GpuBuffer staging = createBuffer(g_ctx, px.size(), VK_BUFFER_USAGE_TRANSFER_SRC_BIT,
                                     VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT |
                                     VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
    void* p;
    VK_CHECK(vkMapMemory(g_ctx.device, staging.mem, 0, VK_WHOLE_SIZE, 0, &p));
    memcpy(p, px.data(), px.size());
    vkUnmapMemory(g_ctx.device, staging.mem);
    VkCommandBuffer cmd = beginCmd(g_ctx);
    transitionImage(cmd, g_atlas.img, VK_IMAGE_ASPECT_COLOR_BIT,
                    VK_IMAGE_LAYOUT_UNDEFINED, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
                    VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT,
                    0, VK_ACCESS_TRANSFER_WRITE_BIT);
    VkBufferImageCopy copy{};
    copy.imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};
    copy.imageExtent = {512, 512, 1};
    vkCmdCopyBufferToImage(cmd, staging.buf, g_atlas.img,
                           VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &copy);
    transitionImage(cmd, g_atlas.img, VK_IMAGE_ASPECT_COLOR_BIT,
                    VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL,
                    VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT,
                    VK_ACCESS_TRANSFER_WRITE_BIT, VK_ACCESS_SHADER_READ_BIT);
    submitCmd(g_ctx, cmd);
    destroyBuffer(g_ctx, staging);
    VkSamplerCreateInfo si{VK_STRUCTURE_TYPE_SAMPLER_CREATE_INFO};
    // Linear filtering gives intermediate alpha at texture edges, which is what
    // alpha-to-coverage converts into partial sample masks (nearest would make
    // every fragment alpha 0/1 and A2C could never produce partial coverage).
    si.magFilter = VK_FILTER_LINEAR;
    si.minFilter = VK_FILTER_LINEAR;
    si.addressModeU = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE;
    si.addressModeV = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE;
    si.addressModeW = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE;
    VK_CHECK(vkCreateSampler(g_ctx.device, &si, nullptr, &g_sampler));
}

static void createGlobalResources() {
    uploadAtlas();
    VkDescriptorSetLayoutBinding b{};
    b.binding = 0;
    b.descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER;
    b.descriptorCount = 1;
    b.stageFlags = VK_SHADER_STAGE_FRAGMENT_BIT;
    VkDescriptorSetLayoutCreateInfo li{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO};
    li.bindingCount = 1;
    li.pBindings = &b;
    VK_CHECK(vkCreateDescriptorSetLayout(g_ctx.device, &li, nullptr, &g_descLayout));
    VkDescriptorPoolSize ps{VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, 1};
    VkDescriptorPoolCreateInfo pi{VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO};
    pi.maxSets = 1;
    pi.poolSizeCount = 1;
    pi.pPoolSizes = &ps;
    VK_CHECK(vkCreateDescriptorPool(g_ctx.device, &pi, nullptr, &g_descPool));
    VkDescriptorSetAllocateInfo ai{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO};
    ai.descriptorPool = g_descPool;
    ai.descriptorSetCount = 1;
    ai.pSetLayouts = &g_descLayout;
    VK_CHECK(vkAllocateDescriptorSets(g_ctx.device, &ai, &g_descSet));
    VkDescriptorImageInfo ii{g_sampler, g_atlas.view, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL};
    VkWriteDescriptorSet w{VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET};
    w.dstSet = g_descSet;
    w.dstBinding = 0;
    w.descriptorCount = 1;
    w.descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER;
    w.pImageInfo = &ii;
    vkUpdateDescriptorSets(g_ctx.device, 1, &w, 0, nullptr);
    // shared unit quad (XY plane, uv = (x+0.5, y+0.5))
    float verts[] = {
        -0.5f, -0.5f, 0, 0, 0,
         0.5f, -0.5f, 0, 1, 0,
         0.5f,  0.5f, 0, 1, 1,
        -0.5f,  0.5f, 0, 0, 1};
    uint16_t idx[] = {0, 1, 2, 0, 2, 3};
    g_vb = createBuffer(g_ctx, sizeof(verts), VK_BUFFER_USAGE_VERTEX_BUFFER_BIT,
                        VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
    g_ib = createBuffer(g_ctx, sizeof(idx), VK_BUFFER_USAGE_INDEX_BUFFER_BIT,
                        VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
    void* p;
    VK_CHECK(vkMapMemory(g_ctx.device, g_vb.mem, 0, VK_WHOLE_SIZE, 0, &p));
    memcpy(p, verts, sizeof(verts));
    vkUnmapMemory(g_ctx.device, g_vb.mem);
    VK_CHECK(vkMapMemory(g_ctx.device, g_ib.mem, 0, VK_WHOLE_SIZE, 0, &p));
    memcpy(p, idx, sizeof(idx));
    vkUnmapMemory(g_ctx.device, g_ib.mem);
}

// ---------------- per-sample extraction (reads unresolved MS attachment) ----------------

struct Extractor {
    VkDescriptorSetLayout layout = VK_NULL_HANDLE;
    VkDescriptorPool pool = VK_NULL_HANDLE;
    VkDescriptorSet set = VK_NULL_HANDLE;
    VkPipelineLayout pipeLayout = VK_NULL_HANDLE;
    VkPipeline pipeline = VK_NULL_HANDLE;
    GpuBuffer outBuf;
};

static void createExtractor(Extractor& e, VkShaderModule comp) {
    VkDescriptorSetLayoutBinding bs[2]{};
    bs[0].binding = 0;
    bs[0].descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER;
    bs[0].descriptorCount = 1;
    bs[0].stageFlags = VK_SHADER_STAGE_COMPUTE_BIT;
    bs[1].binding = 1;
    bs[1].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER;
    bs[1].descriptorCount = 1;
    bs[1].stageFlags = VK_SHADER_STAGE_COMPUTE_BIT;
    VkDescriptorSetLayoutCreateInfo li{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO};
    li.bindingCount = 2;
    li.pBindings = bs;
    VK_CHECK(vkCreateDescriptorSetLayout(g_ctx.device, &li, nullptr, &e.layout));
    VkDescriptorPoolSize sizes[2] = {{VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, 1},
                                     {VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 1}};
    VkDescriptorPoolCreateInfo pi{VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO};
    pi.maxSets = 1;
    pi.poolSizeCount = 2;
    pi.pPoolSizes = sizes;
    VK_CHECK(vkCreateDescriptorPool(g_ctx.device, &pi, nullptr, &e.pool));
    VkDescriptorSetAllocateInfo ai{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO};
    ai.descriptorPool = e.pool;
    ai.descriptorSetCount = 1;
    ai.pSetLayouts = &e.layout;
    VK_CHECK(vkAllocateDescriptorSets(g_ctx.device, &ai, &e.set));
    e.outBuf = createBuffer(g_ctx, sizeof(float) * 4 * 64, VK_BUFFER_USAGE_STORAGE_BUFFER_BIT,
                            VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT |
                            VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
    VkPushConstantRange pcr{VK_SHADER_STAGE_COMPUTE_BIT, 0, 8 * 8 + 8};
    VkPipelineLayoutCreateInfo pli{VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO};
    pli.setLayoutCount = 1;
    pli.pSetLayouts = &e.layout;
    pli.pushConstantRangeCount = 1;
    pli.pPushConstantRanges = &pcr;
    VK_CHECK(vkCreatePipelineLayout(g_ctx.device, &pli, nullptr, &e.pipeLayout));
    VkComputePipelineCreateInfo ci{VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO};
    ci.stage.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO;
    ci.stage.stage = VK_SHADER_STAGE_COMPUTE_BIT;
    ci.stage.module = comp;
    ci.stage.pName = "main";
    ci.layout = e.pipeLayout;
    VK_CHECK(vkCreateComputePipelines(g_ctx.device, VK_NULL_HANDLE, 1, &ci, nullptr, &e.pipeline));
}

// Extracts per-sample RGBA for up to 8 pixels of r.msColor (pre-resolve).
static void extractSamples(Extractor& e, Renderer& r, const int pixels[][2], int count,
                           std::vector<std::vector<Vec4>>& out) {
    int nSamples = (int)r.samples;
    if (r.samples == VK_SAMPLE_COUNT_1_BIT) {
        // A 1x attachment is not multisample: read it directly via image copy.
        VkCommandBuffer cmd = beginCmd(g_ctx);
        transitionImage(cmd, r.msColor.img, VK_IMAGE_ASPECT_COLOR_BIT,
                        VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
                        VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT,
                        VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT, VK_ACCESS_TRANSFER_READ_BIT);
        VkBufferImageCopy copy{};
        copy.imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};
        copy.imageExtent = {(uint32_t)W, (uint32_t)H, 1};
        vkCmdCopyImageToBuffer(cmd, r.msColor.img, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
                               r.readback.buf, 1, &copy);
        submitCmd(g_ctx, cmd);
        VkCommandBuffer cmd2 = beginCmd(g_ctx);
        transitionImage(cmd2, r.msColor.img, VK_IMAGE_ASPECT_COLOR_BIT,
                        VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL,
                        VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT,
                        VK_ACCESS_TRANSFER_READ_BIT, VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT);
        submitCmd(g_ctx, cmd2);
        uint8_t* p;
        VK_CHECK(vkMapMemory(g_ctx.device, r.readback.mem, 0, VK_WHOLE_SIZE, 0, (void**)&p));
        out.assign(count, {});
        for (int i = 0; i < count; i++) {
            size_t o = ((size_t)pixels[i][1] * W + pixels[i][0]) * 4;
            out[i].push_back({p[o] / 255.0f, p[o + 1] / 255.0f, p[o + 2] / 255.0f, p[o + 3] / 255.0f});
        }
        vkUnmapMemory(g_ctx.device, r.readback.mem);
        return;
    }
    VkCommandBuffer cmd = beginCmd(g_ctx);
    transitionImage(cmd, r.msColor.img, VK_IMAGE_ASPECT_COLOR_BIT,
                    VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL,
                    VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT, VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,
                    VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT, VK_ACCESS_SHADER_READ_BIT);
    submitCmd(g_ctx, cmd);
    VkDescriptorImageInfo ii{g_sampler, r.msColor.view, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL};
    VkDescriptorBufferInfo bi{e.outBuf.buf, 0, VK_WHOLE_SIZE};
    VkWriteDescriptorSet ws[2]{};
    ws[0].sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;
    ws[0].dstSet = e.set; ws[0].dstBinding = 0; ws[0].descriptorCount = 1;
    ws[0].descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER; ws[0].pImageInfo = &ii;
    ws[1].sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;
    ws[1].dstSet = e.set; ws[1].dstBinding = 1; ws[1].descriptorCount = 1;
    ws[1].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER; ws[1].pBufferInfo = &bi;
    vkUpdateDescriptorSets(g_ctx.device, 2, ws, 0, nullptr);
    struct { int32_t px[8][2]; int32_t count; int32_t samples; } pc{};
    for (int i = 0; i < count; i++) { pc.px[i][0] = pixels[i][0]; pc.px[i][1] = pixels[i][1]; }
    pc.count = count;
    pc.samples = nSamples;
    VkCommandBuffer cmd2 = beginCmd(g_ctx);
    vkCmdBindPipeline(cmd2, VK_PIPELINE_BIND_POINT_COMPUTE, e.pipeline);
    vkCmdBindDescriptorSets(cmd2, VK_PIPELINE_BIND_POINT_COMPUTE, e.pipeLayout, 0, 1, &e.set, 0, nullptr);
    vkCmdPushConstants(cmd2, e.pipeLayout, VK_SHADER_STAGE_COMPUTE_BIT, 0, sizeof(pc), &pc);
    vkCmdDispatch(cmd2, 1, 1, 1);
    submitCmd(g_ctx, cmd2);
    VkCommandBuffer cmd3 = beginCmd(g_ctx);
    transitionImage(cmd3, r.msColor.img, VK_IMAGE_ASPECT_COLOR_BIT,
                    VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL,
                    VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT,
                    VK_ACCESS_SHADER_READ_BIT, VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT);
    submitCmd(g_ctx, cmd3);
    float* p;
    VK_CHECK(vkMapMemory(g_ctx.device, e.outBuf.mem, 0, VK_WHOLE_SIZE, 0, (void**)&p));
    out.assign(count, {});
    for (int i = 0; i < count; i++)
        for (int s = 0; s < nSamples; s++) {
            float* v = p + (i * nSamples + s) * 4;
            out[i].push_back({v[0], v[1], v[2], v[3]});
        }
    vkUnmapMemory(g_ctx.device, e.outBuf.mem);
}

// ---------------- scenes (shared geometry + atlas for both transparency modes) ----------------

static DrawItem makeQuad(Mat4 model, float us, float vs, float uo, float vo) {
    DrawItem d;
    d.model = model;
    d.uvScale[0] = us; d.uvScale[1] = vs;
    d.uvOffset[0] = uo; d.uvOffset[1] = vo;
    return d;
}

// Sweep scene: perforated metal panel + thin-leaf quads (one near edge-on => near-horizontal
// silhouette) in front of a gradient backdrop.
static std::vector<DrawItem> buildSweepScene() {
    std::vector<DrawItem> s;
    DrawItem bg = makeQuad(mat4Mul(mat4Translate(v3(0, 0, -6)), mat4Scale(40, 24, 1)), 1, 1, 0, 0);
    bg.isBackground = 1.0f;
    s.push_back(bg);
    // perforated metal mesh panel (atlas region B)
    s.push_back(makeQuad(mat4Mul(mat4Translate(v3(0, 0, 0)), mat4Scale(7, 4.5f, 1)),
                         0.49f, 0.49f, 0.505f, 0.005f));
    // thin-leaf quads (atlas region A)
    s.push_back(makeQuad(mat4Mul(mat4Translate(v3(-1.9f, 0.9f, 0.9f)),
                                 mat4Mul(mat4RotateY(0.5f), mat4Scale(2.4f, 2.4f, 1))),
                         0.49f, 0.49f, 0.005f, 0.005f));
    s.push_back(makeQuad(mat4Mul(mat4Translate(v3(1.7f, -0.6f, 1.3f)),
                                 mat4Mul(mat4RotateY(-0.4f), mat4Scale(2.0f, 2.0f, 1))),
                         0.49f, 0.49f, 0.005f, 0.005f));
    // near-horizontal leaf silhouette: quad tilted almost edge-on to the view
    s.push_back(makeQuad(mat4Mul(mat4Translate(v3(0.2f, 1.35f, 1.0f)),
                                 mat4Mul(mat4RotateX(1.45f),
                                 mat4Mul(mat4RotateZ(0.06f), mat4Scale(3.2f, 3.2f, 1)))),
                         0.49f, 0.49f, 0.005f, 0.005f));
    return s;
}

// Static analysis scene: analytic straight alpha edge (near-horizontal), a uniform
// quarter-alpha test block, and an opaque occluder in front of the block's right half.
static std::vector<DrawItem> buildStaticScene() {
    std::vector<DrawItem> s;
    DrawItem bg = makeQuad(mat4Mul(mat4Translate(v3(0, 0, -6)), mat4Scale(40, 24, 1)), 1, 1, 0, 0);
    bg.isBackground = 1.0f;
    s.push_back(bg);
    // analytic edge quad (atlas region C: alpha step at local v=0.5), tilted ~2 deg,
    // placed upper-right so it stays clear of the test block and occluder
    s.push_back(makeQuad(mat4Mul(mat4Translate(v3(1.2f, 1.3f, 0)),
                                 mat4Mul(mat4RotateZ(0.035f), mat4Scale(5, 5, 1))),
                         0.49f, 0.49f, 0.005f, 0.505f));
    // uniform quarter-alpha test block (left-bottom area)
    DrawItem block = makeQuad(mat4Mul(mat4Translate(v3(-3.0f, -1.6f, 1.0f)), mat4Scale(1.6f, 1.6f, 1)),
                              1, 1, 0, 0);
    block.alphaOverride = 0.25f;
    block.tint[0] = 1.0f; block.tint[1] = 0.5f; block.tint[2] = 0.1f;
    s.push_back(block);
    // opaque occluder covering the right quarter of the block, closer to camera
    DrawItem occ = makeQuad(mat4Mul(mat4Translate(v3(-1.9f, -1.6f, 2.0f)), mat4Scale(0.8f, 1.8f, 1)),
                            1, 1, 0, 0);
    occ.alphaOverride = 1.0f;
    occ.tint[0] = 0.75f; occ.tint[1] = 0.12f; occ.tint[2] = 0.12f;
    s.push_back(occ);
    return s;
}

static Mat4 sweepCamera(int frame) {
    float t = (float)frame / (FRAMES - 1);
    float a = -0.38f + 0.76f * t; // slow orbit across the perforations
    Vec3 eye = v3(6.4f * std::sin(a), 1.1f + 0.35f * std::sin(t * 6.2831f), 6.4f * std::cos(a));
    return mat4Mul(mat4Perspective(0.72f, (float)W / H, 0.1f, 100.0f),
                   mat4LookAt(eye, v3(0, 0.35f, 0), v3(0, 1, 0)));
}

static Mat4 staticCamera() {
    return mat4Mul(mat4Perspective(0.72f, (float)W / H, 0.1f, 100.0f),
                   mat4LookAt(v3(0, 0, 8), v3(0, 0, 0), v3(0, 1, 0)));
}

static float luminance(const std::vector<uint8_t>& img, int x, int y) {
    size_t i = ((size_t)y * W + x) * 4;
    return (0.2126f * img[i] + 0.7152f * img[i + 1] + 0.0722f * img[i + 2]) / 255.0f;
}

static double meanLuminance(const std::vector<uint8_t>& img) {
    double s = 0;
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) s += luminance(img, x, y);
    return s / ((double)W * H);
}

// Central region of interest: where the perforation rims and the near-horizontal
// leaf silhouette live; full-frame averages wash the flicker out.
static double roiLuminance(const std::vector<uint8_t>& img) {
    double s = 0; int n = 0;
    for (int y = H / 8; y < 7 * H / 8; y++)
        for (int x = W / 8; x < 7 * W / 8; x++) { s += luminance(img, x, y); n++; }
    return s / n;
}

static double flickerVsPrev(const std::vector<uint8_t>& img,
                            const std::vector<uint8_t>& prev) {
    double s = 0; int n = 0;
    for (int y = H / 8; y < 7 * H / 8; y++)
        for (int x = W / 8; x < 7 * W / 8; x++) {
            s += std::fabs(luminance(img, x, y) - luminance(prev, x, y));
            n++;
        }
    return s / n;
}

// ---------------- luminance fluctuation plot ----------------

struct Curve { std::vector<double> v; uint8_t r, g, b; };

static void plotCurves(const std::string& path, std::vector<Curve> curves, int n) {
    const int PW = 960, PH = 540, ML = 60, MR = 20, MT = 20, MB = 40;
    std::vector<uint8_t> img((size_t)PW * PH * 4, 255);
    auto set = [&](int x, int y, uint8_t r, uint8_t g, uint8_t b) {
        if (x < 0 || y < 0 || x >= PW || y >= PH) return;
        size_t i = ((size_t)y * PW + x) * 4;
        img[i] = r; img[i + 1] = g; img[i + 2] = b; img[i + 3] = 255;
    };
    double lo = 1e9, hi = -1e9;
    for (auto& c : curves) for (double v : c.v) { lo = std::min(lo, v); hi = std::max(hi, v); }
    double pad = std::max(1e-4, (hi - lo) * 0.15);
    lo -= pad; hi += pad;
    auto X = [&](int i) { return ML + (int)((double)i / (n - 1) * (PW - ML - MR)); };
    auto Y = [&](double v) { return MT + (int)((hi - v) / (hi - lo) * (PH - MT - MB)); };
    for (int x = ML; x < PW - MR; x++) { set(x, Y(lo), 0, 0, 0); set(x, Y(hi), 0, 0, 0); }
    for (int y = MT; y < PH - MB; y++) { set(ML, y, 0, 0, 0); set(PW - MR - 1, y, 0, 0, 0); }
    for (int g = 1; g < 5; g++) { // horizontal gridlines
        int y = MT + g * (PH - MT - MB) / 5;
        for (int x = ML; x < PW - MR; x += 2) set(x, y, 210, 210, 210);
    }
    for (auto& c : curves) {
        for (int i = 1; i < (int)c.v.size(); i++) {
            int x0 = X(i - 1), y0 = Y(c.v[i - 1]), x1 = X(i), y1 = Y(c.v[i]);
            int dx = abs(x1 - x0), dy = -abs(y1 - y0);
            int sx = x0 < x1 ? 1 : -1, sy = y0 < y1 ? 1 : -1, err = dx + dy;
            while (true) {
                set(x0, y0, c.r, c.g, c.b);
                if (x0 == x1 && y0 == y1) break;
                int e2 = 2 * err;
                if (e2 >= dy) { err += dy; x0 += sx; }
                if (e2 <= dx) { err += dx; y0 += sy; }
            }
        }
    }
    // legend swatches (mapping documented in report.txt)
    for (size_t k = 0; k < curves.size(); k++)
        for (int x = 0; x < 40; x++)
            for (int y = 0; y < 8; y++)
                set(ML + 20 + (int)k * 60 + x, PH - MB + 18 + y, curves[k].r, curves[k].g, curves[k].b);
    writePNG(path, PW, PH, img);
}

// ---------------- experiments ----------------

struct Combo {
    VkSampleCountFlagBits samples;
    int nSamples;
    bool supported;
    Renderer discardR, a2cR;
    bool ready = false;
};

static void runSweep(Combo& c, Extractor& ex, FILE* report,
                     std::vector<double>& lumDiscard, std::vector<double>& lumA2c,
                     std::vector<double>& flkDiscard, std::vector<double>& flkA2c,
                     const std::string& outDir) {
    std::vector<DrawItem> scene = buildSweepScene();
    std::vector<uint8_t> img, prevD, prevA;
    char name[256];
    for (int f = 0; f < FRAMES; f++) {
        Mat4 vp = sweepCamera(f);
        renderFrame(c.discardR, vp, scene, img);
        lumDiscard.push_back(roiLuminance(img));
        flkDiscard.push_back(f > 0 ? flickerVsPrev(img, prevD) : 0.0);
        prevD = img;
        if (f == 0 || f == FRAMES / 2 || f == FRAMES - 1) {
            snprintf(name, sizeof(name), "%s/frame_discard_%dx_f%03d.png", outDir.c_str(),
                     c.nSamples, f);
            writePNG(name, W, H, img);
        }
        renderFrame(c.a2cR, vp, scene, img);
        lumA2c.push_back(roiLuminance(img));
        flkA2c.push_back(f > 0 ? flickerVsPrev(img, prevA) : 0.0);
        prevA = img;
        if (f == 0 || f == FRAMES / 2 || f == FRAMES - 1) {
            snprintf(name, sizeof(name), "%s/frame_a2c_%dx_f%03d.png", outDir.c_str(),
                     c.nSamples, f);
            writePNG(name, W, H, img);
        }
    }
    auto stats = [](std::vector<double>& v, double& mean, double& meanD, double& maxD) {
        mean = 0; meanD = 0; maxD = 0;
        for (size_t i = 0; i < v.size(); i++) {
            mean += v[i];
            if (i > 0) {
                double d = std::fabs(v[i] - v[i - 1]);
                meanD += d;
                maxD = std::max(maxD, d);
            }
        }
        mean /= v.size();
        meanD /= (v.size() - 1);
    };
    double m, md, xd, ma, mda, xa;
    stats(lumDiscard, m, md, xd);
    stats(lumA2c, ma, mda, xa);
    double flkD = 0, flkA = 0;
    for (int f = 1; f < FRAMES; f++) { flkD += flkDiscard[f]; flkA += flkA2c[f]; }
    flkD /= (FRAMES - 1); flkA /= (FRAMES - 1);
    fprintf(report, "  ROI luminance: discard mean=%.4f fluct(mean|d|)=%.5f max|d|=%.5f flicker=%.5f\n",
            m, md, xd, flkD);
    fprintf(report, "  ROI luminance: a2c     mean=%.4f fluct(mean|d|)=%.5f max|d|=%.5f flicker=%.5f\n",
            ma, mda, xa, flkA);
    // per-sample display: pick partially-covered pixels on the mid frame (a2c render)
    Mat4 vp = sweepCamera(FRAMES / 2);
    renderFrame(c.a2cR, vp, scene, img);
    int picked[8][2];
    int nPick = 0;
    for (int y = 4; y < H - 4 && nPick < 8; y += 3)
        for (int x = 4; x < W - 4 && nPick < 8; x += 3) {
            float l = luminance(img, x, y);
            float ln = luminance(img, x + 2, y);
            if (std::fabs(l - ln) > 0.08f && l > 0.12f && l < 0.55f) { // edge straddler
                bool dup = false;
                for (int k = 0; k < nPick; k++)
                    if (abs(picked[k][0] - x) < 24 && abs(picked[k][1] - y) < 24) dup = true;
                if (!dup) { picked[nPick][0] = x; picked[nPick][1] = y; nPick++; }
            }
        }
    if (nPick == 0) { fprintf(report, "  (no partial-coverage pixels found)\n"); return; }
    std::vector<std::vector<Vec4>> samp;
    extractSamples(ex, c.a2cR, picked, nPick, samp);
    fprintf(report, "  Per-sample write mask, sweep frame %d, alpha-to-coverage %dx\n",
            FRAMES / 2, c.nSamples);
    fprintf(report, "  (sample counted as WRITTEN by cutout when it differs from dark backdrop)\n");
    for (int i = 0; i < nPick; i++) {
        fprintf(report, "  pixel (%3d,%3d): ", picked[i][0], picked[i][1]);
        for (int s = 0; s < c.nSamples; s++) {
            Vec4 v = samp[i][s];
            float l = 0.2126f * v.x + 0.7152f * v.y + 0.0722f * v.z;
            fprintf(report, "[%d:%s %.2f]", s, l > 0.15f ? "W" : ".", l);
        }
        fprintf(report, "\n");
    }
}

// ---------------- static-frame analysis ----------------

static Vec3 meanColor(const std::vector<uint8_t>& img, int cx, int cy, int rad) {
    double r = 0, g = 0, b = 0; int n = 0;
    for (int y = cy - rad; y <= cy + rad; y++)
        for (int x = cx - rad; x <= cx + rad; x++) {
            if (x < 0 || y < 0 || x >= W || y >= H) continue;
            size_t i = ((size_t)y * W + x) * 4;
            r += img[i]; g += img[i + 1]; b += img[i + 2]; n++;
        }
    return {(float)(r / n / 255), (float)(g / n / 255), (float)(b / n / 255)};
}

static void runStatic(Combo& c, Extractor& ex, FILE* report, const std::string& outDir) {
    std::vector<DrawItem> scene = buildStaticScene();
    Mat4 vp = staticCamera();
    // analytic edge line: local y=0 of the edge quad (world), projected to screen
    Mat4 model = mat4Mul(mat4Translate(v3(1.2f, 1.3f, 0)),
                         mat4Mul(mat4RotateZ(0.035f), mat4Scale(5, 5, 1)));
    auto toScreen = [&](Vec3 local, float& px, float& py) {
        Vec3 w = v3(
            model.m[0] * local.x + model.m[4] * local.y + model.m[8] * local.z + model.m[12],
            model.m[1] * local.x + model.m[5] * local.y + model.m[9] * local.z + model.m[13],
            model.m[2] * local.x + model.m[6] * local.y + model.m[10] * local.z + model.m[14]);
        projectPoint(vp, w, W, H, px, py);
    };
    float ax, ay, bx, by, fx, fy;
    toScreen(v3(-0.5f, 0, 0), ax, ay); // unit quad is +-0.5 in model space
    toScreen(v3(0.5f, 0, 0), bx, by);
    toScreen(v3(0, -0.1f, 0), fx, fy); // foreground side reference (local v<0.5 => alpha 1)
    float dx = bx - ax, dy = by - ay;
    float len = std::sqrt(dx * dx + dy * dy);
    float nx = -dy / len, ny = dx / len; // line normal
    float fgSign = (nx * (fx - ax) + ny * (fy - ay)) > 0 ? 1.0f : -1.0f;
    auto distToLine = [&](float px, float py) { return nx * (px - ax) + ny * (py - ay); };
    auto lineParam = [&](float px, float py) {
        return ((px - ax) * dx + (py - ay) * dy) / (len * len);
    };

    struct ModeRes { const char* name; double meanAbs, rms, maxD; int n; };
    ModeRes results[2];
    const char* modeNames[2] = {"discard", "a2c"};
    char name[256];
    for (int mode = 0; mode < 2; mode++) {
        Renderer& r = mode == 0 ? c.discardR : c.a2cR;
        std::vector<uint8_t> img;
        renderFrame(r, vp, scene, img);
        snprintf(name, sizeof(name), "%s/static_%s_%dx.png", outDir.c_str(), modeNames[mode],
                 c.nSamples);
        writePNG(name, W, H, img);
        // reference luminances far from the edge on both sides (mid-height of frame)
        double fgLum = 0, bgLum = 0; int nf = 0, nb = 0;
        for (int x = W / 4; x < 3 * W / 4; x++)
            for (int y = 0; y < H; y++) {
                float t = lineParam(x + 0.5f, y + 0.5f);
                if (t < 0.1f || t > 0.9f) continue; // stay inside the quad's edge segment
                float d = distToLine(x + 0.5f, y + 0.5f) * fgSign;
                if (d > 8 && d < 24) { fgLum += luminance(img, x, y); nf++; }
                if (d < -8 && d > -24) { bgLum += luminance(img, x, y); nb++; }
            }
        fgLum /= nf; bgLum /= nb;
        // deviation of resolved coverage from analytic half-plane coverage
        double sumAbs = 0, sumSq = 0, maxD = 0; int n = 0;
        for (int y = 0; y < H; y++)
            for (int x = 0; x < W; x++) {
                float d = distToLine(x + 0.5f, y + 0.5f);
                if (std::fabs(d) > 2.5f) continue;
                float t = lineParam(x + 0.5f, y + 0.5f);
                if (t < 0.03f || t > 0.97f) continue; // only where the quad edge exists
                int inside = 0;
                for (int sy = 0; sy < 16; sy++)
                    for (int sx = 0; sx < 16; sx++) {
                        float px = x + (sx + 0.5f) / 16.0f, py = y + (sy + 0.5f) / 16.0f;
                        if (distToLine(px, py) * fgSign > 0) inside++;
                    }
                double analytic = inside / 256.0;
                double resolved = (luminance(img, x, y) - bgLum) / (fgLum - bgLum);
                double dev = std::fabs(resolved - analytic);
                sumAbs += dev; sumSq += dev * dev; maxD = std::max(maxD, dev); n++;
            }
        results[mode] = {modeNames[mode], sumAbs / n, std::sqrt(sumSq / n), maxD, n};
        // ---- quarter-alpha block check ----
        float bcx, bcy, bgx, bgy;
        projectPoint(vp, v3(-3.0f, -1.6f, 1.0f), W, H, bcx, bcy);
        projectPoint(vp, v3(-3.0f, 0.2f, 1.0f), W, H, bgx, bgy);
        Vec3 bgRef = meanColor(img, (int)bgx, (int)bgy, 4);
        Vec3 measured = meanColor(img, (int)bcx, (int)bcy, 18);
        float orange[3] = {1.0f, 0.5f, 0.1f};
        fprintf(report, "  [%s %dx] quarter-alpha block: measured=(%.3f,%.3f,%.3f)\n",
                modeNames[mode], c.nSamples, measured.x, measured.y, measured.z);
        if (mode == 1) {
            fprintf(report, "      expected a2c resolve =(0.25*orange+0.75*bg)=(%.3f,%.3f,%.3f)",
                    0.25f * orange[0] + 0.75f * bgRef.x,
                    0.25f * orange[1] + 0.75f * bgRef.y,
                    0.25f * orange[2] + 0.75f * bgRef.z);
            float err = std::fabs(measured.x - (0.25f * orange[0] + 0.75f * bgRef.x));
            fprintf(report, "  err=%.3f %s\n", err, err < 0.06f ? "PASS" : "FAIL");
        } else {
            float err = std::fabs(measured.x - bgRef.x);
            fprintf(report, "      expected discard=>bg=(%.3f,%.3f,%.3f)  err=%.3f %s\n",
                    bgRef.x, bgRef.y, bgRef.z, err, err < 0.06f ? "PASS" : "FAIL");
        }
        // ---- opaque occluder check: covered samples must not leak through ----
        float ox, oy;
        projectPoint(vp, v3(-1.9f, -1.6f, 2.0f), W, H, ox, oy);
        int opix[4][2] = {{(int)ox - 10, (int)oy - 10}, {(int)ox + 10, (int)oy - 10},
                          {(int)ox - 10, (int)oy + 10}, {(int)ox + 10, (int)oy + 10}};
        std::vector<std::vector<Vec4>> samp;
        extractSamples(ex, r, opix, 4, samp);
        int bad = 0, total = 0;
        for (int i = 0; i < 4; i++)
            for (int s = 0; s < c.nSamples; s++) {
                Vec4 v = samp[i][s];
                total++;
                if (std::fabs(v.x - 0.75f) > 0.08f || std::fabs(v.y - 0.12f) > 0.08f) bad++;
            }
        fprintf(report, "      occluder per-sample: %d/%d samples hold occluder color %s\n",
                total - bad, total, bad == 0 ? "PASS (no leak-through)" : "FAIL (leak!)");
        // ---- per-sample dump along the analytic edge ----
        int epix[8][2];
        for (int i = 0; i < 8; i++) {
            float t = 0.2f + 0.6f * i / 7.0f;
            float lx = ax + dx * t, ly = ay + dy * t;
            float off = 0.0f; // land on the edge: partial coverage
            epix[i][0] = (int)(lx + nx * off);
            epix[i][1] = (int)(ly + ny * off);
        }
        extractSamples(ex, r, epix, 8, samp);
        fprintf(report, "      edge pixels per-sample (W=foreground/magenta written):\n");
        for (int i = 0; i < 8; i++) {
            fprintf(report, "      pixel (%3d,%3d): ", epix[i][0], epix[i][1]);
            for (int s = 0; s < c.nSamples; s++) {
                Vec4 v = samp[i][s];
                bool w = v.x > 0.5f && v.z > 0.3f; // magenta foreground
                fprintf(report, "[%d:%s]", s, w ? "W" : ".");
            }
            fprintf(report, "\n");
        }
    }
    fprintf(report, "  Edge deviation vs analytic coverage (%d band pixels):\n", results[0].n);
    for (int m = 0; m < 2; m++)
        fprintf(report, "      %-8s meanAbs=%.4f  RMS=%.4f  max=%.4f\n",
                results[m].name, results[m].meanAbs, results[m].rms, results[m].maxD);
}

int main(int argc, char** argv) {
    std::string outDir = argc > 1 ? argv[1] : "artifacts";
    std::string cmd = "mkdir -p " + outDir;
    system(cmd.c_str());
    FILE* report = fopen((outDir + "/report.txt").c_str(), "w");
    auto log = [&](const char* fmt, ...) {
        va_list ap;
        va_start(ap, fmt);
        vfprintf(stderr, fmt, ap);
        va_end(ap);
        va_start(ap, fmt);
        vfprintf(report, fmt, ap);
        va_end(ap);
    };
    vkCtxInit(g_ctx);
    log("Device: %s (Vulkan %u.%u.%u)\n", g_ctx.props.deviceName,
        VK_VERSION_MAJOR(g_ctx.props.apiVersion), VK_VERSION_MINOR(g_ctx.props.apiVersion),
        VK_VERSION_PATCH(g_ctx.props.apiVersion));
    VkSampleCountFlags supported = g_ctx.props.limits.framebufferColorSampleCounts &
                                   g_ctx.props.limits.sampledImageColorSampleCounts &
                                   g_ctx.props.limits.framebufferDepthSampleCounts;
    log("Sample counts supported (color+sampled+depth): 0x%x\n\n", supported);

    VkShaderModule vert = loadShader(g_ctx, "shaders/cutout.vert.spv");
    VkShaderModule frag = loadShader(g_ctx, "shaders/cutout.frag.spv");
    VkShaderModule comp = loadShader(g_ctx, "shaders/extract.comp.spv");
    createGlobalResources();
    Extractor ex;
    createExtractor(ex, comp);

    struct { VkSampleCountFlagBits bit; int n; } tiers[3] = {
        {VK_SAMPLE_COUNT_1_BIT, 1}, {VK_SAMPLE_COUNT_4_BIT, 4}, {VK_SAMPLE_COUNT_8_BIT, 8}};
    std::vector<Curve> curves, flkCurves;
    uint8_t palette[6][3] = {{220, 60, 60}, {240, 150, 40}, {250, 210, 60},
                             {40, 90, 220}, {60, 170, 90}, {150, 70, 200}};
    int curveIdx = 0;
    std::vector<std::string> legend;
    for (auto& t : tiers) {
        Combo c;
        c.samples = t.bit;
        c.nSamples = t.n;
        c.supported = (supported & t.bit) != 0;
        log("=== Sample count %dx: %s ===\n", t.n,
            c.supported ? "SUPPORTED" : "NOT SUPPORTED by device - skipped");
        if (!c.supported) continue;
        createRenderer(c.discardR, t.bit, false, vert, frag);
        createRenderer(c.a2cR, t.bit, true, vert, frag);
        std::vector<double> lumD, lumA, flkD, flkA;
        log("-- Sweep (%d frames) --\n", FRAMES);
        runSweep(c, ex, report, lumD, lumA, flkD, flkA, outDir);
        {
            std::string csvPath = outDir + "/luminance_" + std::to_string(t.n) + "x.csv";
            FILE* csv = fopen(csvPath.c_str(), "w");
            fprintf(csv, "frame,roi_lum_discard_%dx,roi_lum_a2c_%dx,flicker_discard_%dx,flicker_a2c_%dx\n",
                    t.n, t.n, t.n, t.n);
            for (int f = 0; f < FRAMES; f++)
                fprintf(csv, "%d,%.6f,%.6f,%.6f,%.6f\n", f, lumD[f], lumA[f], flkD[f], flkA[f]);
            fclose(csv);
        }
        curves.push_back({lumD, palette[curveIdx % 6][0], palette[curveIdx % 6][1],
                          palette[curveIdx % 6][2]});
        legend.push_back("discard " + std::to_string(t.n) + "x");
        curveIdx++;
        curves.push_back({lumA, palette[curveIdx % 6][0], palette[curveIdx % 6][1],
                          palette[curveIdx % 6][2]});
        legend.push_back("a2c " + std::to_string(t.n) + "x");
        curveIdx++;
        flkCurves.push_back({flkD, palette[(curveIdx - 2) % 6][0], palette[(curveIdx - 2) % 6][1],
                             palette[(curveIdx - 2) % 6][2]});
        flkCurves.push_back({flkA, palette[(curveIdx - 1) % 6][0], palette[(curveIdx - 1) % 6][1],
                             palette[(curveIdx - 1) % 6][2]});
        log("-- Static frame analysis --\n");
        runStatic(c, ex, report, outDir);
        log("\n");
        destroyRenderer(c.discardR);
        destroyRenderer(c.a2cR);
    }
    if (!curves.empty()) {
        plotCurves(outDir + "/luminance_plot.png", curves, FRAMES);
        plotCurves(outDir + "/flicker_plot.png", flkCurves, FRAMES);
        log("Plot legend (left to right, both plots): ");
        for (size_t i = 0; i < legend.size(); i++) log("%s%s", legend[i].c_str(),
                                                       i + 1 < legend.size() ? ", " : "\n");
    }
    log("\nDone. Artifacts in %s/\n", outDir.c_str());
    fclose(report);
    return 0;
}
