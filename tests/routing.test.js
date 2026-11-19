"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const Routing = require("../src/routing.js");

const report = Routing.buildRoutingReport();

test("all routed state changes are orthogonal or adjacent-layer vias", () => {
  assert.equal(report.passes, true);
  for (const net of report.nets) {
    assert.deepEqual(net.path[0], net.start);
    assert.deepEqual(net.path[net.path.length - 1], net.end);
    for (let index = 1; index < net.path.length; index += 1) {
      const a = net.path[index - 1];
      const b = net.path[index];
      const planarDistance = Math.abs(a.x - b.x) + Math.abs(a.y - b.y);
      if (a.layer === b.layer) {
        assert.equal(planarDistance, 1, `${net.name} has a non-orthogonal step`);
      } else {
        assert.equal(planarDistance, 0, `${net.name} moved and changed layer at once`);
        assert.equal(Math.abs(a.layer - b.layer), 1);
      }
    }
  }
});

test("all routes avoid every obstacle footprint", () => {
  const board = Routing.createBoard();
  assert.equal(report.obstacleValidation.passes, true);
  for (const net of report.nets) {
    for (const node of net.path) {
      assert.equal(board.blockedAt(node.x, node.y), false);
    }
  }
  for (const obstacle of report.obstacleValidation.checks) {
    assert.equal(obstacle.routeCellsInside, 0);
  }
});

test("every via is uniquely placed, unblocked, and belongs to its net", () => {
  assert.equal(report.viaValidation.passes, true);
  assert.equal(report.vias.length, 6);
  const centers = new Set();
  for (const via of report.vias) {
    assert.notEqual(via.fromLayer, via.toLayer);
    assert.ok(via.fromLayer >= 0 && via.fromLayer < 4);
    assert.ok(via.toLayer >= 0 && via.toLayer < 4);
    const center = `${via.x}:${via.y}`;
    assert.equal(centers.has(center), false, "via centers must not collide");
    centers.add(center);
    const net = report.nets.find((item) => item.name === via.net);
    assert.ok(net);
    assert.ok(
      net.path.some(
        (node, index) =>
          index > 0 &&
          node.x === via.x &&
          node.y === via.y &&
          node.layer === via.toLayer &&
          net.path[index - 1].layer !== via.toLayer,
      ),
    );
  }
});

test("all six nets are routed with zero crossings, the absolute lower bound", () => {
  assert.equal(report.routedNets, report.totalNets);
  assert.equal(report.crossings, 0);
  assert.equal(report.crossingLowerBound, 0);
  assert.equal(report.minimumCrossingsProven, true);
  assert.equal(report.conflicts.length, 0);
  assert.ok(report.planarLength > 0);
  assert.equal(report.weightedLength, report.planarLength + report.viaCount * Routing.VIA_COST);
});
