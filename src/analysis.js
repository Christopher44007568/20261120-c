export const ANALYSIS_SIZE = 256;
export const SPECTRUM_BINS = 92;

function fft1d(real, imag, length) {
  for (let i = 1, j = 0; i < length; i++) {
    let bit = length >> 1;
    while (j & bit) {
      j ^= bit;
      bit >>= 1;
    }
    j ^= bit;
    if (i < j) {
      [real[i], real[j]] = [real[j], real[i]];
      [imag[i], imag[j]] = [imag[j], imag[i]];
    }
  }

  for (let size = 2; size <= length; size <<= 1) {
    const angle = (-2 * Math.PI) / size;
    const wLengthReal = Math.cos(angle);
    const wLengthImag = Math.sin(angle);
    const half = size >> 1;
    for (let start = 0; start < length; start += size) {
      let wReal = 1;
      let wImag = 0;
      for (let k = 0; k < half; k++) {
        const even = start + k;
        const odd = even + half;
        const tReal = wReal * real[odd] - wImag * imag[odd];
        const tImag = wReal * imag[odd] + wImag * real[odd];
        real[odd] = real[even] - tReal;
        imag[odd] = imag[even] - tImag;
        real[even] += tReal;
        imag[even] += tImag;
        const nextReal = wReal * wLengthReal - wImag * wLengthImag;
        wImag = wReal * wLengthImag + wImag * wLengthReal;
        wReal = nextReal;
      }
    }
  }
}

function hann(index, length) {
  return 0.5 - 0.5 * Math.cos((2 * Math.PI * index) / (length - 1));
}

function powerSpectrum(field) {
  const { values, width, height } = field;
  const real = new Float64Array(values.length);
  const imag = new Float64Array(values.length);
  let mean = 0;
  for (let i = 0; i < values.length; i++) mean += values[i];
  mean /= values.length;

  for (let y = 0; y < height; y++) {
    const wy = hann(y, height);
    for (let x = 0; x < width; x++) {
      const index = y * width + x;
      real[index] = (values[index] - mean) * wy * hann(x, width);
    }
  }

  const rowReal = new Float64Array(width);
  const rowImag = new Float64Array(width);
  for (let y = 0; y < height; y++) {
    rowReal.set(real.subarray(y * width, (y + 1) * width));
    rowImag.fill(0);
    fft1d(rowReal, rowImag, width);
    real.set(rowReal, y * width);
    imag.set(rowImag, y * width);
  }

  const columnReal = new Float64Array(height);
  const columnImag = new Float64Array(height);
  for (let x = 0; x < width; x++) {
    for (let y = 0; y < height; y++) {
      columnReal[y] = real[y * width + x];
      columnImag[y] = imag[y * width + x];
    }
    fft1d(columnReal, columnImag, height);
    for (let y = 0; y < height; y++) {
      real[y * width + x] = columnReal[y];
      imag[y * width + x] = columnImag[y];
    }
  }

  return { real, imag, width, height };
}

export function radialSpectrum(field, bins = SPECTRUM_BINS) {
  const fft = powerSpectrum(field);
  const { real, imag, width, height } = fft;
  const minFrequency = 0.004;
  const maxFrequency = 0.5;
  const logMin = Math.log(minFrequency);
  const logRange = Math.log(maxFrequency) - logMin;
  const sums = new Float64Array(bins);
  const counts = new Uint32Array(bins);
  let totalPower = 0;
  let highPower = 0;
  let tailPower = 0;

  for (let y = 0; y < height; y++) {
    const fy = y < height / 2 ? y / height : (y - height) / height;
    for (let x = 0; x < width; x++) {
      const fx = x < width / 2 ? x / width : (x - width) / width;
      const frequency = Math.hypot(fx, fy);
      if (frequency < minFrequency || frequency > maxFrequency) continue;
      const bin = Math.min(
        bins - 1,
        Math.floor(((Math.log(frequency) - logMin) / logRange) * bins)
      );
      const index = y * width + x;
      const power = real[index] * real[index] + imag[index] * imag[index];
      sums[bin] += power;
      counts[bin]++;
      totalPower += power;
      if (frequency > 0.22) tailPower += power;
      if (frequency > 0.18) highPower += power;
    }
  }

  const points = [];
  for (let i = 0; i < bins; i++) {
    if (!counts[i]) continue;
    const frequency = Math.exp(logMin + ((i + 0.5) / bins) * logRange);
    points.push({ frequency, power: sums[i] / counts[i] });
  }

  let maximum = 0;
  for (const point of points) maximum = Math.max(maximum, point.power);
  for (const point of points) {
    point.db = 10 * Math.log10(Math.max(point.power / maximum, 1e-12));
  }
  points.totalPower = totalPower;
  points.highPower = highPower;
  points.tailPower = tailPower;
  return points;
}

export function gradientStatistics(field) {
  const { values, width, height } = field;
  const histogram = new Float64Array(36);
  let meanSquare = 0;
  let jxx = 0;
  let jyy = 0;
  let jxy = 0;
  let samples = 0;

  for (let y = 1; y < height - 1; y++) {
    for (let x = 1; x < width - 1; x++) {
      const center = y * width + x;
      const gx = (values[center + 1] - values[center - 1]) * 0.5;
      const gy = (values[center + width] - values[center - width]) * 0.5;
      const energy = gx * gx + gy * gy;
      meanSquare += energy;
      jxx += gx * gx;
      jyy += gy * gy;
      jxy += gx * gy;
      const angle = Math.atan2(gy, gx);
      const bin = Math.min(35, Math.floor(((angle + Math.PI) / (2 * Math.PI)) * 36));
      histogram[bin] += energy;
      samples++;
    }
  }

  const maximum = Math.max(...histogram, 1e-12);
  const normalizedHistogram = Array.from(histogram, (value) => value / maximum);
  const trace = jxx + jyy;
  const anisotropy =
    trace > 1e-12
      ? Math.sqrt((jxx - jyy) ** 2 + 4 * jxy ** 2) / trace
      : 0;
  const orientation = (0.5 * Math.atan2(2 * jxy, jxx - jyy) * 180) / Math.PI;

  return {
    rms: Math.sqrt(meanSquare / samples),
    anisotropy,
    orientation: ((orientation % 180) + 180) % 180,
    histogram: normalizedHistogram,
  };
}

function spectrumSlope(points) {
  const samples = points.filter((point) => point.frequency >= 0.03 && point.frequency <= 0.3);
  const xMean = samples.reduce((sum, point) => sum + Math.log10(point.frequency), 0) / samples.length;
  const yMean = samples.reduce((sum, point) => sum + point.db, 0) / samples.length;
  let numerator = 0;
  let denominator = 0;
  for (const point of samples) {
    const x = Math.log10(point.frequency) - xMean;
    numerator += x * (point.db - yMean);
    denominator += x * x;
  }
  return numerator / denominator;
}

function spectralProminence(points) {
  const residuals = [];
  for (let i = 3; i < points.length - 3; i++) {
    const frequency = points[i].frequency;
    if (frequency < 0.16 || frequency > 0.46) continue;
    let localMean = 0;
    for (let offset = -3; offset <= 3; offset++) localMean += points[i + offset].db;
    localMean /= 7;
    residuals.push(points[i].db - localMean);
  }
  const peak = Math.max(...residuals, 0);
  return Math.pow(10, peak / 10);
}

export function analyzeNoisePair(smoothField, warpedField, bins = SPECTRUM_BINS) {
  const smoothSpectrum = radialSpectrum(smoothField, bins);
  const warpedSpectrum = radialSpectrum(warpedField, bins);
  const smoothGradient = gradientStatistics(smoothField);
  const warpedGradient = gradientStatistics(warpedField);
  const tailRatio =
    smoothSpectrum.tailPower > 1e-20
      ? warpedSpectrum.tailPower / smoothSpectrum.tailPower
      : 1;

  return {
    smoothSpectrum,
    warpedSpectrum,
    detailGain: warpedGradient.rms / Math.max(smoothGradient.rms, 1e-8) - 1,
    tailRatio,
    artifactScore: spectralProminence(warpedSpectrum),
    spectralSlope: spectrumSlope(warpedSpectrum),
    spectralSlopeSmooth: spectrumSlope(smoothSpectrum),
    anisotropy: warpedGradient.anisotropy,
    anisotropySmooth: smoothGradient.anisotropy,
    orientation: warpedGradient.orientation,
    orientationSmooth: smoothGradient.orientation,
    histogram: warpedGradient.histogram,
    histogramSmooth: smoothGradient.histogram,
  };
}
