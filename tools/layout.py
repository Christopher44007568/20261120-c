"""std140/std430 layout computation and validation against SPIR-V
Offset / ArrayStride / MatrixStride decorations."""



def align_up(alignment, value):
    return (value + alignment - 1) // alignment * alignment


class LayoutError(Exception):
    pass


class LayoutEngine:
    """Computes member offsets / array strides for a parsed module."""

    def __init__(self, mod, std):
        if std not in ("std140", "std430"):
            raise ValueError(std)
        self.mod = mod
        self.std = std
        self._cache = {}

    def _round(self, alignment):
        if self.std == "std140":
            return align_up(16, alignment)
        return alignment

    def type_layout(self, type_id):
        """Return (size, alignment) for a type id."""
        if type_id in self._cache:
            return self._cache[type_id]
        result = self._compute(type_id)
        self._cache[type_id] = result
        return result

    def _compute(self, type_id):
        mod = self.mod
        t = mod.types[type_id]
        kind = t["kind"]
        if kind == "bool":
            return 4, 4
        if kind in ("int", "float"):
            width = t["width"] // 8
            return width, width
        if kind == "vector":
            comp_size, _ = self.type_layout(t["component"])
            count = t["count"]
            align = comp_size * 2 if count == 2 else comp_size * 4
            return comp_size * count, align
        if kind == "matrix":
            col_size, col_align = self.type_layout(t["column"])
            stride = align_up(self._round(col_align), col_size)
            return stride * t["count"], self._round(col_align)
        if kind in ("array", "runtime_array"):
            elem_size, elem_align = self.type_layout(t["element"])
            align = self._round(elem_align)
            stride = align_up(align, elem_size)
            if kind == "runtime_array":
                return stride, align
            length = mod.constants.get(t["length_id"])
            if length is None:
                raise LayoutError("array length not a constant")
            return stride * length, align
        if kind == "struct":
            offset = 0
            max_align = 1
            for member in t["members"]:
                size, align = self.type_layout(member)
                offset = align_up(align, offset)
                offset += size
                max_align = max(max_align, align)
            struct_align = self._round(max_align)
            return align_up(struct_align, offset), struct_align
        raise LayoutError("no layout rule for kind %s" % kind)

    def struct_members(self, struct_id):
        """Return list of (member_index, type_id, offset) for a struct."""
        t = self.mod.types[struct_id]
        offset = 0
        out = []
        for index, member in enumerate(t["members"]):
            size, align = self.type_layout(member)
            offset = align_up(align, offset)
            out.append((index, member, offset))
            offset += size
        return out

    def array_stride(self, array_type_id):
        elem_size, elem_align = self.type_layout(
            self.mod.types[array_type_id]["element"])
        return align_up(self._round(elem_align), elem_size)

    def matrix_stride(self, matrix_type_id):
        col_size, col_align = self.type_layout(
            self.mod.types[matrix_type_id]["column"])
        return align_up(self._round(col_align), col_size)


def validate_block(mod, struct_id, std):
    """Compare computed layout with decorations. Returns list of issues."""
    engine = LayoutEngine(mod, std)
    issues = []
    member_decs = mod.member_decorations.get(struct_id, {})
    for index, member, offset in engine.struct_members(struct_id):
        _, member_align = engine.type_layout(member)
        declared = member_decs.get(index, {}).get("Offset")
        if declared is None:
            issues.append("member %d: missing Offset decoration" % index)
        elif declared != offset:
            # An explicit layout(offset=...) may only add padding.
            if declared > offset and declared % member_align == 0:
                continue
            issues.append("member %d: offset %d != expected %d"
                          % (index, declared, offset))
        if mod.types[member]["kind"] == "matrix":
            stride = member_decs.get(index, {}).get("MatrixStride")
            expected = engine.matrix_stride(member)
            if stride is not None and stride != expected:
                issues.append("member %d: matrix stride %d != expected %d"
                              % (index, stride, expected))
        _check_strides(mod, engine, member, index, issues)
    return issues


def _check_strides(mod, engine, type_id, member_index, issues):
    t = mod.types[type_id]
    if t["kind"] in ("array", "runtime_array"):
        declared = mod.decorations.get(type_id, {}).get("ArrayStride")
        expected = engine.array_stride(type_id)
        if declared != expected:
            issues.append("member %d: array stride %s != expected %d"
                          % (member_index, declared, expected))
        _check_strides(mod, engine, t["element"], member_index, issues)
