const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const context = { window: {} };
vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../ui/assets/badge-theme.js"), "utf8"), context);
const { fromPixels } = context.window.schoolBadgeTheme;
const pixels = (...groups) => Uint8ClampedArray.from(groups.flatMap(([rgb, count]) => Array.from({ length: count }, () => rgb).flat()));
const channels = (hex) => hex.slice(1).match(/../g).map((value) => parseInt(value, 16));

test("a red badge keeps a red theme despite a large white background and gray edges", () => {
  const theme = fromPixels(pixels([[255, 255, 255, 255], 900], [[238, 20, 25, 255], 80], [[170, 170, 170, 255], 100]));
  const [r, g, b] = channels(theme.color);
  assert.ok(r > g * 3 && r > b * 3);
  const soft = channels(theme.soft);
  assert.ok(soft.every((value) => value >= 240));
  assert.ok(soft[0] > soft[2]);
});

test("the dominant hue wins over a smaller colored detail", () => {
  const theme = fromPixels(pixels([[30, 75, 185, 255], 100], [[235, 30, 20, 255], 12]));
  const [r, g, b] = channels(theme.color);
  assert.ok(b > r * 3 && b > g * 2);
});

test("bright badge colors produce readable accent text", () => {
  for (const rgb of [[0, 255, 0, 255], [255, 255, 0, 255]]) {
    const theme = fromPixels(pixels([rgb, 100]));
    const linear = channels(theme.color).map((channel) => {
      const value = channel / 255;
      return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
    });
    const luminance = linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
    assert.ok(1.05 / (luminance + 0.05) >= 4.5);
  }
});

test("a monochrome badge produces a neutral theme", () => {
  const theme = fromPixels(pixels([[255, 255, 255, 255], 900], [[45, 45, 45, 255], 100]));
  const [r, g, b] = channels(theme.color);
  assert.equal(r, g);
  assert.equal(g, b);
});

test("empty, white and transparent images keep the fallback theme", () => {
  assert.equal(fromPixels(new Uint8ClampedArray()), null);
  assert.equal(fromPixels(pixels([[255, 255, 255, 255], 100])), null);
  assert.equal(fromPixels(pixels([[255, 0, 0, 0], 100])), null);
});
