import test from 'node:test';
import assert from 'node:assert/strict';
import { selectLatestChampion, matchChampionCharacter, extractPortraitColor, createPortraitPalette } from '../champion-core.mjs';

const registry = [
  { id: 100701, name: '골드쉽', file: '골드쉽' },
  { id: 100702, name: '골드쉽(수영복)', file: '골드쉽(수영복)' },
  { id: 100703, name: '골드쉽(Larc)', file: '골드쉽(Larc)' },
];
const labels = {
  100701: { name: '골드 쉽', title: '[레드 스트라이프]' },
  100702: { name: '골드 쉽', title: '[RUN! 럼블! 런처!!]' },
  100703: { name: '골드 쉽', title: '[La mode 564]' },
};
const rgba = rows => new Uint8ClampedArray(rows.flat());

test('an explicit costume ID takes precedence over an inconsistent record name', () => {
  assert.equal(matchChampionCharacter({ card_id: 100702, uma: '골드쉽' }, registry, labels).file, '골드쉽(수영복)');
});

test('an unknown explicit ID never falls back to a different costume with the same name', () => {
  assert.equal(matchChampionCharacter({ card_id: 999999, uma: '골드쉽' }, registry, labels), null);
});

test('costume names survive whitespace and Latin case normalization', () => {
  assert.equal(matchChampionCharacter({ uma: '골드 쉽 (larc)' }, registry, labels).id, 100703);
  assert.equal(matchChampionCharacter({ uma: '골드쉽 (수영복)' }, registry, labels).id, 100702);
});

test('a full official title resolves to its costume even when the registry uses a nickname', () => {
  assert.equal(matchChampionCharacter({ uma: '골드 쉽 [La mode 564]' }, registry, labels).id, 100703);
});

test('a base name is not matched by substring to a costume, and unknown nicknames remain unresolved', () => {
  assert.equal(matchChampionCharacter({ uma: '골드쉽' }, registry, labels).id, 100701);
  assert.equal(matchChampionCharacter({ uma: '골드쉽(미확인 의상)' }, registry, labels), null);
  assert.equal(matchChampionCharacter({ uma: '고루시' }, registry, labels), null);
});

test('ambiguous normalized names do not choose the first image', () => {
  const duplicate = [...registry, { id: 100799, name: '골드 쉽' }];
  assert.equal(matchChampionCharacter({ uma: '골드쉽' }, duplicate, labels), null);
});

test('the latest completed round wins regardless of array order or rank order', () => {
  const records = [
    { round: 10, finalsUma: [{ rank: 2, player: 'runner-up' }, { rank: 1, player: 'winner' }] },
    { round: 11, finalsUma: [] },
    { round: 8, finals: [{ rank: 1, player: 'earlier winner' }] },
  ];
  assert.equal(selectLatestChampion(records).round.round, 10);
  assert.equal(selectLatestChampion(records).winner.player, 'winner');
  assert.equal(selectLatestChampion([{ round: 12, finals: [] }]), null);
});

test('transparent pixels, white costume areas and black outlines do not drown out red accents', () => {
  const pixels = rgba([
    [0, 255, 0, 0], [0, 255, 0, 0], [0, 255, 0, 0], [0, 255, 0, 0],
    [255, 255, 255, 255], [255, 255, 255, 255], [0, 0, 0, 255], [0, 0, 0, 255],
    [210, 35, 60, 255], [210, 35, 60, 255], [255, 255, 255, 255], [0, 0, 0, 255],
  ]);
  const color = extractPortraitColor(pixels, 4, 3);
  assert.ok(color.h > 340 || color.h < 20);
});

test('red pixels on both sides of the hue boundary are counted together', () => {
  const redA = [240, 25, 45, 255], redB = [240, 45, 25, 255], blue = [25, 25, 240, 255];
  const color = extractPortraitColor(rgba([redA, redA, blue, blue, redB, redB, blue]), 7, 1);
  assert.ok(color.h > 345 || color.h < 15);
});

test('equally saturated lower-half costume color has priority over upper-half hair color', () => {
  const pixels = rgba([[200, 30, 30, 255], [200, 30, 30, 255], [30, 70, 200, 255], [30, 70, 200, 255]]);
  const color = extractPortraitColor(pixels, 1, 4);
  assert.ok(color.h > 220 && color.h < 240);
});

test('grayscale and transparent-only images explicitly use the default palette', () => {
  assert.equal(extractPortraitColor(rgba([[0, 0, 0, 0], [128, 128, 128, 255], [255, 255, 255, 255]]), 3, 1), null);
  assert.equal(createPortraitPalette(null), null);
});

// Convert CSS HSL to sRGB to check rendered foreground/background WCAG contrast.
function cssRgba(value) {
  const [hue, saturation, lightness, alpha = 1] = value.match(/[\d.]+/g).map(Number);
  const h = (hue % 360) / 60, s = saturation / 100, l = lightness / 100;
  const c = (1 - Math.abs(2 * l - 1)) * s, x = c * (1 - Math.abs(h % 2 - 1));
  const sectors = [[c, x, 0], [x, c, 0], [0, c, x], [0, x, c], [x, 0, c], [c, 0, x]];
  return [...sectors[Math.floor(h)].map(channel => channel + l - c / 2), alpha];
}

function contrast(first, second) {
  const luminance = color => color.slice(0, 3).reduce((sum, channel, i) => {
    const linear = channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
    return sum + linear * [0.2126, 0.7152, 0.0722][i];
  }, 0);
  const a = luminance(first), b = luminance(second);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

test('the entire banner follows red, green and blue images instead of retaining a fixed green background', () => {
  const samples = [[240, 30, 30, 255], [30, 200, 30, 255], [30, 30, 240, 255]];
  samples.forEach((pixel, channel) => {
    const palette = createPortraitPalette(extractPortraitColor(rgba([pixel]), 1, 1));
    const background = cssRgba(palette.background);
    assert.ok(background[channel] > background[(channel + 1) % 3]);
    assert.ok(background[channel] > background[(channel + 2) % 3]);
  });
});

test('banner text and buttons retain WCAG AA contrast throughout the hue range, including the glow', () => {
  for (let hue = 0; hue < 360; hue += 5) {
    for (const saturation of [0.23, 0.55, 1]) {
      const palette = createPortraitPalette({ h: hue, s: saturation, l: 0.5, hex: '#808080' });
      const background = cssRgba(palette.background), glow = cssRgba(palette.glow);
      for (const strength of [0, 0.5, 1]) {
        const alpha = glow[3] * strength;
        const surface = background.slice(0, 3).map((channel, i) => channel * (1 - alpha) + glow[i] * alpha);
        for (const role of ['text', 'muted', 'accent', 'hover']) {
          assert.ok(contrast(cssRgba(palette[role]), surface) >= 4.5, `hue=${hue}, saturation=${saturation}, glow=${strength}, role=${role}`);
        }
      }
      assert.ok(contrast(background, cssRgba(palette.accent)) >= 4.5);
      assert.ok(contrast(background, cssRgba(palette.hover)) >= 4.5);
    }
  }
});
