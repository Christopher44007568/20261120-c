"""Domain errors raised by the material graph pipeline."""


class GraphError(Exception):
    """Base class for all material graph errors."""


class CycleError(GraphError):
    """Raised when the graph contains a directed cycle."""

    def __init__(self, cycle):
        self.cycle = list(cycle)
        names = " -> ".join(self.cycle + [self.cycle[0]])
        super().__init__(f"cyclic dependency rejected: {names}")


class ConnectionError(GraphError):
    """Raised when an edge references unknown or incompatible ports."""


class TypeInferenceError(GraphError):
    """Raised when node types cannot be resolved consistently."""


class CompileError(GraphError):
    """Raised when a generated shader fails compiler verification."""
