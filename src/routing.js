(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.PcbRouting = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  function key(layer, x, y) {
    return `${layer}:${x}:${y}`;
  }

  function parseKey(value) {
    const [layer, x, y] = value.split(":").map(Number);
    return { layer, x, y };
  }

  const LAYERS = Object.freeze([
    { index: 0, name: "TOP", label: "F.Cu", color: "#ffb45c" },
    { index: 1, name: "IN1", label: "In1.Cu", color: "#6ee7f2" },
    { index: 2, name: "IN2", label: "In2.Cu", color: "#f097ff" },
    { index: 3, name: "BOT", label: "B.Cu", color: "#89efac" },
  ]);

  const BOARD = Object.freeze({ width: 24, height: 16, layers: 4 });

  const OBSTACLES = Object.freeze([
    { id: "U1", label: "MCU", x: 9, y: 5, width: 5, height: 5, height3d: 3.2 },
    { id: "PWR", label: "PWR", x: 2, y: 2, width: 3, height: 3, height3d: 2.6 },
    { id: "SEN", label: "SENSOR", x: 18, y: 2, width: 3, height: 4, height3d: 2.1 },
    { id: "DSP", label: "DISPLAY", x: 18, y: 10, width: 3, height: 4, height3d: 2.4 },
    { id: "Y1", label: "XTAL", x: 6, y: 12, width: 3, height: 3, height3d: 1.6 },
    { id: "C1", label: "CAP", x: 14, y: 3, width: 2, height: 2, height3d: 1.3 },
  ]);

  const NETS = Object.freeze([
    { name: "VCC", color: "#ffb45c", start: { layer: 0, x: 5, y: 3 }, end: { layer: 1, x: 17, y: 3 } },
    { name: "LED", color: "#89efac", start: { layer: 0, x: 10, y: 10 }, end: { layer: 3, x: 1, y: 8 } },
    { name: "XTAL", color: "#f097ff", start: { layer: 0, x: 12, y: 10 }, end: { layer: 2, x: 9, y: 13 } },
    { name: "SDA", color: "#6ee7f2", start: { layer: 0, x: 8, y: 7 }, end: { layer: 2, x: 17, y: 5 } },
    { name: "SCL", color: "#79a9ff", start: { layer: 0, x: 8, y: 9 }, end: { layer: 1, x: 17, y: 6 } },
    { name: "MOSI", color: "#ff7d91", start: { layer: 0, x: 14, y: 7 }, end: { layer: 2, x: 17, y: 12 } },
  ]);

  function obstacleCells(obstacle) {
    const cells = [];
    for (let y = obstacle.y; y < obstacle.y + obstacle.height; y += 1) {
      for (let x = obstacle.x; x < obstacle.x + obstacle.width; x += 1) {
        cells.push({ x, y });
      }
    }
    return cells;
  }

  function createBoard() {
    const blocked = new Set();
    for (const obstacle of OBSTACLES) {
      for (const cell of obstacleCells(obstacle)) {
        blocked.add(`${cell.x}:${cell.y}`);
      }
    }
    return {
      ...BOARD,
      obstacles: OBSTACLES,
      blocked,
      inBounds(x, y) {
        return x >= 0 && y >= 0 && x < BOARD.width && y < BOARD.height;
      },
      blockedAt(x, y) {
        return !this.inBounds(x, y) || blocked.has(`${x}:${y}`);
      },
    };
  }

  function inBounds(layer, x, y) {
    return layer >= 0 && layer < BOARD.layers && x >= 0 && y >= 0 && x < BOARD.width && y < BOARD.height;
  }

  class MinHeap {
    constructor() {
      this.items = [];
      this.serial = 0;
    }

    push(priority, node) {
      const item = { priority, serial: this.serial += 1, node };
      this.items.push(item);
      let index = this.items.length - 1;
      while (index > 0) {
        const parent = (index - 1) >> 1;
        if (this.compare(this.items[parent], item) <= 0) break;
        this.items[index] = this.items[parent];
        index = parent;
      }
      this.items[index] = item;
    }

    compare(a, b) {
      return a.priority - b.priority || a.serial - b.serial;
    }

    pop() {
      if (!this.items.length) return null;
      const first = this.items[0];
      const last = this.items.pop();
      if (this.items.length && last) {
        let index = 0;
        while (true) {
          const left = index * 2 + 1;
          const right = left + 1;
          if (left >= this.items.length) break;
          let child = left;
          if (right < this.items.length && this.compare(this.items[right], this.items[left]) < 0) {
            child = right;
          }
          if (this.compare(last, this.items[child]) <= 0) break;
          this.items[index] = this.items[child];
          index = child;
        }
        this.items[index] = last;
      }
      return first.node;
    }
  }

  const VIA_COST = 9;
  const OCCUPIED_COST = 60;

  function heuristic(node, goal) {
    return (
      Math.abs(node.x - goal.x) +
      Math.abs(node.y - goal.y) +
      VIA_COST * Math.abs(node.layer - goal.layer)
    );
  }

  function findPath(board, start, goal, occupancy, viaCells, reserved) {
    const startKey = key(start.layer, start.x, start.y);
    const goalKey = key(goal.layer, goal.x, goal.y);
    const heap = new MinHeap();
    const best = new Map([[startKey, 0]]);
    const cameFrom = new Map();
    heap.push(heuristic(start, goal), start);

    while (heap.items.length) {
      const current = heap.pop();
      const currentKey = key(current.layer, current.x, current.y);
      if (currentKey === goalKey) {
        const path = [];
        let cursor = currentKey;
        while (cursor) {
          path.push(parseKey(cursor));
          cursor = cameFrom.get(cursor);
        }
        return path.reverse();
      }
      const neighbors = [
        { layer: current.layer, x: current.x + 1, y: current.y },
        { layer: current.layer, x: current.x - 1, y: current.y },
        { layer: current.layer, x: current.x, y: current.y + 1 },
        { layer: current.layer, x: current.x, y: current.y - 1 },
      ];
      for (const neighbor of neighbors) {
        if (!inBounds(neighbor.layer, neighbor.x, neighbor.y)) continue;
        if (board.blockedAt(neighbor.x, neighbor.y)) continue;
        const prefix = `${neighbor.layer}:`;
        if (reserved.has(prefix + neighbor.x + ":" + neighbor.y)) continue;
        const occupied = occupancy.has(prefix + neighbor.x + ":" + neighbor.y);
        const stepCost = 1 + (occupied ? OCCUPIED_COST : 0);
        relax(neighbor, currentKey, stepCost);
      }
      for (const layer of [current.layer - 1, current.layer + 1]) {
        if (!inBounds(layer, current.x, current.y)) continue;
        if (board.blockedAt(current.x, current.y)) continue;
        const viaKey = `${current.x}:${current.y}`;
        if (viaCells.has(viaKey)) continue;
        const targetKey = key(layer, current.x, current.y);
        if (reserved.has(targetKey)) continue;
        const occupied = occupancy.has(targetKey);
        relax(
          { layer, x: current.x, y: current.y },
          currentKey,
          VIA_COST + (occupied ? OCCUPIED_COST : 0),
        );
      }

      function relax(node, fromKey, cost) {
        const nodeKey = key(node.layer, node.x, node.y);
        const nextCost = best.get(currentKey) + cost;
        if (nextCost >= (best.get(nodeKey) ?? Infinity)) return;
        best.set(nodeKey, nextCost);
        cameFrom.set(nodeKey, fromKey);
        heap.push(nextCost + heuristic(node, goal), node);
      }
    }
    return null;
  }

  function routeOrder(order) {
    const board = createBoard();
    const occupancy = new Set();
    const viaCells = new Set();
    const paths = {};
    const netsByName = new Map(NETS.map((net) => [net.name, net]));

    for (const name of order) {
      const net = netsByName.get(name);
      const reserved = new Set();
      for (const other of NETS) {
        if (other.name === name) continue;
        for (const pin of [other.start, other.end]) {
          reserved.add(key(pin.layer, pin.x, pin.y));
        }
      }
      const path = findPath(board, net.start, net.end, occupancy, viaCells, reserved);
      if (!path) return null;
      paths[name] = path;
      for (const node of path) occupancy.add(key(node.layer, node.x, node.y));
      for (let index = 1; index < path.length; index += 1) {
        if (path[index].layer !== path[index - 1].layer) {
          viaCells.add(`${path[index].x}:${path[index].y}`);
        }
      }
    }
    return paths;
  }

  function routeAll() {
    const preferred = NETS.map((net) => net.name);
    const orders = [
      preferred,
      ["LED", "XTAL", "SDA", "SCL", "MOSI", "VCC"],
      ["SDA", "SCL", "MOSI", "XTAL", "LED", "VCC"],
      ["VCC", "SDA", "SCL", "MOSI", "LED", "XTAL"],
    ];
    for (const order of orders) {
      const paths = routeOrder(order);
      if (paths) return { paths, order };
    }
    return { paths: null, order: [] };
  }

  function extractVias(path, net) {
    const vias = [];
    for (let index = 1; index < path.length; index += 1) {
      const previous = path[index - 1];
      const current = path[index];
      if (previous.layer === current.layer) continue;
      const last = vias[vias.length - 1];
      if (last && last.x === current.x && last.y === current.y) {
        last.toLayer = current.layer;
      } else {
        vias.push({
          net,
          x: current.x,
          y: current.y,
          fromLayer: previous.layer,
          toLayer: current.layer,
        });
      }
    }
    return vias;
  }

  function routeLength(path) {
    let planar = 0;
    let vias = 0;
    for (let index = 1; index < path.length; index += 1) {
      if (path[index].layer === path[index - 1].layer) planar += 1;
      else vias += 1;
    }
    return { planar, vias, weighted: planar + vias * VIA_COST };
  }

  function crossingInventory(paths) {
    const owners = new Map();
    for (const [net, path] of Object.entries(paths || {})) {
      for (const node of path) {
        const cellKey = key(node.layer, node.x, node.y);
        if (!owners.has(cellKey)) owners.set(cellKey, new Set());
        owners.get(cellKey).add(net);
      }
    }
    const conflicts = [];
    for (const [cellKey, nets] of owners.entries()) {
      if (nets.size > 1) {
        conflicts.push({ cell: parseKey(cellKey), nets: [...nets].sort() });
      }
    }
    return conflicts;
  }

  function validateVias(vias) {
    const board = createBoard();
    const errors = [];
    const centers = new Map();
    for (const via of vias) {
      if (via.fromLayer === via.toLayer) {
        errors.push(`${via.net}: via has identical layers at (${via.x},${via.y})`);
      }
      if (Math.abs(via.toLayer - via.fromLayer) > 1) {
        const low = Math.min(via.fromLayer, via.toLayer);
        const high = Math.max(via.fromLayer, via.toLayer);
        for (let layer = low; layer <= high; layer += 1) {
          if (board.blockedAt(via.x, via.y)) {
            errors.push(`${via.net}: via crosses blocked cell on layer ${layer}`);
          }
        }
      } else if (board.blockedAt(via.x, via.y)) {
        errors.push(`${via.net}: via center lies in an obstacle`);
      }
      const centerKey = `${via.x}:${via.y}`;
      if (centers.has(centerKey)) {
        errors.push(`${via.net}: via collides with ${centers.get(centerKey)} at (${via.x},${via.y})`);
      } else {
        centers.set(centerKey, via.net);
      }
    }
    return errors;
  }

  function validateRouteCells(board, net, path) {
    const errors = [];
    for (const node of path) {
      if (board.blockedAt(node.x, node.y)) {
        errors.push(`${net}: route enters obstacle at layer ${node.layer} (${node.x},${node.y})`);
      }
    }
    return errors;
  }

  function buildRoutingReport() {
    const board = createBoard();
    const result = routeAll();
    if (!result.paths) {
      return {
        passes: false,
        routedNets: 0,
        totalNets: NETS.length,
        crossings: null,
        errors: ["No complete routing solution found."],
      };
    }
    const vias = [];
    const netReports = [];
    const errors = [];
    for (const net of NETS) {
      const path = result.paths[net.name];
      const netVias = extractVias(path, net.name);
      vias.push(...netVias);
      errors.push(...validateRouteCells(board, net.name, path));
      const length = routeLength(path);
      netReports.push({
        name: net.name,
        color: net.color,
        start: net.start,
        end: net.end,
        states: path.length,
        planarLength: length.planar,
        viaCount: netVias.length,
        weightedLength: length.planar + netVias.length * VIA_COST,
        layerSequence: [...new Set(path.map((node) => node.layer))],
        path,
      });
    }
    errors.push(...validateVias(vias));
    const conflicts = crossingInventory(result.paths);
    if (conflicts.length) {
      errors.push(`${conflicts.length} same-layer crossing cells found`);
    }
    const obstacleChecks = OBSTACLES.map((obstacle) => {
      let routeCellsInside = 0;
      for (const net of netReports) {
        for (const node of net.path) {
          if (
            node.x >= obstacle.x &&
            node.x < obstacle.x + obstacle.width &&
            node.y >= obstacle.y &&
            node.y < obstacle.y + obstacle.height
          ) {
            routeCellsInside += 1;
          }
        }
      }
      return {
        id: obstacle.id,
        label: obstacle.label,
        cells: obstacle.width * obstacle.height,
        routeCellsInside,
      };
    });
    return {
      passes: errors.length === 0 && conflicts.length === 0,
      routedNets: NETS.length,
      totalNets: NETS.length,
      routeOrder: result.order,
      crossings: conflicts.length,
      crossingLowerBound: 0,
      minimumCrossingsProven: conflicts.length === 0,
      viaCount: vias.length,
      planarLength: netReports.reduce((sum, net) => sum + net.planarLength, 0),
      weightedLength: netReports.reduce((sum, net) => sum + net.weightedLength, 0),
      vias: vias.map((via) => ({
        ...via,
        fromLayerName: LAYERS[via.fromLayer]?.name,
        toLayerName: LAYERS[via.toLayer]?.name,
      })),
      viaValidation: { passes: !errors.some((error) => error.includes("via")), errors: errors.filter((error) => error.includes("via")) },
      obstacleValidation: { passes: !errors.some((error) => error.includes("obstacle") || error.includes("route enters")), checks: obstacleChecks },
      errors,
      conflicts,
      nets: netReports,
      obstacles: OBSTACLES,
      layers: LAYERS,
    };
  }

  return {
    BOARD,
    LAYERS,
    OBSTACLES,
    NETS,
    VIA_COST,
    createBoard,
    obstacleCells,
    findPath,
    routeAll,
    extractVias,
    routeLength,
    crossingInventory,
    validateVias,
    buildRoutingReport,
  };
});

