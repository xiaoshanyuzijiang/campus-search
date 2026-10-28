// Read a badge in memory; white backgrounds and gray JPEG edges do not set its hue.
window.schoolBadgeTheme = (() => {
  function fromPixels(pixels) {
    const bins = Array.from({ length: 24 }, () => ({ weight: 0, rgb: [0, 0, 0] }));
    const neutral = { weight: 0, rgb: [0, 0, 0] };
    for (let i = 0; i < pixels.length; i += 4) {
      const rgb = [pixels[i], pixels[i + 1], pixels[i + 2]];
      const alpha = pixels[i + 3] / 255;
      if (alpha < 0.5) continue;
      const max = Math.max(...rgb);
      const min = Math.min(...rgb);
      const delta = max - min;
      const saturation = max ? delta / max : 0;
      let bucket;
      let weight;
      if (delta > 24 && saturation > 0.18 && max > 35) {
        let hue = max === rgb[0] ? (rgb[1] - rgb[2]) / delta
          : max === rgb[1] ? 2 + (rgb[2] - rgb[0]) / delta
            : 4 + (rgb[0] - rgb[1]) / delta;
        hue = (hue * 60 + 360) % 360;
        bucket = bins[Math.round(hue / 15) % bins.length];
        weight = saturation * saturation * alpha;
      } else if (max < 220) {
        bucket = neutral;
        weight = (1 - max / 255) ** 2 * alpha;
      } else {
        continue;
      }
      bucket.weight += weight;
      rgb.forEach((channel, index) => { bucket.rgb[index] += channel * weight; });
    }
    const neighbors = (index) => [-1, 0, 1].map((offset) => bins[(index + offset + bins.length) % bins.length]);
    const scores = bins.map((_, index) => neighbors(index).reduce((sum, bin) => sum + bin.weight, 0));
    const best = scores.indexOf(Math.max(...scores));
    const chosen = scores[best] > 0 ? neighbors(best) : [neutral];
    const total = chosen.reduce((sum, bin) => sum + bin.weight, 0);
    if (!total) return null;
    const rgb = [0, 1, 2].map((index) => chosen.reduce((sum, bin) => sum + bin.rgb[index], 0) / total);
    // Keep accent text readable, including badges in bright green or yellow.
    const luminance = () => rgb.reduce((sum, channel, index) => {
      const value = channel / 255;
      return sum + [0.2126, 0.7152, 0.0722][index] * (value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4);
    }, 0);
    while (luminance() > 0.18) rgb.forEach((_, index) => { rgb[index] *= 0.92; });
    const mix = (white) => "#" + rgb.map((channel) => Math.round(channel * (1 - white) + 255 * white).toString(16).padStart(2, "0")).join("");
    return { color: mix(0), soft: mix(0.95), border: mix(0.84) };
  }

  function fromImage(image) {
    const canvas = document.createElement("canvas");
    const scale = Math.min(1, 80 / Math.max(image.naturalWidth, image.naturalHeight));
    canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
    canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
    const context = canvas.getContext("2d", { willReadFrequently: true });
    if (!context) return null;
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    return fromPixels(context.getImageData(0, 0, canvas.width, canvas.height).data);
  }

  return { fromPixels, fromImage };
})();
