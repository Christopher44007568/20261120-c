#include <vulkan/vulkan.h>
#include <cstdio>
#include <vector>
int main(){
    VkInstance inst;
    VkApplicationInfo ai{VK_STRUCTURE_TYPE_APPLICATION_INFO};
    ai.apiVersion = VK_API_VERSION_1_1;
    VkInstanceCreateInfo ici{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};
    ici.pApplicationInfo = &ai;
    if(vkCreateInstance(&ici,nullptr,&inst)!=VK_SUCCESS){printf("no instance\n");return 1;}
    uint32_t n=0; vkEnumeratePhysicalDevices(inst,&n,nullptr);
    std::vector<VkPhysicalDevice> devs(n);
    vkEnumeratePhysicalDevices(inst,&n,devs.data());
    for(auto d:devs){
        VkPhysicalDeviceProperties p; vkGetPhysicalDeviceProperties(d,&p);
        printf("device: %s (type %d) api %u.%u.%u\n",p.deviceName,(int)p.deviceType,
            VK_VERSION_MAJOR(p.apiVersion),VK_VERSION_MINOR(p.apiVersion),VK_VERSION_PATCH(p.apiVersion));
        printf("  framebufferColorSampleCounts=0x%x sampledImageColorSampleCounts=0x%x\n",
            p.limits.framebufferColorSampleCounts,p.limits.sampledImageColorSampleCounts);
        printf("  framebufferDepthSampleCounts=0x%x standardSampleLocations=%d\n",
            p.limits.framebufferDepthSampleCounts, p.limits.standardSampleLocations);
    }
    return 0;
}
