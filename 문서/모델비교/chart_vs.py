import json, sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False
D = 'C:/Users/Lenovo/AppData/Local/Temp/claude/03001d3845169707/5e8a68e1-b3f4-4a59-9038-276206d419ef/scratchpad'
SURF, CARD, INK, INK2, MUTE, GRID = '#f6f7f9', '#ffffff', '#0f172a', '#475569', '#94a3b8', '#e2e8f0'
ACC = '#2a78d6'          # 수소문 강조색
OTH = ['#9aa5b4', '#b4bcc8', '#cbd2db']   # 범용 AI 3종(회색 계열, 이름은 막대 아래 글자로 구분)

G = json.load(open(D + '/grades.json', encoding='utf-8'))
ours = {i: 3 for i in range(1, 31)}
ours.update({1: 2, 11: 2, 14: 2, 16: 2, 23: 2, 24: 0, 26: 2})
NAMES = ['수소문\n(우리 봇)', 'ChatGPT\nGPT-5.2', 'Claude\nSonnet 5.5', 'Gemini\n2.5 Flash']
KEYS = [None, 'gpt', 'claude', 'gemini']


def sc(k):
    if k is None: return {str(i): v for i, v in ours.items()}, [], []
    g = G[k]; return g['scores'], g.get('halluc', []), g.get('missing', [])


rows = []
for k in KEYS:
    s, h, miss = sc(k)
    got = sum(s.values()); n = len(s)
    total90 = got if n == 30 else round(got / (3 * n) * 90)
    cite = None
    rows.append({'s': s, 'h': len(h), 'miss': miss, 'total': total90, 'exact': n == 30})

CATS = [('절차', range(1, 9)), ('시설기준', range(9, 14)), ('운영', range(14, 17)), ('수수료', range(17, 21)),
        ('벌칙', range(21, 23)), ('최신성', range(23, 25)), ('서식', range(25, 28)), ('범위 밖·환각', range(28, 31))]


def cat_pct(r, qs):
    got = [r['s'][str(q)] for q in qs if str(q) in r['s']]
    return 100 * sum(got) / (3 * len(got)) if got else 0


def card(fig, x, y, w, h):
    fig.patches.append(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0,rounding_size=0.012', transform=fig.transFigure,
                                      facecolor=CARD, edgecolor=GRID, linewidth=1, zorder=-5))


def clean(ax):
    for s in ['top', 'right', 'left']: ax.spines[s].set_visible(False)
    ax.spines['bottom'].set_color(GRID); ax.tick_params(colors=INK2, length=0); ax.set_facecolor(CARD)


cols = [ACC] + OTH
fig = plt.figure(figsize=(12, 15), facecolor=SURF)
fig.text(0.05, 0.962, '수소문 vs 범용 AI 3종', fontsize=28, weight='bold', color=INK)
fig.text(0.05, 0.94, '수소시설 인허가 30문항 · 문항당 3점(정답 2 + 근거 1), 90점 만점 · 2026-11-19', fontsize=12, color=INK2)

# 핵심 숫자 카드 3개
r0 = rows[0]; best_other = max(rows[1:], key=lambda r: r['total'])
kp = [(f"{r0['total']}점", '수소문 총점', f"범용 AI 최고 {best_other['total']}점보다 +{r0['total'] - best_other['total']}"),
      (f"{round(cat_pct(r0, range(17, 21)))}%", '수수료 문항 정답률', '고시 원문 표를 그대로 찾아 답함'),
      (f"{r0['h']}건", '지어낸 수치·조문', f"GPT {rows[1]['h']}건 · Claude {rows[2]['h']}건 · Gemini {rows[3]['h']}건")]
for k, (big, lab, sub) in enumerate(kp):
    x = 0.05 + k * 0.305
    card(fig, x, 0.80, 0.285, 0.115)
    fig.text(x + 0.02, 0.87, big, fontsize=30, weight='bold', color=ACC)
    fig.text(x + 0.02, 0.845, lab, fontsize=12.5, weight='bold', color=INK)
    fig.text(x + 0.02, 0.822, sub, fontsize=10, color=INK2)

# 총점 막대
card(fig, 0.05, 0.47, 0.9, 0.31)
ax = fig.add_axes([0.09, 0.505, 0.84, 0.22]); clean(ax)
for i, r in enumerate(rows):
    ax.bar(i, r['total'], width=0.55, color=cols[i], edgecolor=CARD, linewidth=2, zorder=3)
    lab = f"{r['total']}점" + ('' if r['exact'] else '*')
    ax.text(i, r['total'] + 2, lab, ha='center', va='bottom', fontsize=17 if i == 0 else 14, weight='bold', color=ACC if i == 0 else INK)
ax.set_xticks(range(4)); ax.set_xticklabels(NAMES, fontsize=12, color=INK)
for t in ax.get_xticklabels()[:1]: t.set_weight('bold'); t.set_color(ACC)
ax.set_ylim(0, 100); ax.set_yticks([0, 30, 60, 90]); ax.yaxis.grid(True, color=GRID, lw=0.8, zorder=0)
fig.text(0.075, 0.75, '총점 (90점 만점)', fontsize=15, weight='bold', color=INK)

# 유형별 득점률(수소문 vs 범용 AI 평균 대신 각각)
card(fig, 0.05, 0.10, 0.9, 0.35)
ax3 = fig.add_axes([0.17, 0.13, 0.75, 0.27]); clean(ax3)
ax3.spines['bottom'].set_visible(False)
h = 0.19
for j, r in enumerate(rows):
    ys = [k + (j - 1.5) * (h + 0.015) for k in range(len(CATS))]
    ps = [cat_pct(r, qs) for _, qs in CATS]
    ax3.barh(ys, [max(p, 0.8) for p in ps], height=h, color=cols[j], edgecolor=CARD, linewidth=1.5, zorder=3)
    if j == 0:
        for y, p in zip(ys, ps): ax3.text(p + 1, y, f'{round(p)}%', va='center', fontsize=8.5, weight='bold', color=ACC)
ax3.set_yticks(range(len(CATS))); ax3.set_yticklabels([c for c, _ in CATS], fontsize=11.5, color=INK)
ax3.invert_yaxis(); ax3.set_xlim(0, 110); ax3.set_xticks([0, 50, 100]); ax3.set_xticklabels(['0%', '50%', '100%'])
ax3.xaxis.grid(True, color=GRID, lw=0.8, zorder=0)
fig.text(0.075, 0.42, '유형별 득점률', fontsize=15, weight='bold', color=INK)
hd = [plt.Rectangle((0, 0), 1, 1, color=c) for c in cols]
fig.legend(hd, [n.replace('\n', ' ') for n in NAMES], loc='upper right', bbox_to_anchor=(0.94, 0.428), frameon=False, ncol=4, fontsize=10)

notes = ['· 수소문: 법령·고시·KGS Code 원문 3만여 조각을 검색해 근거를 붙여 답하는 우리 서비스(현재 운영판).',
         '· 범용 AI: 질문만 그대로 입력(자료 없이 각 모델의 지식으로 답함). 같은 기준표로 채점.',
         '· 지어낸 수치·조문이 있으면 해당 문항 0점. 24번(2026 공고)은 네 곳 모두 자료가 없어 0점.']
miss = rows[3]['miss']
if miss:
    notes.append(f"* Gemini는 무료 사용량 한도로 {len(miss)}문항({', '.join(map(str, miss))}번) 답을 받지 못해 나머지 {30 - len(miss)}문항 득점률을 90점으로 환산.")
for k, t in enumerate(notes):
    fig.text(0.05, 0.075 - k * 0.019, t, fontsize=10, color=INK2)
fig.savefig(sys.argv[1], dpi=160, facecolor=SURF)
print([(n.split()[0], r['total'], r['h'], r['miss']) for n, r in zip(NAMES, rows)])
