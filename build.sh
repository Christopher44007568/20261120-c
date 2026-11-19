#!/bin/bash
set -e
cd "$(dirname "$0")"
GLSLANG=tools/sysroot/usr/bin/glslangValidator
VULKAN_INC=tools/sysroot/usr/include
for s in cutout.vert cutout.frag extract.comp; do
    $GLSLANG -V "shaders/$s" -o "shaders/$s.spv"
done
g++ -O2 -std=c++17 -Wall -I"$VULKAN_INC" src/main.cpp -o msaa_cutout_lab \
    /usr/lib/x86_64-linux-gnu/libvulkan.so.1
echo "build ok"
