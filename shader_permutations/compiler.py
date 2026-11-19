"""A small, deterministic shader compiler used for compile-time accounting."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import blake2b

from .model import Variant


class CompilerError(ValueError):
    """Raised when a generated shader program is malformed."""


@dataclass(frozen=True, slots=True)
class CompiledProgram:
    instructions: tuple[tuple[str, tuple[float, ...]], ...]
    digest: str

    @property
    def instruction_count(self) -> int:
        return len(self.instructions)


_KEYWORD_COEFFICIENTS = {
    "PBR": (0.72, 0.69, 0.66),
    "NORMAL_MAP": (0.11, 0.08, 0.04),
    "EMISSIVE": (0.91, 0.48, 0.16),
    "TRANSMISSION": (0.24, 0.61, 0.84),
    "CLEARCOAT": (0.88, 0.90, 0.94),
    "ANISOTROPY": (0.36, 0.52, 0.73),
    "SUBSURFACE": (0.77, 0.38, 0.31),
    "ALPHA_MASK": (0.63, 0.79, 0.42),
    "SHADOW_CASCADE": (0.18, 0.22, 0.29),
    "FOG": (0.57, 0.64, 0.71),
}

_PATH_COEFFICIENTS = {
    "FORWARD": (0.31, 0.43, 0.59),
    "FORWARD_PLUS": (0.41, 0.37, 0.53),
    "DEFERRED": (0.27, 0.49, 0.67),
    "RAYTRACE": (0.53, 0.29, 0.47),
}


def _vec3_block(a: tuple[float, float, float], b: tuple[float, float, float]) -> list[str]:
    return [
        f"PUSH_VEC3 {a[0]:.6f} {a[1]:.6f} {a[2]:.6f}",
        f"PUSH_VEC3 {b[0]:.6f} {b[1]:.6f} {b[2]:.6f}",
        "MUL",
        "ADD",
    ]


def generate_program_source(variant: Variant) -> str:
    """Specialize the shader stack program for a keyword combination."""

    resolved = sorted(variant.resolved_keywords)
    lines = [
        "SHADER 1",
        f"PATH {variant.path}",
        f"KEYWORDS {' '.join(sorted(variant.keywords)) or 'NONE'}",
        f"RESOLVED {' '.join(resolved)}",
        "CODE",
        "PUSH_VEC3 0.040000 0.050000 0.060000",
        "PUSH_VEC3 0.800000 0.720000 0.610000",
        "MUL",
        "PUSH_VEC3 0.350000 0.370000 0.400000",
        "PUSH_VEC3 0.120000 0.160000 0.200000",
        "DOT",
        "PUSH 0.650000",
        "MUL",
        "MUL",
        "PUSH_VEC3 1.000000 0.900000 0.750000",
        "MUL",
        "PUSH_VEC3 0.040000 0.050000 0.060000",
        "ADD",
    ]
    for keyword in resolved:
        coefficient = _KEYWORD_COEFFICIENTS[keyword]
        lines.extend(_vec3_block(coefficient, (0.85, 0.80, 0.75)))
        lines.extend(
            [
                f"PUSH {0.05 + coefficient[0] / 20.0:.6f}",
                "PUSH_VEC3 0.060000 0.070000 0.080000",
                "MUL",
                "ADD",
            ]
        )
    path_coefficient = _PATH_COEFFICIENTS[variant.path]
    lines.extend(_vec3_block(path_coefficient, (0.92, 0.94, 0.96)))
    lines.extend(
        [
            "PUSH_VEC3 0.010000 0.015000 0.020000",
            "ADD",
            "SATURATE",
            "OUTPUT",
            "END",
        ]
    )
    return "\n".join(lines) + "\n"


_OPCODES = {
    "PUSH",
    "PUSH_VEC3",
    "ADD",
    "MUL",
    "DOT",
    "NORMALIZE",
    "SATURATE",
    "OUTPUT",
}


class ShaderCompiler:
    """Parse and lower the shader stack language into typed instructions."""

    def compile(self, variant: Variant) -> CompiledProgram:
        return self.compile_source(generate_program_source(variant))

    def compile_source(self, source: str) -> CompiledProgram:
        stack: list[str] = []
        instructions: list[tuple[str, tuple[float, ...]]] = []
        in_code = False
        ended = False

        for line_number, raw_line in enumerate(source.splitlines(), start=1):
            line = raw_line.split("#", 1)[0].strip()
            if not line:
                continue
            tokens = line.split()
            opcode, operands = tokens[0], tokens[1:]
            if opcode == "SHADER":
                if operands != ["1"]:
                    raise CompilerError(f"line {line_number}: unsupported version")
                continue
            if opcode in {"PATH", "KEYWORDS", "RESOLVED"}:
                continue
            if opcode == "CODE":
                in_code = True
                continue
            if opcode == "END":
                ended = True
                break
            if not in_code:
                raise CompilerError(f"line {line_number}: instruction before CODE")
            if opcode not in _OPCODES:
                raise CompilerError(f"line {line_number}: unknown opcode {opcode}")

            values = self._parse_operands(opcode, operands, line_number)
            instructions.append((opcode, values))
            if opcode == "PUSH":
                stack.append("scalar")
            elif opcode == "PUSH_VEC3":
                stack.append("vec3")
            elif opcode in {"ADD", "MUL"}:
                left, right = self._pop2(stack, opcode, line_number)
                if opcode == "ADD" and left != right:
                    raise CompilerError(f"line {line_number}: ADD shape mismatch")
                stack.append("vec3" if "vec3" in {left, right} else "scalar")
            elif opcode == "DOT":
                left, right = self._pop2(stack, opcode, line_number)
                if left != "vec3" or right != "vec3":
                    raise CompilerError(f"line {line_number}: DOT requires vec3")
                stack.append("scalar")
            elif opcode == "NORMALIZE":
                if not stack or stack.pop() != "vec3":
                    raise CompilerError(f"line {line_number}: NORMALIZE requires vec3")
                stack.append("vec3")
            elif opcode == "SATURATE":
                if not stack:
                    raise CompilerError(f"line {line_number}: SATURATE stack underflow")
                if stack[-1] not in {"scalar", "vec3"}:
                    raise CompilerError(f"line {line_number}: bad SATURATE input")
            elif opcode == "OUTPUT":
                if operands or not stack or stack[-1] != "vec3":
                    raise CompilerError(f"line {line_number}: OUTPUT requires one vec3")
                stack.pop()

        if not ended:
            raise CompilerError("missing END")
        if stack:
            raise CompilerError("unconsumed values remain on the stack")
        if not instructions or instructions[-1][0] != "OUTPUT":
            raise CompilerError("program has no OUTPUT")
        digest = blake2b(source.encode("utf-8"), digest_size=16).hexdigest()
        return CompiledProgram(tuple(instructions), digest)

    @staticmethod
    def _parse_operands(
        opcode: str, operands: list[str], line_number: int
    ) -> tuple[float, ...]:
        if opcode == "PUSH" and len(operands) == 1:
            return (ShaderCompiler._float(operands[0], line_number),)
        if opcode == "PUSH_VEC3" and len(operands) == 3:
            return tuple(
                ShaderCompiler._float(value, line_number) for value in operands
            )
        if opcode in _OPCODES and not operands:
            return ()
        raise CompilerError(f"line {line_number}: bad operands for {opcode}")

    @staticmethod
    def _float(value: str, line_number: int) -> float:
        try:
            return float(value)
        except ValueError as error:
            raise CompilerError(f"line {line_number}: invalid number {value}") from error

    @staticmethod
    def _pop2(
        stack: list[str], opcode: str, line_number: int
    ) -> tuple[str, str]:
        if len(stack) < 2:
            raise CompilerError(f"line {line_number}: {opcode} stack underflow")
        return stack.pop(), stack.pop()
