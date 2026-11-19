"""Board geometry: layers, grid cells, obstacles and pins."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Obstacle:
    """Axis-aligned keep-out rectangle on one layer (grid-cell coordinates)."""

    layer: int
    x0: int
    y0: int
    x1: int
    y1: int

    def cells(self):
        for x in range(self.x0, self.x1):
            for y in range(self.y0, self.y1):
                yield (x, y)


@dataclass(frozen=True)
class Pin:
    """Endpoint of a net, anchored at a grid cell on a layer."""

    net: str
    layer: int
    x: int
    y: int

    @property
    def cell(self):
        return (self.x, self.y)


@dataclass
class Board:
    width: int
    height: int
    layers: int
    obstacles: list[Obstacle] = field(default_factory=list)

    def __post_init__(self):
        self._blocked = [set() for _ in range(self.layers)]
        for obs in self.obstacles:
            if not (0 <= obs.layer < self.layers):
                raise ValueError(f"obstacle layer out of range: {obs.layer}")
            for cell in obs.cells():
                self._check_cell(cell)
                self._blocked[obs.layer].add(cell)

    def _check_cell(self, cell):
        x, y = cell
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise ValueError(f"cell outside board: {cell}")

    def blocked(self, layer, cell):
        self._check_cell(cell)
        return cell in self._blocked[layer]

    def in_bounds(self, layer, cell):
        x, y = cell
        return 0 <= layer < self.layers and 0 <= x < self.width and 0 <= y < self.height

    def check_pins(self, pins):
        for pin in pins:
            if not self.in_bounds(pin.layer, pin.cell):
                raise ValueError(f"pin outside board: {pin}")
            if self.blocked(pin.layer, pin.cell):
                raise ValueError(f"pin inside obstacle: {pin}")

    def neighbors(self, layer, cell):
        """In-plane orthogonal neighbours (vias are handled by the router)."""
        x, y = cell
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < self.width and 0 <= ny < self.height:
                if not self.blocked(layer, (nx, ny)):
                    yield (layer, (nx, ny))
