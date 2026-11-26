"""팀 30문항 재채점 결과를 PPT 용 16:9 그림 4장으로 그린다.

  python 문서/모델비교/chart_ppt.py  ->  문서/모델비교/ppt/1_총점.png ... 4_한장요약.png
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import FancyBboxPatch  # 유형별 표의 둥근 칸

HERE = Path(__file__).resolve().parent
plt.rcParams['font.family'] = 'Malgun Gothic'
G = json.loads((HERE / 'grades_30_20261124.json').read_text(encoding='utf-8'))
K = ['A', 'B', 'E', 'C']
NM = ['수소문 (우리 봇)', 'Claude Opus 5.5', 'Gemini 4 Hydrogen', 'GPT-6 luna']
T90 = [sum(G['scores'][k].values()) for k in K]
T = [round(t * 100 / 90) for t in T90]   # 90점 만점(30문항 x 3점)을 100점 만점으로 환산, 정수 반올림
H = [len(G['halluc'][k]) for k in K]
BG, INK, SUB, MUTE, GRID = '#ffffff', '#0b0b0b', '#52514e', '#8a8984', '#e7e6e2'
BLUE, GRAY = '#2a78d6', '#cfcec8'
OUT = HERE / 'ppt'
OUT.mkdir(exist_ok=True)
FOOT = '팀 30문항, 문항당 0~3점(90점)을 100점 만점으로 환산, 법령 원문과 대조해 채점 · 범용 AI는 검색 없이 질문만 · Gemini 4 Hydrogen 은 생각 단계 Low · 2026-11-24'


def slide(title, sub):
    fig = plt.figure(figsize=(12, 6.75), dpi=160)
    fig.patch.set_facecolor(BG)
    fig.text(.06, .875, title, fontsize=27, weight='bold', color=INK)
    fig.text(.06, .815, sub, fontsize=14.5, color=SUB)
    fig.text(.06, .04, FOOT, fontsize=9.5, color=MUTE)
    return fig


def hbars(ax, vals, vmax, fmt, labels, big=22):
    n = len(vals)
    ax.set_xlim(0, vmax)
    ax.set_ylim(n - .4, -.6)
    for i, v in enumerate(vals):
        c = BLUE if i == 0 else GRAY
        ax.barh(i, v, height=.52, color=c, edgecolor='none')
        ax.text(v + vmax * .018, i, fmt(v), va='center', fontsize=big if i == 0 else big - 3,
                weight='bold', color=BLUE if i == 0 else SUB)
    ax.set_yticks(range(n), labels, fontsize=15, color=INK)
    ax.set_xticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0, pad=14)
    ax.get_yticklabels()[0].set_fontweight('bold')


# 1 총점
f = slide(f'정확도: 수소문 {T[0]}점, 범용 AI의 2배', '팀 30문항 총점 (100점 만점)')
ax = f.add_axes([.27, .13, .64, .6])
hbars(ax, T, 112, lambda v: f'{v}점', NM, 26)
ax.axvline(100, color=GRID, lw=1.5, ls=(0, (4, 4)), zorder=0)
ax.text(100, -.5, '만점 100', ha='center', fontsize=11, color=MUTE)
f.savefig(OUT / '1_총점.png')
plt.close(f)

# 2 환각
f = slide('틀린 내용을 맞다고 단정한 답: 수소문 0건', '30문항 중 없는 조문, 틀린 금액, 틀린 기관을 확신하며 답한 수')
ax = f.add_axes([.27, .13, .64, .6])
hbars(ax, H, 12, lambda v: f'{v}건', NM, 26)
f.savefig(OUT / '2_환각.png')
plt.close(f)

# 3 유형별 득점률
CATS = [('절차', range(1, 9)), ('시설기준', range(9, 14)), ('운영', range(14, 17)), ('수수료', range(17, 21)),
        ('벌칙', range(21, 23)), ('최신 정보', range(23, 25)), ('서식', range(25, 28)), ('범위 밖 질문', range(28, 31))]
pc = np.array([[100 * sum(G['scores'][k][str(i)] for i in r) / (3 * len(r)) for _, r in CATS] for k in K])
cm = LinearSegmentedColormap.from_list('b', ['#f3f7fc', '#c4daf4', '#7aabe8', '#2a78d6', '#184f94'])
f = slide('수수료와 벌칙은 수소문만 맞혔어요', '질문 유형별 득점률 (%)')
ax = f.add_axes([.22, .1, .73, .62])
for x in range(len(CATS)):
    for y in range(4):
        v = pc[y, x]
        ax.add_patch(FancyBboxPatch((x + .05, y + .07), .9, .86, boxstyle='round,pad=0,rounding_size=.08',
                                    fc=cm(v / 100), ec='none'))
        ax.text(x + .5, y + .5, f'{v:.0f}', ha='center', va='center', fontsize=16, weight='bold',
                color='white' if v >= 55 else INK)
ax.set_xlim(0, len(CATS))
ax.set_ylim(4, 0)
ax.set_xticks(np.arange(len(CATS)) + .5, [c for c, _ in CATS], fontsize=13.5, color=INK)
ax.set_yticks(np.arange(4) + .5, NM, fontsize=14.5, color=INK)
ax.get_yticklabels()[0].set_fontweight('bold')
ax.xaxis.tick_top()
ax.tick_params(length=0, pad=8)
for s in ax.spines.values():
    s.set_visible(False)
f.savefig(OUT / '3_유형별.png')
plt.close(f)

# 4 한 장 요약
f = slide('수소문 vs 범용 AI 3종', '팀 30문항 다시 채점 결과')
a1 = f.add_axes([.25, .14, .33, .56])
hbars(a1, T, 130, lambda v: f'{v}점', NM)
a1.set_title('총점 (100점 만점)', loc='left', fontsize=15, weight='bold', color=INK, pad=16)
a2 = f.add_axes([.68, .14, .26, .56])
hbars(a2, H, 14, lambda v: f'{v}건', [''] * 4)
a2.set_title('틀린 걸 단정한 답', loc='left', fontsize=15, weight='bold', color=INK, pad=16)
f.savefig(OUT / '4_한장요약.png')
plt.close(f)
print(T90, T, H)

# 5 네 장을 한 장에(2x2)
from PIL import Image, ImageDraw
tiles = [Image.open(OUT / n) for n in ('1_총점.png', '2_환각.png', '3_유형별.png', '4_한장요약.png')]
w, h = tiles[0].size
gap = 40
sheet = Image.new('RGB', (w * 2 + gap * 3, h * 2 + gap * 3), '#eef0f3')
for k, t in enumerate(tiles):
    x, y = gap + (k % 2) * (w + gap), gap + (k // 2) * (h + gap)
    sheet.paste(t, (x, y))
    ImageDraw.Draw(sheet).rectangle([x - 1, y - 1, x + w, y + h], outline='#d6d9de', width=2)
sheet.save(OUT / '5_네장한번에.png')

# 6 종합: 총점 + 환각 + 유형별 득점률을 한 장에
f = plt.figure(figsize=(12, 6.75), dpi=160)
f.patch.set_facecolor(BG)
f.text(.05, .9, '수소문, 범용 AI 3종보다 2배 정확하고 틀린 단정은 0건', fontsize=23, weight='bold', color=INK)
f.text(.05, .85, '팀 30문항 다시 채점 결과 종합', fontsize=13.5, color=SUB)
f.text(.05, .035, FOOT, fontsize=9, color=MUTE)
a1 = f.add_axes([.2, .47, .25, .3])
hbars(a1, T, 133, lambda v: f'{v}점', NM, 17)
a1.tick_params(labelsize=12)
a1.set_title('총점 (100점 만점)', loc='left', fontsize=13, weight='bold', color=INK, pad=10)
a2 = f.add_axes([.2, .09, .25, .3])
hbars(a2, H, 14, lambda v: f'{v}건', NM, 17)
a2.tick_params(labelsize=12)
a2.set_title('틀린 걸 단정한 답', loc='left', fontsize=13, weight='bold', color=INK, pad=10)
a3 = f.add_axes([.53, .09, .43, .68])
for x in range(len(CATS)):
    for y in range(4):
        v = pc[y, x]
        a3.add_patch(FancyBboxPatch((y + .05, x + .06), .9, .88, boxstyle='round,pad=0,rounding_size=.07',
                                    fc=cm(v / 100), ec='none'))
        a3.text(y + .5, x + .5, f'{v:.0f}', ha='center', va='center', fontsize=12.5, weight='bold',
                color='white' if v >= 55 else INK)
a3.set_xlim(0, 4)
a3.set_ylim(len(CATS), 0)
a3.set_yticks(np.arange(len(CATS)) + .5, [c for c, _ in CATS], fontsize=12, color=INK)
a3.set_xticks(np.arange(4) + .5, ['수소문', 'Opus 5.5', 'Gemini 4', 'GPT-6 luna'], fontsize=11.5, color=INK)
a3.get_xticklabels()[0].set_fontweight('bold')
a3.xaxis.tick_top()
a3.tick_params(length=0, pad=6)
for s in a3.spines.values():
    s.set_visible(False)
a3.set_title('질문 유형별 득점률 (%)', loc='left', fontsize=13, weight='bold', color=INK, pad=30)
f.savefig(OUT / '6_종합.png')
plt.close(f)
