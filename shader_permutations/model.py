"""Shader keyword domain, material profiles, and permutation generation."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

KEYWORDS: tuple[str, ...] = (
    "PBR",
    "NORMAL_MAP",
    "EMISSIVE",
    "TRANSMISSION",
    "CLEARCOAT",
    "ANISOTROPY",
    "SUBSURFACE",
    "ALPHA_MASK",
    "SHADOW_CASCADE",
    "FOG",
)

LIGHT_PATHS: tuple[str, ...] = (
    "FORWARD",
    "FORWARD_PLUS",
    "DEFERRED",
    "RAYTRACE",
)

IMPLIED_BY: dict[str, tuple[str, ...]] = {
    "PBR": (),
    "NORMAL_MAP": ("PBR",),
    "EMISSIVE": ("PBR",),
    "TRANSMISSION": ("PBR",),
    "CLEARCOAT": ("PBR",),
    "ANISOTROPY": ("PBR", "NORMAL_MAP"),
    "SUBSURFACE": ("PBR",),
    "ALPHA_MASK": (),
    "SHADOW_CASCADE": ("PBR",),
    "FOG": (),
}

PBR_ONLY_KEYWORDS = frozenset(
    {
        "NORMAL_MAP",
        "EMISSIVE",
        "TRANSMISSION",
        "CLEARCOAT",
        "ANISOTROPY",
        "SUBSURFACE",
        "SHADOW_CASCADE",
    }
)


@dataclass(frozen=True, slots=True)
class Variant:
    """A canonical, minimal keyword set for one lighting path."""

    keywords: frozenset[str]
    path: str

    @property
    def resolved_keywords(self) -> frozenset[str]:
        return resolve_dependencies(self.keywords)

    @property
    def cache_key(self) -> tuple[str, tuple[str, ...]]:
        return self.path, tuple(sorted(self.keywords))

    @property
    def resolved_cache_key(self) -> tuple[str, tuple[str, ...]]:
        return self.path, tuple(sorted(self.resolved_keywords))

    @property
    def label(self) -> str:
        keywords = "+".join(sorted(self.keywords)) or "BASE"
        return f"{self.path}:{keywords}"


@dataclass(frozen=True, slots=True)
class MaterialProfile:
    """Material capabilities and the keyword options it can specialize."""

    name: str
    required: frozenset[str]
    optional: tuple[str, ...]
    paths: tuple[str, ...]


SCENE_MATERIALS: tuple[MaterialProfile, ...] = (
    MaterialProfile(
        "painted_metal",
        frozenset({"PBR", "CLEARCOAT"}),
        ("NORMAL_MAP", "FOG"),
        ("FORWARD_PLUS", "DEFERRED"),
    ),
    MaterialProfile(
        "frosted_glass",
        frozenset({"PBR", "TRANSMISSION"}),
        ("NORMAL_MAP", "FOG"),
        ("FORWARD", "FORWARD_PLUS"),
    ),
    MaterialProfile(
        "skin",
        frozenset({"PBR", "SUBSURFACE"}),
        ("NORMAL_MAP", "EMISSIVE"),
        ("FORWARD",),
    ),
    MaterialProfile(
        "foliage",
        frozenset({"PBR", "ALPHA_MASK"}),
        ("NORMAL_MAP", "FOG", "SHADOW_CASCADE"),
        ("FORWARD", "FORWARD_PLUS"),
    ),
    MaterialProfile(
        "emissive_panel",
        frozenset({"PBR", "EMISSIVE"}),
        ("FOG",),
        ("FORWARD", "FORWARD_PLUS", "DEFERRED"),
    ),
    MaterialProfile(
        "brushed_metal",
        frozenset({"PBR", "ANISOTROPY"}),
        ("EMISSIVE", "FOG"),
        ("FORWARD", "FORWARD_PLUS", "DEFERRED"),
    ),
    MaterialProfile(
        "unlit_sign",
        frozenset(),
        ("ALPHA_MASK", "FOG"),
        LIGHT_PATHS,
    ),
)


def resolve_dependencies(keywords: set[str] | frozenset[str]) -> frozenset[str]:
    """Return the keyword closure required to compile the variant."""

    resolved = set(keywords)
    while True:
        implied = {
            dependency
            for keyword in resolved
            for dependency in IMPLIED_BY[keyword]
        }
        additions = implied - resolved
        if not additions:
            return frozenset(resolved)
        resolved.update(additions)


def minimize_keywords(resolved_keywords: set[str] | frozenset[str]) -> frozenset[str]:
    """Drop keywords that another selected keyword already activates."""

    resolved = set(resolved_keywords)
    minimal = {
        keyword
        for keyword in resolved
        if not any(
            keyword in resolve_dependencies({other})
            for other in resolved
            if other != keyword
        )
    }
    return frozenset(minimal)


def validate_variant(resolved_keywords: frozenset[str], path: str) -> tuple[str, ...]:
    """Return all semantic and lighting-path violations for a variant."""

    reasons: list[str] = []
    if path not in LIGHT_PATHS:
        reasons.append(f"unknown_light_path:{path}")
    if "PBR" not in resolved_keywords and resolved_keywords & PBR_ONLY_KEYWORDS:
        reasons.append("pbr_required")
    if "ANISOTROPY" in resolved_keywords and "NORMAL_MAP" not in resolved_keywords:
        reasons.append("anisotropy_requires_normal_map")
    if "TRANSMISSION" in resolved_keywords and "ALPHA_MASK" in resolved_keywords:
        reasons.append("transmission_conflicts_with_alpha_mask")
    if "SUBSURFACE" in resolved_keywords and (
        "TRANSMISSION" in resolved_keywords or "ANISOTROPY" in resolved_keywords
    ):
        reasons.append("subsurface_conflicts_with_transport")
    if "SUBSURFACE" in resolved_keywords and path != "FORWARD":
        reasons.append("subsurface_requires_forward")
    if "TRANSMISSION" in resolved_keywords and path in {"DEFERRED", "RAYTRACE"}:
        reasons.append("transmission_path_unsupported")
    if "ANISOTROPY" in resolved_keywords and path == "RAYTRACE":
        reasons.append("anisotropy_path_unsupported")
    if "CLEARCOAT" in resolved_keywords and path == "RAYTRACE":
        reasons.append("clearcoat_path_unsupported")
    if "SHADOW_CASCADE" in resolved_keywords and path == "RAYTRACE":
        reasons.append("shadow_cascade_path_unsupported")
    if "ALPHA_MASK" in resolved_keywords and path == "DEFERRED":
        reasons.append("alpha_mask_path_unsupported")
    return tuple(reasons)


def make_variant(raw_keywords: set[str] | frozenset[str], path: str) -> Variant:
    resolved = resolve_dependencies(raw_keywords)
    return Variant(minimize_keywords(resolved), path)


def generate_baseline_variants() -> tuple[Variant, ...]:
    """Naive Cartesian product before dependency or path pruning."""

    variants: list[Variant] = []
    for path in LIGHT_PATHS:
        for enabled in product((False, True), repeat=len(KEYWORDS)):
            raw = {
                keyword
                for keyword, is_enabled in zip(KEYWORDS, enabled, strict=True)
                if is_enabled
            }
            variants.append(make_variant(raw, path))
    return tuple(variants)


def generate_material_variants(
    materials: tuple[MaterialProfile, ...] = SCENE_MATERIALS,
) -> tuple[Variant, ...]:
    """Generate only valid, minimal variants reachable by scene materials."""

    variants: dict[tuple[str, tuple[str, ...]], Variant] = {}
    for material in materials:
        for path in material.paths:
            for enabled in product((False, True), repeat=len(material.optional)):
                raw = set(material.required)
                raw.update(
                    keyword
                    for keyword, is_enabled in zip(
                        material.optional, enabled, strict=True
                    )
                    if is_enabled
                )
                resolved = resolve_dependencies(raw)
                if validate_variant(resolved, path):
                    continue
                variant = Variant(minimize_keywords(resolved), path)
                variants[variant.cache_key] = variant
    return tuple(variants.values())
