import {
  SH_FLOATS,
  SH_COUNT,
  UP,
  addPointLight,
  ambientCoefficients,
  clampIrradiance,
  evaluateIrradiance,
  luminance,
} from "./sh.js";

const cardinalOffsets = [
  [-1, 0],
  [1, 0],
  [0, -1],
  [0, 1],
];

export function unionRects(a, b) {
  if (!a) return b ? { ...b } : null;
  if (!b) return { ...a };
  return {
    row0: Math.min(a.row0, b.row0),
    row1: Math.max(a.row1, b.row1),
    col0: Math.min(a.col0, b.col0),
    col1: Math.max(a.col1, b.col1),
  };
}

export class ProbeGrid {
  constructor({
    cols = 14,
    rows = 10,
    spacing = 1,
    y = 0.45,
    ambient = [0.14, 0.17, 0.22],
    propagation = 0.18,
    iterations = 2,
  } = {}) {
    this.cols = cols;
    this.rows = rows;
    this.spacing = spacing;
    this.y = y;
    this.count = cols * rows;
    this.minX = -((cols - 1) * spacing) / 2;
    this.minZ = -((rows - 1) * spacing) / 2;
    this.propagation = propagation;
    this.iterations = iterations;
    this.ambient = [...ambient];

    this.positions = new Float64Array(this.count * 3);
    for (let row = 0; row < rows; row += 1) {
      for (let col = 0; col < cols; col += 1) {
        const offset = (row * cols + col) * 3;
        this.positions[offset] = this.minX + col * spacing;
        this.positions[offset + 1] = y;
        this.positions[offset + 2] = this.minZ + row * spacing;
      }
    }

    const ambientSh = ambientCoefficients(ambient);
    this.base = new Float64Array(this.count * SH_FLOATS);
    this.dynamic = new Float64Array(this.count * SH_FLOATS);
    this.target = new Float64Array(this.count * SH_FLOATS);
    this.display = new Float64Array(this.count * SH_FLOATS);
    this.propagationScratch = new Float64Array(this.count * SH_FLOATS);
    this.basis = new Float64Array(SH_COUNT);
    for (let probe = 0; probe < this.count; probe += 1) {
      this.base.set(ambientSh, probe * SH_FLOATS);
      this.target.set(ambientSh, probe * SH_FLOATS);
      this.display.set(ambientSh, probe * SH_FLOATS);
    }

    this.updateEpoch = 0;
    this.lastStats = { updatedProbes: 0, projectionTests: 0, full: true };
  }

  probePosition(index, out = new Float64Array(3)) {
    const offset = index * 3;
    out[0] = this.positions[offset];
    out[1] = this.positions[offset + 1];
    out[2] = this.positions[offset + 2];
    return out;
  }

  cellAt(position) {
    const continuousCol = Math.max(
      0,
      Math.min(this.cols - 1, (position[0] - this.minX) / this.spacing),
    );
    const continuousRow = Math.max(
      0,
      Math.min(this.rows - 1, (position[2] - this.minZ) / this.spacing),
    );
    const col0 = Math.min(this.cols - 2, Math.floor(continuousCol));
    const row0 = Math.min(this.rows - 2, Math.floor(continuousRow));
    return {
      col0,
      col1: col0 + 1,
      row0,
      row1: row0 + 1,
      tx: continuousCol - col0,
      tz: continuousRow - row0,
    };
  }

  sampleCoefficients(position, out = new Float64Array(SH_FLOATS)) {
    const cell = this.cellAt(position);
    const i00 = cell.row0 * this.cols + cell.col0;
    const i10 = cell.row0 * this.cols + cell.col1;
    const i01 = cell.row1 * this.cols + cell.col0;
    const i11 = cell.row1 * this.cols + cell.col1;
    const w00 = (1 - cell.tx) * (1 - cell.tz);
    const w10 = cell.tx * (1 - cell.tz);
    const w01 = (1 - cell.tx) * cell.tz;
    const w11 = cell.tx * cell.tz;
    out.fill(0);
    const o00 = i00 * SH_FLOATS;
    const o10 = i10 * SH_FLOATS;
    const o01 = i01 * SH_FLOATS;
    const o11 = i11 * SH_FLOATS;
    for (let value = 0; value < SH_FLOATS; value += 1) {
      out[value] =
        this.display[o00 + value] * w00 +
        this.display[o10 + value] * w10 +
        this.display[o01 + value] * w01 +
        this.display[o11 + value] * w11;
    }
    return { coefficients: out, weights: { w00, w10, w01, w11 }, cell };
  }

  sampleIrradiance(position, normal = UP, out = new Float64Array(3)) {
    const coefficients = new Float64Array(SH_FLOATS);
    const sampled = this.sampleCoefficients(position, coefficients);
    evaluateIrradiance(sampled.coefficients, normal, out, this.basis);
    clampIrradiance(out);
    return { rgb: out, weights: sampled.weights, cell: sampled.cell };
  }

  probeLuminance(index, field = "display") {
    const source = this[field];
    const offset = index * SH_FLOATS;
    const coefficients = source.subarray(offset, offset + SH_FLOATS);
    const rgb = evaluateIrradiance(coefficients, UP, new Float64Array(3), this.basis);
    clampIrradiance(rgb);
    return luminance(rgb[0], rgb[1], rgb[2]);
  }

  rectForLight(light, extraCells = this.iterations + 1) {
    return this.rectForCircle(light.position[0], light.position[2], light.radius, extraCells);
  }

  rectForCircle(x, z, radius, extraCells = this.iterations + 1) {
    const padding = extraCells * this.spacing;
    const col0 = Math.max(0, Math.floor((x - radius - padding - this.minX) / this.spacing));
    const col1 = Math.min(
      this.cols - 1,
      Math.ceil((x + radius + padding - this.minX) / this.spacing),
    );
    const row0 = Math.max(0, Math.floor((z - radius - padding - this.minZ) / this.spacing));
    const row1 = Math.min(
      this.rows - 1,
      Math.ceil((z + radius + padding - this.minZ) / this.spacing),
    );
    return { row0, row1, col0, col1 };
  }

  rectForLights(lights) {
    let rect = null;
    for (const light of lights) rect = unionRects(rect, this.rectForLight(light));
    return rect;
  }

  _projectInto(field, row0, row1, col0, col1, lights) {
    let projectionTests = 0;
    const localCols = col1 - col0 + 1;
    for (let row = row0; row <= row1; row += 1) {
      for (let col = col0; col <= col1; col += 1) {
        const probe = row * this.cols + col;
        const position = this.positions.subarray(probe * 3, probe * 3 + 3);
        const local = ((row - row0) * localCols + (col - col0)) * SH_FLOATS;
        for (const light of lights) {
          projectionTests += 1;
          addPointLight(field.subarray(local, local + SH_FLOATS), position, light, this.basis);
        }
      }
    }
    return projectionTests;
  }

  _propagate(field, rows, cols, scratch) {
    let source = field;
    let destination = scratch;
    for (let pass = 0; pass < this.iterations; pass += 1) {
      destination.fill(0);
      for (let row = 0; row < rows; row += 1) {
        for (let col = 0; col < cols; col += 1) {
          const cell = row * cols + col;
          const offset = cell * SH_FLOATS;
          for (let value = 0; value < SH_FLOATS; value += 1) {
            destination[offset + value] = source[offset + value];
          }
          let neighborCount = 0;
          for (const [dr, dc] of cardinalOffsets) {
            const neighborRow = row + dr;
            const neighborCol = col + dc;
            if (
              neighborRow < 0 ||
              neighborRow >= rows ||
              neighborCol < 0 ||
              neighborCol >= cols
            ) {
              continue;
            }
            neighborCount += 1;
            const neighborOffset = (neighborRow * cols + neighborCol) * SH_FLOATS;
            for (let value = 0; value < SH_FLOATS; value += 1) {
              destination[offset + value] +=
                source[neighborOffset + value] * this.propagation;
            }
          }
          if (neighborCount === 0) continue;
        }
      }
      [source, destination] = [destination, source];
    }
    return source;
  }

  updateAll(lights) {
    this.dynamic.fill(0);
    const projectionTests = this._projectInto(
      this.dynamic,
      0,
      this.rows - 1,
      0,
      this.cols - 1,
      lights,
    );
    const propagated = this._propagate(
      this.dynamic,
      this.rows,
      this.cols,
      this.propagationScratch,
    );
    for (let probe = 0; probe < this.count; probe += 1) {
      const offset = probe * SH_FLOATS;
      for (let value = 0; value < SH_FLOATS; value += 1) {
        this.target[offset + value] = this.base[offset + value] + propagated[offset + value];
      }
    }
    this.updateEpoch += 1;
    this.lastStats = { updatedProbes: this.count, projectionTests, full: true };
    return this.lastStats;
  }

  updateRegion(lights, rect) {
    const rows = rect.row1 - rect.row0 + 1;
    const cols = rect.col1 - rect.col0 + 1;
    const field = new Float64Array(rows * cols * SH_FLOATS);
    const scratch = new Float64Array(rows * cols * SH_FLOATS);
    const projectionTests = this._projectInto(
      field,
      rect.row0,
      rect.row1,
      rect.col0,
      rect.col1,
      lights,
    );
    const propagated = this._propagate(field, rows, cols, scratch);

    for (let row = rect.row0; row <= rect.row1; row += 1) {
      for (let col = rect.col0; col <= rect.col1; col += 1) {
        const probe = row * this.cols + col;
        const targetOffset = probe * SH_FLOATS;
        const localOffset = ((row - rect.row0) * cols + (col - rect.col0)) * SH_FLOATS;
        for (let value = 0; value < SH_FLOATS; value += 1) {
          this.dynamic[targetOffset + value] = propagated[localOffset + value];
          this.target[targetOffset + value] =
            this.base[targetOffset + value] + propagated[localOffset + value];
        }
      }
    }
    this.updateEpoch += 1;
    this.lastStats = {
      updatedProbes: rows * cols,
      projectionTests,
      full: rows === this.rows && cols === this.cols,
    };
    return this.lastStats;
  }

  computeReference(lights) {
    const referenceGrid = new ProbeGrid({
      cols: this.cols,
      rows: this.rows,
      spacing: this.spacing,
      y: this.y,
      ambient: this.ambient,
      propagation: this.propagation,
      iterations: this.iterations,
    });
    referenceGrid.updateAll(lights);
    return referenceGrid.target;
  }

  smoothDisplay(alpha) {
    const clamped = Math.max(0, Math.min(1, alpha));
    if (clamped >= 1) {
      this.display.set(this.target);
      return;
    }
    for (let index = 0; index < this.display.length; index += 1) {
      this.display[index] += (this.target[index] - this.display[index]) * clamped;
    }
  }

  resetDisplay() {
    this.display.set(this.target);
  }
}
