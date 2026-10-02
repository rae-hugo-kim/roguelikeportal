export function selectLatestChampion(records) {
  let selected = null;
  for (const round of records) {
    const winner = (round.finalsUma || round.finals || []).find(entry => Number(entry.rank) === 1 && entry.player);
    if (winner && Number.isFinite(Number(round.round)) && (!selected || Number(round.round) > Number(selected.round.round))) {
      selected = { round, winner };
    }
  }
  return selected;
}

// 의상을 제거한 부분 일치는 하지 않습니다. 명시한 ID가 없더라도 이름으로 다른 의상을 고르지 않습니다.
export function matchChampionCharacter(winner, registry, labels = {}) {
  if (winner.card_id != null) return registry.find(c => c.id === Number(winner.card_id)) || null;
  const normalize = name => String(name || '').normalize('NFKC').replace(/\s/g, '').toLowerCase();
  const wanted = normalize(winner.uma);
  if (!wanted) return null;
  const matches = registry.filter(c => {
    if (normalize(c.name) === wanted) return true;
    const label = labels[c.id];
    return label?.title && normalize(`${label.name} ${label.title}`) === wanted;
  });
  return matches.length === 1 ? matches[0] : null;
}

function rgbToHsl(r, g, b) {
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  const delta = max - min, lightness = (max + min) / 2;
  if (!delta) return { h: 0, s: 0, l: lightness };
  let h = max === r ? (g - b) / delta : max === g ? (b - r) / delta + 2 : (r - g) / delta + 4;
  h = (h * 60 + 360) % 360;
  return { h, s: delta / (1 - Math.abs(2 * lightness - 1)), l: lightness };
}

// 브라우저에서 64×64로 축소한 RGBA를 받습니다. 투명 픽셀·흰색·검은색은 대표색에서 제외합니다.
// 피부·머리색보다 의상 색이 반영되도록 이미지 아래쪽과 채도가 높은 픽셀에 가중치를 줍니다.
// 인접 색상 구간을 함께 집계하여 0°/360° 경계의 빨강도 같은 색상군으로 취급합니다.
export function extractPortraitColor(pixels, width, height) {
  const buckets = Array.from({ length: 24 }, () => ({ weight: 0, r: 0, g: 0, b: 0 }));
  for (let i = 0; i < pixels.length; i += 4) {
    const [r, g, b, a] = pixels.subarray(i, i + 4);
    if (a < 192) continue;
    const color = rgbToHsl(r, g, b);
    if (color.s < 0.22 || color.l < 0.12 || color.l > 0.88) continue;
    const y = Math.floor(i / 4 / width) / height;
    const weight = color.s * color.s * (a / 255) * (y >= 0.45 ? 2 : 0.5);
    const bucket = buckets[Math.floor(color.h / 15)];
    bucket.weight += weight;
    bucket.r += r * weight; bucket.g += g * weight; bucket.b += b * weight;
  }
  let best = -1, score = 0;
  for (let i = 0; i < buckets.length; i++) {
    const total = buckets[(i + 23) % 24].weight + buckets[i].weight + buckets[(i + 1) % 24].weight;
    if (total > score) { best = i; score = total; }
  }
  if (best < 0) return null;
  const cluster = [buckets[(best + 23) % 24], buckets[best], buckets[(best + 1) % 24]];
  const rgb = ['r', 'g', 'b'].map(channel => Math.round(cluster.reduce((sum, bucket) => sum + bucket[channel], 0) / score));
  return { ...rgbToHsl(...rgb), hex: '#' + rgb.map(n => n.toString(16).padStart(2, '0')).join('') };
}

// 대표색의 색상 계열로 배너 전체를 구성합니다. 어두운 면·밝은 원형 배경·텍스트 대비를 분리합니다.
export function createPortraitPalette(color) {
  if (!color) return null;
  const hue = Math.round(color.h);
  const saturation = Math.round(Math.max(20, Math.min(38, color.s * 45)));
  const bannerSaturation = Math.round(Math.max(28, Math.min(44, color.s * 55)));
  return {
    source: color.hex,
    background: `hsl(${hue} ${bannerSaturation}% 18%)`,
    border: `hsl(${hue} ${Math.round(bannerSaturation * 0.75)}% 32%)`,
    text: `hsl(${hue} 28% 96%)`,
    muted: `hsl(${hue} 18% 83%)`,
    accent: `hsl(${hue} 46% 83%)`,
    hover: `hsl(${hue} 46% 90%)`,
    light: `hsl(${hue} ${saturation}% 85%)`,
    shade: `hsl(${hue} ${saturation}% 68%)`,
    ring: `hsl(${hue} ${Math.round(saturation * 0.7)}% 71%)`,
    glow: `hsl(${hue} ${bannerSaturation}% 35% / 0.45)`,
    shadow: `hsl(${hue} ${bannerSaturation}% 6% / 0.4)`,
  };
}
