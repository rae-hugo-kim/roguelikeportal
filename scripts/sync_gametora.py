#!/usr/bin/env python3
"""GameTora(한섭 기준) 데이터로 룰렛 풀과 경기장 데이터를 갱신한다.

명령:
  supports    index.html `const supportCards` 에 신규 SSR 서포트 카드 추가
  characters  index.html `const characters` 에 신규 육성마를 추가하고 character-labels.json 공식 명칭을 갱신합니다.
  tracks      racetrack-data.json 을 한섭 경기장 스냅샷으로 재생성하고, 룰렛 trackData 와의 차이를 보고

supports / characters 공통
- 식별: 각 항목의 `id` = GameTora support_id / card_id.
- 이름: 기본은 공식 명칭 "캐릭터명 [타이틀]". --alias 로 기존 스타일 "캐릭터명(별명)" 지정.
  별명 생략 시 서포트는 금딱(이벤트 획득 레어) 스킬명, 육성마는 기존 데이터에서 학습한 의상 별명(summer→수영복 등).
  후보가 없거나 여러 개면 목록을 출력하고 중단한다.
- added: 한섭 출시일(release_ko). 미출시면 GameTora 예측 출시일, 예측일이 이미 지났는데 미출시면 2099-12-31.
  added 가 오늘 이후(대기 중)인 기존 항목은 실제 출시일/새 예측일로, 공식 명칭이면 이름도 최신 한글 명칭으로 갱신한다.
- 이미지: --images-dir 에 GameTora 원본을 <file>.png 로 저장한다. 이미지가 없는 모든 항목을 매번 다시 시도한다.
  keiaaskim/uma-race-system 체크아웃의 images/support-cards, images/characters 를 가리키게 한다.

사용:
  python3 scripts/sync_gametora.py supports                  # 미리보기(변경 없음)
  python3 scripts/sync_gametora.py supports --apply --images-dir <uma-race-system>/images/support-cards
  python3 scripts/sync_gametora.py supports --apply --alias 30236 --alias 30245=예각일섬 --op 30236
  python3 scripts/sync_gametora.py characters --apply --images-dir <uma-race-system>/images/characters
  python3 scripts/sync_gametora.py tracks --apply
"""
import argparse
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import Counter

BASE = 'https://gametora.com'
UA = {'User-Agent': 'Mozilla/5.0 (roguelikeportal sync)'}
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
UNKNOWN_DATE = '2099-12-31'
STAT_PREFIX = {
    'speed': '스피드', 'stamina': '스태미너', 'power': '파워', 'guts': '근성',
    'intelligence': '지능', 'friend': '친구', 'group': '그룹',
}
# GameTora racetracks: statThresholds 1~5, inout 1~4 (GameTora 번들 코드 기준)
STAT_NAME = {1: '스피드', 2: '스태미너', 3: '파워', 4: '근성', 5: '지능'}
POSITION = {2: '안쪽', 3: '바깥쪽', 4: '바깥쪽→안쪽'}
PHASES = ('early', 'mid', 'late', 'spurt')


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read()


class GameTora:
    def __init__(self):
        self.manifest = json.loads(get(f'{BASE}/data/manifests/umamusume.json'))

    def dataset(self, key):
        return json.loads(get(f'{BASE}/data/umamusume/{key}.{self.manifest[key]}.json'))


def nospace(s):
    return re.sub(r'\s', '', s)


def read_const(src, var):
    m = re.search(r'(const %s = )([\[{].*?[\]}]);\n' % var, src)
    if not m:
        sys.exit(f'index.html 에서 const {var} 줄을 찾지 못했습니다.')
    return m, json.loads(m.group(2))


def write_const(path, src, m, value):
    line = m.group(1) + json.dumps(value, ensure_ascii=False, separators=(',', ':')) + ';\n'
    with open(path, 'w', encoding='utf-8') as f:
        f.write(src[:m.start()] + line + src[m.end():])


# ---------------------------------------------------------------- 풀(서포트/육성마)

class Supports:
    var, dataset, id_key, pred_key = 'supportCards', 'support-cards', 'support_id', 'support_cards'

    def __init__(self, gt, pool):
        self.skills = {s['id']: s for s in gt.dataset('skills')}

    @staticmethod
    def entries(pool):
        return [e for v in pool.values() for e in v]

    @staticmethod
    def append(pool, card, entry):
        pool[card['type']].append(entry)

    @staticmethod
    def eligible(card):
        return card['rarity'] == 3 and card['type'] in STAT_PREFIX

    @staticmethod
    def char_name(card):
        return card.get('name_ko') or card['name_jp']

    def official_name(self, card):
        return f"{self.char_name(card)} {card.get('title_ko') or card.get('title_ja') or ''}".strip()

    def file(self, card):
        return f"{STAT_PREFIX[card['type']]}_{nospace(self.char_name(card))}_{card['support_id']}"

    @staticmethod
    def image_url(card):
        return f"{BASE}/images/umamusume/supports/tex_support_card_{card['support_id']}.png"

    def alias_candidates(self, card):
        return [(self.skills[i].get('name_ko') or self.skills[i]['jpname'])
                for i in card.get('event_skills', []) if self.skills.get(i, {}).get('rarity') == 2]

    alias_label = '금딱'


class Characters:
    var, dataset, id_key, pred_key = 'characters', 'character-cards', 'card_id', 'char_cards'
    alias_label = '의상 별명'

    def __init__(self, gt, pool):
        # 기존 데이터에서 version → 별명 학습 (예: summer → 수영복). 기본 의상(version 없음)은 별명 없음.
        cards = {c['card_id']: c for c in gt.dataset(self.dataset)}
        self.version_alias = {}
        for e in pool:
            m = re.match(r'.*\((.*)\)$', e['name'])
            if m and e['id'] in cards:
                self.version_alias.setdefault(cards[e['id']].get('version'), set()).add(m.group(1))

    @staticmethod
    def entries(pool):
        return pool

    @staticmethod
    def append(pool, card, entry):
        pool.append(entry)

    @staticmethod
    def eligible(card):
        return True

    @staticmethod
    def char_name(card):
        return card.get('name_ko') or card['name_jp']

    def official_name(self, card):
        return f"{self.char_name(card)} {card.get('title_ko') or card.get('title_jp') or ''}".strip()

    def file(self, card):
        # '_' 가 들어가면 loadCardImage 가 서포트 카드 경로로 오인하므로 '-' 를 쓴다.
        return f"{nospace(self.char_name(card))}-{card['card_id']}"

    @staticmethod
    def image_url(card):
        return f"{BASE}/images/umamusume/characters/chara_stand_{card['char_id']}_{card['card_id']}.png"

    def alias_candidates(self, card):
        version = card.get('version')
        if version is None:
            return ['']  # 기본 의상: 캐릭터명만
        return sorted(self.version_alias.get(version, ()))


def added_date(card, predicted, today, id_key):
    if card.get('release_ko'):
        return card['release_ko']
    pred = predicted.get(str(card[id_key]), {}).get('release_date')
    return pred if pred and pred > today else UNKNOWN_DATE


def sync_pool(args, kind_cls):
    aliases = {}
    for a in args.alias:
        sid, _, name = a.partition('=')
        aliases[int(sid)] = name or None

    gt = GameTora()
    src = open(args.index, encoding='utf-8').read()
    m, pool = read_const(src, kind_cls.var)
    kind = kind_cls(gt, pool)
    cards = gt.dataset(kind.dataset)
    predicted = gt.dataset('ko/foresight/predicted_releases')[kind.pred_key]
    by_id = {c[kind.id_key]: c for c in cards}

    entries = kind.entries(pool)
    missing_id = [e['name'] for e in entries if 'id' not in e]
    if missing_id:
        sys.exit(f'id 가 없는 기존 항목이 있습니다: {missing_id}')
    existing = {e['id']: e for e in entries}

    # 1) 대기 중(added > today)인 기존 항목의 출시일·공식 명칭 갱신
    updated = []
    for sid, e in existing.items():
        if e['added'] <= args.today or sid not in by_id:
            continue
        new = added_date(by_id[sid], predicted, args.today, kind.id_key)
        name = kind.official_name(by_id[sid]) if ' [' in e['name'] else e['name']
        if new != e['added'] or name != e['name']:
            updated.append((e['name'], f"{e['added']} → {new}", name))
            e['added'], e['name'] = new, name

    # 2) 신규 항목 추가
    errors, added, seen = [], [], set()
    for c in sorted(cards, key=lambda c: c[kind.id_key]):
        sid = c[kind.id_key]
        if sid in existing or not kind.eligible(c):
            continue
        seen.add(sid)
        if sid in aliases:
            alias = aliases[sid]
            if alias is None:
                cands = kind.alias_candidates(c)
                if len(cands) != 1:
                    errors.append(f'{sid} {kind.official_name(c)}: {kind.alias_label} 후보 {len(cands)}개 {cands} → --alias {sid}=<별명> 으로 지정하세요')
                    continue
                alias = cands[0]
            base = nospace(kind.char_name(c))
            name = f'{base}({nospace(alias)})' if alias else base
        else:
            name = kind.official_name(c)
        entry = {'name': name, 'file': kind.file(c)}
        if sid in args.op:
            entry['isOp'] = True
        entry['id'] = sid
        entry['added'] = added_date(c, predicted, args.today, kind.id_key)
        kind.append(pool, c, entry)
        added.append(entry)

    unknown = (set(aliases) | set(args.op)) - seen
    if unknown:
        errors.append(f'--alias/--op 대상이 이번 신규 항목이 아닙니다: {sorted(unknown)}')
    if args.op and kind_cls is not Supports:
        errors.append('--op 은 supports 에서만 쓸 수 있습니다.')

    for e in added:
        c = by_id[e['id']]
        state = '대기' if e['added'] > args.today else '출시'
        group = f"[{c['type']:12}] " if kind_cls is Supports else ''
        cands = kind.alias_candidates(c)
        print(f"+ {group}{e['id']} {e['added']} {state}  {e['name']}  ({kind.alias_label}: {', '.join(x or '(기본)' for x in cands) or '-'}){'  [OP]' if e.get('isOp') else ''}")
    for old_name, dates, name in updated:
        print(f"~ {old_name}: added {dates}{'' if name == old_name else f', 이름 → {name}'}")
    print(f'신규 {len(added)}개 (대기 {sum(1 for e in added if e["added"] > args.today)}개), 대기 항목 갱신 {len(updated)}개')
    if errors:
        print('\n'.join('! ' + e for e in errors), file=sys.stderr)
        sys.exit(1)
    if not args.apply:
        print('미리보기입니다. 반영하려면 --apply 를 붙이세요.')
        return

    if args.images_dir:
        os.makedirs(args.images_dir, exist_ok=True)
        saved, unavailable = 0, []
        for e in kind.entries(pool):
            path = os.path.join(args.images_dir, e['file'] + '.png')
            if os.path.exists(path) or e['id'] not in by_id:
                continue
            try:
                data = get(kind.image_url(by_id[e['id']]))
            except urllib.error.HTTPError as err:
                if err.code != 404:
                    raise
                unavailable.append(e)
                continue
            with open(path, 'wb') as f:
                f.write(data)
            saved += 1
        print(f'이미지 {saved}장 저장 → {args.images_dir}')
        for e in unavailable:
            state = '대기' if e['added'] > args.today else '출시됨!'
            print(f"  원본 이미지 없음({state}): {e['id']} {e['name']} — 나중에 다시 실행하세요", file=sys.stderr)
    elif added:
        print('경고: --images-dir 없이 반영했습니다. 신규 이미지는 따로 올려야 합니다.', file=sys.stderr)

    write_const(args.index, src, m, pool)
    if kind_cls is Characters:
        registered_ids = {entry['id'] for entry in kind.entries(pool)}
        labels = {
            str(card['card_id']): {
                'name': kind.char_name(card),
                'title': card.get('title_ko') or card.get('title_jp') or '',
                'source': f"{BASE}/ko/umamusume/characters/{card['url_name']}",
            }
            for card in cards if card['card_id'] in registered_ids
        }
        labels_path = os.path.join(os.path.dirname(os.path.abspath(args.index)), 'character-labels.json')
        with open(labels_path, 'w', encoding='utf-8') as f:
            json.dump(labels, f, ensure_ascii=False, indent=2)
        print(f'{labels_path} 공식 명칭 {len(labels)}개를 갱신했습니다.')
    print(f'{args.index} 반영 완료')


# ---------------------------------------------------------------- 경기장

def kr_racetrack_prefix():
    """GameTora 경기장 페이지 코드에서 한섭(ko)이 쓰는 스냅샷 경로를 읽는다 (예: 'history/pre_santa_anita/')."""
    html = get(f'{BASE}/ko/umamusume/racetracks').decode('utf-8', 'ignore')
    page = re.search(r'src="(/_next/static/chunks/pages/ko/umamusume/racetracks-[^"]+\.js)"', html)
    if not page:
        sys.exit('GameTora 경기장 페이지 스크립트를 찾지 못했습니다. --snapshot 으로 지정하세요.')
    js = get(BASE + page.group(1)).decode('utf-8', 'ignore')
    m = re.search(r'"ko"==(\w+)\|\|"zh_tw"==\1\?"([^"]*)"', js)
    if not m:
        sys.exit('한섭 경기장 스냅샷 경로를 찾지 못했습니다. --snapshot 으로 지정하세요.')
    return m.group(2)


def build_course(track_id, c, image_prefix):
    course = {'distance': c['length'], 'surface': '잔디' if c['terrain'] == 1 else '더트'}
    if c['inout'] in POSITION:
        course['position'] = POSITION[c['inout']]
    course['phases'] = {k: {'start': p['start'], 'end': p['end']} for k, p in zip(PHASES, c['phases'])}
    course['corners'] = [{'number': x['number'], 'start': x['start'], 'end': x['end']} for x in c['corners']]
    course['straights'] = [{'number': i + 1, 'start': x['start'], 'end': x['end']} for i, x in enumerate(c['straights'])]
    course['positionKeep'] = {'start': 0, 'end': c['positionKeepEnd']}
    course['spurtStart'] = c['spurtStart']['meters'] if c.get('spurtStart') else None
    course['statBonus'] = ', '.join(STAT_NAME[s] for s in c['statThresholds']) or '없음'
    course['imageUrl'] = f"https://media.gametora.com/umamusume/racetrack/{image_prefix}full/ko/{track_id}/{c['id']}.png"
    course['slopes'] = [{'start': x['start'], 'length': x['end'] - x['start'], 'end': x['end'],
                         'type': 'uphill' if x['slope'] > 0 else 'downhill'} for x in c['slopes']]
    return course


def sync_tracks(args):
    gt = GameTora()
    prefix = args.snapshot if args.snapshot is not None else kr_racetrack_prefix()
    tracks = gt.dataset(f'{prefix}racetracks')
    info = {str(x['id']): x for x in gt.dataset('racetracks_extended')}

    # 기존 venue 표시명/ID 는 유지한다 (회차 기록의 코스 문자열과 대조에 쓰인다).
    old = json.load(open(args.tracks, encoding='utf-8'))
    old_names = {}
    for v in old['venues']:
        tid = v['courses'][0]['imageUrl'].rsplit('/', 2)[1]
        old_names[tid] = (v['venue'], v['venueId'])

    venues = []
    for t in tracks:
        name, vid = old_names.get(t['id']) or (info[t['id']]['name_ko'], nospace(info[t['id']]['name_en'].lower().replace(' ', '_')))
        venues.append({'venue': name, 'venueId': vid,
                       'courses': [build_course(t['id'], c, prefix) for c in t['courses']]})
    new = {'venues': venues, 'source': f'gametora:{prefix}racetracks',
           'crawledAt': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'), 'errors': []}

    # 변경 요약 (course 이미지 ID 기준)
    def index(d):
        return {c['imageUrl'].rsplit('/', 1)[1]: (v['venue'], c) for v in d['venues'] for c in v['courses']}
    before, after = index(old), index(new)
    ignore = {'imageUrl'}
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = [(k, sorted(f for f in set(before[k][1]) | set(after[k][1]) if f not in ignore and before[k][1].get(f) != after[k][1].get(f)))
               for k in sorted(set(before) & set(after))]
    changed = [(k, f) for k, f in changed if f]
    print(f'한섭 스냅샷: {prefix or "(현재 일섭과 동일)"}racetracks — 경기장 {len(venues)}곳, 코스 {len(after)}개')
    for k in added:
        print(f'+ {after[k][0]} {after[k][1]["distance"]}m {after[k][1]["surface"]} ({k})')
    for k in removed:
        print(f'- {before[k][0]} {before[k][1]["distance"]}m {before[k][1]["surface"]} ({k})')
    print('~ 필드별 변경 코스 수:', dict(Counter(f for _, fs in changed for f in fs)) or '없음')

    # 룰렛 trackData 와 비교 (자동 수정하지 않음: 마장 복사 텍스트를 봇이 파싱한다)
    src = open(args.index, encoding='utf-8').read()
    td = re.search(r'const trackData = \{\s*tracks: \[(.*?)\n\s*\],', src, re.S)
    roulette = {}
    for n, s, ds, pos in re.findall(r"\{name:'([^']+)',type:'([^']+)',distances:\[([^\]]*)\],hasPosition:\w+(?:,position:'([^']+)')?\}", td.group(1)):
        for d in re.findall(r"'(\d+)m'", ds):
            roulette[(n.replace(' 경마장', ''), s, int(d), pos or None)] = True
    kr = {}
    for t in tracks:
        for c in t['courses']:
            kr[(info[t['id']]['name_ko'], '잔디' if c['terrain'] == 1 else '더트', c['length'], POSITION.get(c['inout']))] = True
    only_kr, only_roulette = sorted(set(kr) - set(roulette)), sorted(set(roulette) - set(kr))
    if only_kr or only_roulette:
        print('룰렛 trackData 와 한섭 코스 차이 (index.html 수동 확인 필요):')
        for x in only_kr:
            print(f'  한섭에만: {x[0]} {x[1]} {x[2]}m {x[3] or ""}')
        for x in only_roulette:
            print(f'  룰렛에만: {x[0]} {x[1]} {x[2]}m {x[3] or ""}')
    else:
        print('룰렛 trackData 는 한섭 코스와 일치합니다.')

    if not args.apply:
        print('미리보기입니다. 반영하려면 --apply 를 붙이세요.')
        return
    with open(args.tracks, 'w', encoding='utf-8') as f:
        json.dump(new, f, ensure_ascii=False, indent=2)
    print(f'{args.tracks} 반영 완료')


# ----------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('supports', 'characters'):
        p = sub.add_parser(name)
        p.add_argument('--alias', action='append', default=[], metavar='ID[=별명]',
                       help='신규 항목 이름을 "캐릭터명(별명)" 으로. 별명 생략 시 자동 후보(1개일 때만)')
        p.add_argument('--op', action='append', default=[], type=int, metavar='ID', help='(supports) 사기카드(isOp) 표시')
        p.add_argument('--images-dir', help='이미지를 <file>.png 로 저장할 디렉터리')
    t = sub.add_parser('tracks')
    t.add_argument('--tracks', default=os.path.join(ROOT, 'racetrack-data.json'))
    t.add_argument('--snapshot', help="GameTora 스냅샷 접두어 (예: 'history/pre_santa_anita/', 현재판은 ''). 기본: 자동 감지")
    for p in sub.choices.values():
        p.add_argument('--index', default=os.path.join(ROOT, 'index.html'))
        p.add_argument('--apply', action='store_true', help='파일에 반영 (없으면 미리보기)')
        p.add_argument('--today', default=datetime.date.today().isoformat(), help='기준일 (기본: 오늘)')
    args = ap.parse_args()
    if args.cmd == 'tracks':
        sync_tracks(args)
    else:
        sync_pool(args, Supports if args.cmd == 'supports' else Characters)


if __name__ == '__main__':
    main()
