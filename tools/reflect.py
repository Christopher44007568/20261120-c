"""Build a reflection dict (descriptors, push constants, I/O) from a
parsed SPIR-V module."""
from layout import LayoutEngine


def type_name(mod, type_id):
    t = mod.types[type_id]
    kind = t["kind"]
    if kind == "float":
        return "float" if t["width"] == 32 else "double"
    if kind == "int":
        return ("int" if t["signed"] else "uint")
    if kind == "bool":
        return "bool"
    if kind == "vector":
        base = type_name(mod, t["component"])
        prefix = {"float": "vec", "double": "dvec", "int": "ivec",
                  "uint": "uvec", "bool": "bvec"}.get(base, base)
        return "%s%d" % (prefix, t["count"])
    if kind == "matrix":
        return "mat%d" % t["count"]
    if kind == "array":
        length = mod.constants.get(t["length_id"], "?")
        return "%s[%s]" % (type_name(mod, t["element"]), length)
    if kind == "runtime_array":
        return "%s[]" % type_name(mod, t["element"])
    if kind == "struct":
        return mod.names.get(type_id, "struct#%d" % type_id)
    if kind == "image":
        return "texture%s" % t["dim"].replace("2D", "2D").replace("Cube", "Cube")
    if kind == "sampler":
        return "sampler"
    if kind == "sampled_image":
        image = mod.types[t["image"]]
        return "sampler%s" % image["dim"]
    return kind


def _pointee(mod, var):
    pointer = mod.types[var["type_id"]]
    return pointer["pointee"]


def _block_members(mod, struct_id, std):
    engine = LayoutEngine(mod, std)
    names = mod.member_names.get(struct_id, {})
    out = []
    for index, member, offset in engine.struct_members(struct_id):
        entry = {
            "name": names.get(index, "member%d" % index),
            "type": type_name(mod, member),
            "offset": offset,
        }
        t = mod.types[member]
        if t["kind"] in ("array", "runtime_array"):
            entry["arrayStride"] = engine.array_stride(member)
        if t["kind"] == "matrix":
            entry["matrixStride"] = engine.matrix_stride(member)
        out.append(entry)
    return out


def _descriptor_type(mod, var, pointee):
    storage = var["storage"]
    if storage == "Uniform":
        struct_decs = mod.decorations.get(pointee, {})
        if struct_decs.get("BufferBlock"):
            return "storage_buffer"
        return "uniform_buffer"
    if storage == "StorageBuffer":
        return "storage_buffer"
    if storage == "PushConstant":
        return "push_constant"
    if storage == "UniformConstant":
        t = mod.types[pointee]
        if t["kind"] == "sampled_image":
            return "combined_image_sampler"
        if t["kind"] == "sampler":
            return "sampler"
        if t["kind"] == "image":
            return "sampled_image" if t["sampled"] == 1 else "storage_image"
    return "unknown"


def reflect(mod, module_name):
    stage = mod.entry_points[0]["model"] if mod.entry_points else "unknown"
    result = {
        "module": module_name,
        "stage": stage,
        "spirvVersion": mod.version,
        "descriptors": [],
        "pushConstants": [],
        "inputs": [],
        "outputs": [],
    }
    for var in mod.variables:
        pointee = _pointee(mod, var)
        decs = mod.decorations.get(var["id"], {})
        name = mod.names.get(var["id"], "var#%d" % var["id"])
        storage = var["storage"]
        if storage in ("Uniform", "StorageBuffer", "UniformConstant"):
            dtype = _descriptor_type(mod, var, pointee)
            entry = {
                "name": name,
                "set": decs.get("DescriptorSet", 0),
                "binding": decs.get("Binding", 0),
                "type": dtype,
                "stage": stage,
            }
            if dtype in ("uniform_buffer", "storage_buffer"):
                std = "std140" if dtype == "uniform_buffer" else "std430"
                engine = LayoutEngine(mod, std)
                size, _ = engine.type_layout(pointee)
                entry["blockType"] = mod.names.get(pointee, "")
                entry["size"] = size
                entry["layout"] = std
                entry["members"] = _block_members(mod, pointee, std)
                if mod.types[pointee]["members"]:
                    last = mod.types[pointee]["members"][-1]
                    if mod.types[last]["kind"] == "runtime_array":
                        entry["size"] = None  # unsized SSBO
            elif dtype in ("combined_image_sampler", "sampled_image",
                           "storage_image"):
                image_id = pointee
                if mod.types[image_id]["kind"] == "sampled_image":
                    image_id = mod.types[image_id]["image"]
                image = mod.types[image_id]
                entry["dim"] = image["dim"]
                entry["glslType"] = type_name(mod, pointee)
            result["descriptors"].append(entry)
        elif storage == "PushConstant":
            engine = LayoutEngine(mod, "std140")
            size, _ = engine.type_layout(pointee)
            result["pushConstants"].append({
                "name": name,
                "blockType": mod.names.get(pointee, ""),
                "size": size,
                "stage": stage,
                "members": _block_members(mod, pointee, "std140"),
            })
        elif storage in ("Input", "Output"):
            if "Location" not in decs:
                continue  # built-ins (gl_Position etc.)
            slot = "inputs" if storage == "Input" else "outputs"
            result[slot].append({
                "name": name,
                "location": decs["Location"],
                "type": type_name(mod, pointee),
                "flat": bool(decs.get("Flat")),
            })
    result["descriptors"].sort(key=lambda d: (d["set"], d["binding"]))
    result["inputs"].sort(key=lambda d: d["location"])
    result["outputs"].sort(key=lambda d: d["location"])
    return result
