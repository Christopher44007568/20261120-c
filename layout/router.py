"""Multi-net orthogonal router with rip-up/reroute and via bookkeeping."""

from collections import defaultdict
from dataclasses import dataclass, field

from .astar import VIA_COST, astar


@dataclass
class RouteResult:
    nets: dict
    vias: list = field(default_factory=list)
    crossings: int = 0
    crossing_events: list = field(default_factory=list)
    planar_length: int = 0
    via_count: int = 0
    total_length: float = 0.0
    via_errors: list = field(default_factory=list)
    routed: bool = True


class Router:
    def __init__(self, board, pins, rip_up_passes=2):
        board.check_pins(pins)
        self.board = board
        self.pins = pins
        self.rip_up_passes = rip_up_passes
        self.endpoints = defaultdict(list)
        for pin in pins:
            self.endpoints[pin.net].append((pin.layer, pin.cell))

    def _net_order(self):
        def span(net):
            pts = self.endpoints[net]
            return max(
                abs(a[1][0] - b[1][0]) + abs(a[1][1] - b[1][1])
                + VIA_COST * abs(a[0] - b[0])
                for a in pts for b in pts
            )
        return sorted(self.endpoints, key=span, reverse=True)

    def route(self):
        reserved = {(p.layer, p.cell) for p in self.pins}
        paths = {}
        occupancy = defaultdict(int)
        for net in self._net_order():
            start, goal = self.endpoints[net]
            net_reserved = {s for s in reserved
                            if not self._belongs(s, net)}
            path = astar(self.board, start, goal, net_reserved, occupancy)
            if path is None:
                return RouteResult(nets=paths, routed=False)
            paths[net] = path
            for state in path:
                occupancy[state] += 1

        for _ in range(self.rip_up_passes):
            before = self._count_crossings(paths)
            if before == 0:
                break
            paths, occupancy = self._rip_up_round(paths, reserved,
                                                   before)
            if self._count_crossings(paths):
                paths, occupancy = self._pairwise_round(
                    paths, reserved, self._count_crossings(paths))
        return self._build_result(paths)

    def _belongs(self, state, net):
        return any(state == ep for ep in self.endpoints[net])

    def _segments(self, path):
        """Yield directed edges as canonical (state_a, state_b) tuples."""
        for a, b in zip(path, path[1:]):
            yield tuple(sorted((a, b), key=lambda s: (s[0], s[1])))

    def _count_crossings(self, paths):
        events, count = [], 0
        cell_owners = defaultdict(set)
        edge_owners = defaultdict(set)
        for net, path in paths.items():
            for layer, cell in path[1:-1]:
                cell_owners[(layer, cell)].add(net)
            for edge in self._segments(path):
                edge_owners[edge].add(net)
        for (layer, cell), owners in cell_owners.items():
            if len(owners) > 1:
                count += 1
                events.append(("cell", layer, cell, sorted(owners)))
        for edge, owners in edge_owners.items():
            if len(owners) > 1:
                count += 1
                events.append(("edge", edge, sorted(owners)))
        self._last_events = events
        return count

    def _extract_vias(self, paths):
        vias = []
        for net, path in paths.items():
            for (la, cell), (lb, _) in zip(path, path[1:]):
                if la != lb:
                    vias.append((net, cell, min(la, lb), max(la, lb)))
        return vias

    def _validate_vias(self, vias):
        errors = []
        seen = set()
        for net, cell, lo, hi in vias:
            if hi != lo + 1:
                errors.append(f"{net}: via spans non-adjacent layers {lo}-{hi}")
            key = (cell, lo)
            if key in seen:
                errors.append(f"duplicate via at layer {lo} cell {cell}")
            seen.add(key)
            for layer in range(lo, hi + 1):
                if self.board.blocked(layer, cell):
                    errors.append(
                        f"{net}: via cell {cell} blocked on layer {layer}")
        return errors

    def _build_result(self, paths):
        crossings = self._count_crossings(paths)
        vias = self._extract_vias(paths)
        planar = sum(max(0, len(path) - 1)
                     - sum(1 for a, b in zip(path, path[1:]) if a[0] != b[0])
                     for path in paths.values())
        via_errors = self._validate_vias(vias)
        return RouteResult(
            nets=paths,
            vias=vias,
            crossings=crossings,
            crossing_events=getattr(self, "_last_events", []),
            planar_length=planar,
            via_count=len(vias),
            total_length=planar + VIA_COST * len(vias),
            via_errors=via_errors,
            routed=True,
        )

    def _rip_up_round(self, paths, reserved, current_crossings):
        """Re-route conflict nets with hotspot weighting; accept strict gains."""
        occupancy = defaultdict(int)
        for path in paths.values():
            for state in path:
                occupancy[state] += 1
        events = self._collect_events(paths)
        hotspots = defaultdict(int)
        conflict_nets = defaultdict(int)
        for event in events:
            owners = event[-1]
            states = self._event_states(event)
            for state in states:
                hotspots[state] += 1
            for net in owners:
                conflict_nets[net] += 1
        order = sorted(conflict_nets,
                       key=lambda n: conflict_nets[n], reverse=True)
        order += [n for n in self._net_order() if n not in conflict_nets]
        for net in order:
            for state in paths[net]:
                occupancy[state] -= 1
            start, goal = self.endpoints[net]
            net_reserved = {s for s in reserved
                            if not self._belongs(s, net)}
            candidate = astar(self.board, start, goal, net_reserved,
                              occupancy, hotspots)
            if candidate is None:
                for state in paths[net]:
                    occupancy[state] += 1
                continue
            trial = dict(paths)
            trial[net] = candidate
            trial_crossings = self._count_crossings(trial)
            if trial_crossings < current_crossings:
                paths = trial
                current_crossings = trial_crossings
                for state in candidate:
                    occupancy[state] += 1
                events = self._collect_events(paths)
                hotspots = defaultdict(int)
                for event in events:
                    for state in self._event_states(event):
                        hotspots[state] += 1
            else:
                for state in paths[net]:
                    occupancy[state] += 1
        return paths, occupancy

    def _collect_events(self, paths):
        self._count_crossings(paths)
        return getattr(self, "_last_events", [])

    def _pairwise_round(self, paths, reserved, current_crossings):
        """Temporarily remove both nets of each conflict, then re-route."""
        events = self._collect_events(paths)
        pairs = set()
        for event in events:
            owners = event[-1]
            if len(owners) == 2:
                pairs.add(tuple(sorted(owners)))
        for net_a, net_b in pairs:
            occupancy = defaultdict(int)
            for net, path in paths.items():
                if net in (net_a, net_b):
                    continue
                for state in path:
                    occupancy[state] += 1
            trial = dict(paths)
            ok = True
            for net in (net_a, net_b):
                start, goal = self.endpoints[net]
                net_reserved = {s for s in reserved
                                if not self._belongs(s, net)}
                candidate = astar(self.board, start, goal, net_reserved,
                                  occupancy)
                if candidate is None:
                    ok = False
                    break
                trial[net] = candidate
                for state in candidate:
                    occupancy[state] += 1
            trial_crossings = (self._count_crossings(trial) if ok
                               else current_crossings + 1)
            if ok and trial_crossings < current_crossings:
                paths = trial
                current_crossings = trial_crossings
        occupancy = defaultdict(int)
        for path in paths.values():
            for state in path:
                occupancy[state] += 1
        return paths, occupancy

    def _event_states(self, event):
        if event[0] == "cell":
            _, layer, cell, _ = event
            return [(layer, cell)]
        _, edge, _ = event
        return list(edge)
