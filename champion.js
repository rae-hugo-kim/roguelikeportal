const championCoreReady = import('./champion-core.mjs');
const characterLabelsReady = fetch('character-labels.json').then(response => {
  if (!response.ok) throw new Error('Character labels unavailable');
  return response.json();
}).catch(() => ({}));
const hero = document.querySelector('.champion-hero');
let portrait = document.getElementById('champion-portrait');
const portraitStatus = document.getElementById('portrait-status');
const paletteKeys = ['light', 'shade', 'ring', 'glow', 'background', 'border', 'text', 'muted', 'accent', 'hover', 'shadow'];
const setChampionText = (id, value) => { document.getElementById(id).textContent = value; };
let portraitRequest = 0;

function resetPortraitPalette() {
  paletteKeys.forEach(key => hero.style.removeProperty(`--portrait-${key}`));
}

function showPortraitFailure(request) {
  if (request !== portraitRequest) return;
  portrait.hidden = true;
  portraitStatus.hidden = false;
  portraitStatus.textContent = '공식 이미지를 불러오지 못했어요. 우승 기록은 아래에서 확인해 주세요.';
  resetPortraitPalette();
  hero.dataset.paletteState = 'image-error';
}

async function renderChampionCharacter(winner) {
  const request = ++portraitRequest;
  resetPortraitPalette();
  hero.dataset.paletteState = 'loading';
  hero.dataset.cardId = '';
  portrait.hidden = true;
  portrait.removeAttribute('src');
  portraitStatus.hidden = false;
  portraitStatus.textContent = '공식 이미지를 불러오고 있어요…';
  setChampionText('winner-uma', winner.uma || '우승 말딸이 기록되지 않았어요.');
  setChampionText('winner-title', '');
  const [core, labels] = await Promise.all([championCoreReady, characterLabelsReady]);
  if (request !== portraitRequest) return;
  const character = core.matchChampionCharacter(winner, characters, labels);
  if (!character) {
    hero.dataset.paletteState = 'unmatched';
    portraitStatus.textContent = '이 기록의 의상 이미지를 아직 확인하지 못했어요.';
    setChampionText('portrait-caption', '다른 의상 이미지를 임의로 표시하지 않습니다.');
    return;
  }
  const label = labels[character.id];
  hero.dataset.cardId = character.id;
  setChampionText('winner-uma', label?.name || character.name);
  setChampionText('winner-title', label?.title.replace(/^\[|\]$/g, '') || '기록에 저장된 이름으로 표시하고 있어요.');
  setChampionText('portrait-caption', '공식 이미지 · © Cygames');

  const image = new Image(512, 512);
  image.crossOrigin = 'anonymous';
  image.decoding = 'async';
  image.fetchPriority = 'high';
  image.id = 'champion-portrait';
  image.alt = `${label ? label.name + ' ' + label.title : character.name}의 게임 공식 캐릭터 이미지`;
  image.src = `${IMG_BASE}characters/${encodeURIComponent(character.file)}.png`;
  try {
    await image.decode();
  } catch {
    showPortraitFailure(request);
    return;
  }
  if (request !== portraitRequest) return;
  let palette = null;
  try {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 64;
    const context = canvas.getContext('2d', { willReadFrequently: true });
    context.drawImage(image, 0, 0, 64, 64);
    palette = core.createPortraitPalette(core.extractPortraitColor(context.getImageData(0, 0, 64, 64).data, 64, 64));
  } catch {
    // 이미지 색을 읽을 수 없더라도 공식 이미지는 유지하고 기본 배경을 사용합니다.
  }
  if (palette) {
    paletteKeys.forEach(key => hero.style.setProperty(`--portrait-${key}`, palette[key]));
    hero.dataset.paletteState = 'extracted';
  } else {
    hero.dataset.paletteState = 'fallback';
    setChampionText('portrait-caption', '공식 이미지 · 기본 배경 · © Cygames');
  }
  image.addEventListener('error', () => showPortraitFailure(request), { once: true });
  portrait.replaceWith(image);
  portrait = image;
  portraitStatus.hidden = true;
}

async function initializeChampion() {
  const core = await championCoreReady;
  const selection = core.selectLatestChampion(DATA);
  setChampionText('record-count-note', `${DATA.length}개 회차의 기록을 담았습니다.`);
  if (!selection) {
    setChampionText('winner-name', '첫 우승자를 기다립니다.');
    setChampionText('winner-honorific', '');
    setChampionText('champion-heading', '아직 결승 결과가 등록되지 않았어요.');
    document.querySelector('.hero-actions').hidden = true;
    document.querySelector('.champion-seal').hidden = true;
    document.querySelector('.hero-art').hidden = true;
    document.querySelector('.race-context').hidden = true;
    return;
  }
  const { round, winner } = selection;
  setChampionText('winner-name', winner.player);
  setChampionText('champion-round', `${round.round}회 우승`);
  setChampionText('champion-watermark', round.round);
  setChampionText('champion-course', [round.course, round.season, round.weather].filter(Boolean).join(' · '));
  const timestamp = round.timestamp || '';
  const date = new Date(timestamp.length === 10 ? `${timestamp}T12:00:00+09:00` : timestamp);
  if (!Number.isNaN(date.valueOf())) {
    setChampionText('champion-date', new Intl.DateTimeFormat('ko-KR', { year: 'numeric', month: 'long', day: 'numeric', timeZone: 'Asia/Seoul' }).format(date));
    document.getElementById('champion-date').dateTime = timestamp;
  } else {
    setChampionText('champion-date', '날짜가 기록되지 않았어요.');
  }
  document.getElementById('champion-record').href = `#round-${round.round}`;
  document.getElementById('champion-player').href = `#player/${encodeURIComponent(winner.player)}`;
  await renderChampionCharacter(winner);
}

for (const card of document.querySelectorAll('#tab-rounds .round-card')) {
  card.id = `round-${card.querySelector('.round-num').textContent.replace('#', '')}`;
}
function routePortalHash() {
  const hash = location.hash.slice(1);
  const record = /^round-(\d+)$/.exec(hash);
  if (record) {
    showTab('rounds');
    const card = document.getElementById(`round-${record[1]}`);
    if (card) {
      card.classList.add('open');
      card.tabIndex = -1;
      card.focus({ preventScroll: true });
      card.scrollIntoView({ block: 'start' });
    }
    history.replaceState(null, '', `#${hash}`);
  } else if (hash.startsWith('player/')) {
    let name;
    try { name = decodeURIComponent(hash.slice(7)); } catch { showTab('player'); return; }
    if (Object.hasOwn(playerStats, name)) showPlayer(name);
    else showTab('player');
  } else if (['overview', 'rounds', 'player', 'roulette', 'tracks'].includes(hash) || !hash) {
    showTab(hash || 'overview');
    if (!hash || hash === 'overview') window.scrollTo(0, 0);
  }
}
window.addEventListener('hashchange', routePortalHash);
routePortalHash();
initializeChampion().catch(() => {
  setChampionText('winner-name', '우승 기록을 불러오지 못했어요.');
  setChampionText('winner-honorific', '');
  document.querySelector('.hero-art').hidden = true;
  document.querySelector('.hero-actions').hidden = true;
});
