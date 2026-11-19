"""Minimal pure-Python SPIR-V binary parser for shader reflection."""
import struct

MAGIC = 0x07230203

OP_NAME = 5
OP_MEMBER_NAME = 6
OP_ENTRY_POINT = 15
OP_TYPE_VOID = 19
OP_TYPE_BOOL = 20
OP_TYPE_INT = 21
OP_TYPE_FLOAT = 22
OP_TYPE_VECTOR = 23
OP_TYPE_MATRIX = 24
OP_TYPE_IMAGE = 25
OP_TYPE_SAMPLER = 26
OP_TYPE_SAMPLED_IMAGE = 27
OP_TYPE_ARRAY = 28
OP_TYPE_RUNTIME_ARRAY = 29
OP_TYPE_STRUCT = 30
OP_TYPE_POINTER = 32
OP_CONSTANT = 43
OP_VARIABLE = 59
OP_DECORATE = 71
OP_MEMBER_DECORATE = 72

DECORATION_NAMES = {
    2: "Block", 3: "BufferBlock", 4: "RowMajor", 5: "ColMajor",
    6: "ArrayStride", 7: "MatrixStride", 11: "BuiltIn", 14: "Flat",
    24: "NonWritable", 25: "NonReadable", 30: "Location", 31: "Component",
    33: "Binding", 34: "DescriptorSet", 35: "Offset",
}

STORAGE_CLASS = {
    0: "UniformConstant", 1: "Input", 2: "Uniform", 3: "Output",
    5: "Private", 6: "Function", 9: "PushConstant", 12: "StorageBuffer",
}

EXECUTION_MODEL = {
    0: "vertex", 1: "tessellation_control", 2: "tessellation_evaluation",
    3: "geometry", 4: "fragment", 5: "compute",
}

IMAGE_DIM = {0: "1D", 1: "2D", 2: "3D", 3: "Cube", 4: "Rect", 5: "Buffer",
             6: "SubpassData"}

TYPE_OPCODE_NAMES = {
    OP_TYPE_VOID: "void", OP_TYPE_BOOL: "bool", OP_TYPE_INT: "int",
    OP_TYPE_FLOAT: "float", OP_TYPE_VECTOR: "vector", OP_TYPE_MATRIX: "matrix",
    OP_TYPE_IMAGE: "image", OP_TYPE_SAMPLER: "sampler",
    OP_TYPE_SAMPLED_IMAGE: "sampled_image", OP_TYPE_ARRAY: "array",
    OP_TYPE_RUNTIME_ARRAY: "runtime_array", OP_TYPE_STRUCT: "struct",
    OP_TYPE_POINTER: "pointer",
}


def _read_cstring(words, start):
    data = b"".join(struct.pack("<I", w) for w in words[start:])
    end = data.find(b"\x00")
    return data[:end].decode("utf-8", "replace")


class Module:
    def __init__(self):
        self.version = None
        self.types = {}
        self.constants = {}
        self.names = {}
        self.member_names = {}
        self.decorations = {}
        self.member_decorations = {}
        self.variables = []
        self.entry_points = []


def parse(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    words = struct.unpack("<%dI" % (len(raw) // 4), raw)
    if words[0] != MAGIC:
        raise ValueError("%s: not a SPIR-V module" % path)
    mod = Module()
    mod.version = "%d.%d" % ((words[1] >> 16) & 0xFF, (words[1] >> 8) & 0xFF)
    pos = 5
    while pos < len(words):
        word_count = words[pos] >> 16
        opcode = words[pos] & 0xFFFF
        ops = words[pos + 1: pos + word_count]
        _handle(mod, opcode, ops)
        pos += word_count
    return mod


def _handle(mod, opcode, ops):
    if opcode == OP_NAME:
        mod.names[ops[0]] = _read_cstring(ops, 1)
    elif opcode == OP_MEMBER_NAME:
        mod.member_names.setdefault(ops[0], {})[ops[1]] = _read_cstring(ops, 2)
    elif opcode == OP_DECORATE:
        name = DECORATION_NAMES.get(ops[1])
        if name:
            value = ops[2] if len(ops) > 2 else True
            mod.decorations.setdefault(ops[0], {})[name] = value
    elif opcode == OP_MEMBER_DECORATE:
        name = DECORATION_NAMES.get(ops[2])
        if name:
            value = ops[3] if len(ops) > 3 else True
            mod.member_decorations.setdefault(ops[0], {}).setdefault(
                ops[1], {})[name] = value
    elif opcode == OP_ENTRY_POINT:
        name = _read_cstring(ops, 2)
        name_words = len(name) // 4 + 1
        mod.entry_points.append({
            "model": EXECUTION_MODEL.get(ops[0], str(ops[0])),
            "id": ops[1],
            "name": name,
            "interfaces": list(ops[2 + name_words:]),
        })
    elif opcode in TYPE_OPCODE_NAMES:
        _handle_type(mod, opcode, ops)
    elif opcode == OP_CONSTANT:
        mod.constants[ops[1]] = ops[2] if len(ops) > 2 else 0
    elif opcode == OP_VARIABLE:
        mod.variables.append({
            "id": ops[1],
            "type_id": ops[0],
            "storage": STORAGE_CLASS.get(ops[2], str(ops[2])),
        })


def _handle_type(mod, opcode, ops):
    kind = TYPE_OPCODE_NAMES[opcode]
    result_id = ops[0]
    t = {"kind": kind}
    if kind == "int":
        t.update(width=ops[1], signed=bool(ops[2]))
    elif kind == "float":
        t.update(width=ops[1])
    elif kind == "vector":
        t.update(component=ops[1], count=ops[2])
    elif kind == "matrix":
        t.update(column=ops[1], count=ops[2])
    elif kind == "image":
        t.update(sampled_type=ops[1], dim=IMAGE_DIM.get(ops[2], str(ops[2])),
                 depth=ops[3], arrayed=ops[4], ms=ops[5], sampled=ops[6])
    elif kind == "sampled_image":
        t.update(image=ops[1])
    elif kind == "array":
        t.update(element=ops[1], length_id=ops[2])
    elif kind == "runtime_array":
        t.update(element=ops[1])
    elif kind == "struct":
        t.update(members=list(ops[1:]))
    elif kind == "pointer":
        t.update(storage=STORAGE_CLASS.get(ops[1], str(ops[1])), pointee=ops[2])
    mod.types[result_id] = t
