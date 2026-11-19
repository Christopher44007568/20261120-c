import test from 'node:test';
import assert from 'node:assert/strict';
import {
  ATMOSPHERE,
  cloudOpticalDepth,
  cloudProfile,
  cloudShadowFraction,
  colorDistance,
  directIlluminance,
  luminance,
  skyColor,
  sunDirection,
  sunTransmittance
} from '../src/atmosphere.js';

test('sun direction is a unit vector for the validated elevation range', () => {
  for (const elevation of [-6, 0, 14, 45, 90]) {
    const direction = sunDirection(elevation);
    const length = Math.hypot(direction.x, direction.y, direction.z);
    assert.ok(Math.abs(length - 1) < 1e-12);
  }
  assert.ok(Math.abs(sunDirection(14).y - Math.sin(14 * Math.PI / 180)) < 1e-12);
});

test('noon zenith is blue dominant and sunset horizon turns warm', () => {
  const noon = skyColor(89.5, 90);
  const noonHorizon = skyColor(0.8, 90);
  const sunsetHorizon = skyColor(0.8, 2);
  assert.ok(noon[2] > noon[0], 'blue should exceed red at the zenith');
  assert.ok(sunsetHorizon[0] - sunsetHorizon[2] >
    noonHorizon[0] - noonHorizon[2], 'sunset horizon should be warmer');
});

test('direct sunlight falls with a larger scattering coefficient', () => {
  let previous = Infinity;
  for (let scale = 0.2; scale <= 3.001; scale += 0.1) {
    const transmittance = luminance(sunTransmittance(14, scale, 0.82));
    assert.ok(transmittance < previous, `transmittance must fall at ${scale}`);
    previous = transmittance;
  }
});

test('direct illuminance increases with solar elevation', () => {
  let previous = -1;
  for (let elevation = 0; elevation <= 90; elevation += 1) {
    const illuminance = directIlluminance(elevation);
    assert.ok(illuminance >= previous, `illuminance must rise at ${elevation}`);
    previous = illuminance;
  }
});

test('sky and horizon colors are continuous across solar elevations', () => {
  let previousZenith = null;
  let previousHorizon = null;
  let maxDelta = 0;
  for (let elevation = -6; elevation <= 90.001; elevation += 0.25) {
    const zenith = skyColor(89.5, elevation);
    const horizon = skyColor(0.8, elevation);
    if (previousZenith) {
      maxDelta = Math.max(
        maxDelta,
        colorDistance(previousZenith, zenith),
        colorDistance(previousHorizon, horizon)
      );
    }
    previousZenith = zenith;
    previousHorizon = horizon;
  }
  assert.ok(maxDelta < 0.2, `adjacent color delta ${maxDelta} should be below 0.2`);
});

test('the sky-to-horizon gradient has no visible step', () => {
  for (const elevation of [14, 62, 90]) {
    let previous = null;
    let maxDelta = 0;
    for (let viewElevation = 0.8; viewElevation <= 45; viewElevation += 0.5) {
      const color = skyColor(viewElevation, elevation);
      if (previous) maxDelta = Math.max(maxDelta, colorDistance(previous, color));
      previous = color;
    }
    assert.ok(maxDelta < 0.06, `gradient delta ${maxDelta} at ${elevation}°`);
  }
});

test('cloud optical depth and shadow fraction rise with coverage and thickness', () => {
  let previousOptical = 0;
  let previousShadow = 0;
  for (const coverage of [0.1, 0.25, 0.5, 0.75, 1]) {
    for (const thickness of [0.5, 1.5, 3]) {
      const optical = cloudOpticalDepth(coverage, thickness);
      const shadow = cloudShadowFraction(coverage, thickness);
      assert.ok(optical > 0);
      assert.ok(shadow > 0 && shadow <= 1);
      if (thickness === 0.5) {
        assert.ok(optical > previousOptical, 'coverage must raise optical depth');
        assert.ok(shadow > previousShadow, 'coverage must raise shadow');
        previousOptical = optical;
        previousShadow = shadow;
      }
    }
  }
  assert.ok(cloudOpticalDepth(0.6, 3) > cloudOpticalDepth(0.6, 1.5));
  assert.ok(cloudShadowFraction(0.6, 3) > cloudShadowFraction(0.6, 1.5));
});

test('cloud profile exposes height, optical depth, and shadow coverage', () => {
  const profile = cloudProfile();
  assert.equal(profile.baseKm, ATMOSPHERE.cloudBaseKm);
  assert.ok(profile.topKm > profile.baseKm);
  assert.ok(profile.opticalDepth > 0);
  assert.ok(profile.shadowFraction > 0 && profile.shadowFraction < 1);
});
