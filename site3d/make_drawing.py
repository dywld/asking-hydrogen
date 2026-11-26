#!/usr/bin/env python3
"""시연용 예시 배치도 PDF 를 만든다(가상 설계, 실제 충전소 도면 아님).

  python site3d/make_drawing.py
  -> cf/public_extra/site/예시_배치도.pdf, 문서/에이전트_시안/예시_배치도.pdf

좌표: 부지 중심 (0,0), x 오른쪽(+), y 위쪽(+), 단위 m. 아래쪽(-y)이 도로(천호대로) 쪽.
일부러 넣은 문제 1개: 튜브트레일러(저장설비)와 충전기2 사이 약 4.4m, 그 사이 방호벽 없음
(고압가스법 시행규칙 별표 5 제2호: 8m 이상 또는 방호벽).
"""
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parent.parent
plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False

SITE_W, SITE_D = 50, 40
EQUIP = [  # 이름, 종류, 중심 x, y, 가로, 세로
    ('관리동', 'building', -15, 10, 12, 10),
    ('압축기', 'process', 6, 9, 6, 4),
    ('축압기', 'compressed', 14, 9, 4, 3),
    ('프리쿨러', 'process', -3, 9, 3, 2),
    ('튜브트레일러(저장설비)', 'storage', 8, -3, 12, 2.5),
    ('충전기1', 'charger', -6, -9, 1.2, 0.8),
    ('충전기2', 'charger', 2, -9, 1.2, 0.8),
]
WALLS = [((2, 6), (17, 6)), ((2, 6), (2, 12)), ((17, 6), (17, 12))]   # 방호벽(철근콘크리트, 높이 2m)


def main():
    fig = plt.figure(figsize=(16.54, 11.69))      # A3 가로
    ax = fig.add_axes([0.05, 0.08, 0.68, 0.84])
    ax.set_xlim(-SITE_W / 2 - 4, SITE_W / 2 + 4); ax.set_ylim(-SITE_D / 2 - 7, SITE_D / 2 + 4)
    ax.set_aspect('equal')
    for v in range(-25, 26, 5):
        ax.axvline(v, color='#d9dde3', lw=0.5, zorder=0)
        ax.text(v, SITE_D / 2 + 1.6, f'{v}', ha='center', fontsize=8, color='#667')
    for v in range(-20, 21, 5):
        ax.axhline(v, color='#d9dde3', lw=0.5, zorder=0)
        ax.text(-SITE_W / 2 - 2.2, v, f'{v}', va='center', ha='right', fontsize=8, color='#667')
    ax.add_patch(Rectangle((-SITE_W / 2, -SITE_D / 2), SITE_W, SITE_D, fill=False, lw=2.4, ls=(0, (8, 3, 2, 3)), color='#222'))
    ax.text(-SITE_W / 2, SITE_D / 2 + 0.4, '사업소 경계', fontsize=10, va='bottom')
    ax.annotate('', (-SITE_W / 2, -SITE_D / 2 - 2), (SITE_W / 2, -SITE_D / 2 - 2), arrowprops=dict(arrowstyle='<->', lw=1))
    ax.text(0, -SITE_D / 2 - 2.6, f'{SITE_W:.0f}.0 m', ha='center', va='top', fontsize=10)
    ax.annotate('', (SITE_W / 2 + 2, -SITE_D / 2), (SITE_W / 2 + 2, SITE_D / 2), arrowprops=dict(arrowstyle='<->', lw=1))
    ax.text(SITE_W / 2 + 2.6, 0, f'{SITE_D:.0f}.0 m', rotation=90, va='center', fontsize=10)
    ax.add_patch(Rectangle((-SITE_W / 2 - 4, -SITE_D / 2 - 7), SITE_W + 8, 3.2, color='#eceff3', zorder=0))
    ax.text(0, -SITE_D / 2 - 5.4, '도로 (천호대로) 방향', ha='center', va='center', fontsize=11, color='#555')
    col = {'building': '#f3f4f6', 'process': '#fde68a', 'compressed': '#fdba74', 'storage': '#93c5fd', 'charger': '#86efac'}
    for n, k, x, y, w, d in EQUIP:
        ax.add_patch(Rectangle((x - w / 2, y - d / 2), w, d, facecolor=col[k], edgecolor='#222', lw=1.3))
        small = w < 3
        ax.text(x, y + (d / 2 + 0.9 if small else 0.35), n, ha='center', va='center', fontsize=9.5 if small else 10.5, weight='bold')
        ax.text(x, y + (d / 2 + 2.1 if small else -0.9), f'{w:g}×{d:g} m', ha='center', va='center', fontsize=8, color='#444')
    for (x1, y1), (x2, y2) in WALLS:
        ax.plot([x1, x2], [y1, y2], color='#111', lw=5, solid_capstyle='butt')
    ax.text(9.5, 5.2, '방호벽 (철근콘크리트 H=2.0m, t=0.15m)', ha='center', fontsize=8.5)
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    # 표제란
    tb = fig.add_axes([0.75, 0.08, 0.22, 0.84]); tb.axis('off')
    rows = [('도면명', '배치도'), ('공사명', '수소충전소 신축 (저장식, 예시)'), ('위치', '서울 강동구 천호대로 일대'),
            ('축척', '1/200 (A3)'), ('좌표', '부지 중심 기준, 단위 m, 격자 5m'), ('도면번호', 'A-101'),
            ('작성', '시연용 가상 도면'), ('비고', '실제 충전소 도면이 아님')]
    tb.add_patch(Rectangle((0, 0), 1, 1, fill=False, lw=1.5, transform=tb.transAxes))
    for i, (k, v) in enumerate(rows):
        y = 0.95 - i * 0.06
        tb.text(0.05, y, k, fontsize=10, color='#555', transform=tb.transAxes)
        tb.text(0.32, y, v, fontsize=10.5, transform=tb.transAxes)
    tb.text(0.05, 0.40, '범례', fontsize=11, weight='bold', transform=tb.transAxes)
    for i, (k, lab) in enumerate([('process', '처리설비'), ('compressed', '압축가스설비'), ('storage', '저장설비'),
                                   ('charger', '충전설비'), ('building', '건축물')]):
        y = 0.35 - i * 0.045
        tb.add_patch(Rectangle((0.05, y - 0.012), 0.08, 0.025, facecolor=col[k], edgecolor='#222', transform=tb.transAxes))
        tb.text(0.17, y, lab, va='center', fontsize=10, transform=tb.transAxes)
    tb.plot([0.05, 0.13], [0.105, 0.105], color='#111', lw=5, transform=tb.transAxes)
    tb.text(0.17, 0.105, '방호벽', va='center', fontsize=10, transform=tb.transAxes)
    for dst in [ROOT / 'cf/public_extra/site/예시_배치도.pdf', ROOT / '문서/에이전트_시안/예시_배치도.pdf']:
        dst.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(dst)
    fig.savefig(ROOT / '문서/에이전트_시안/예시_배치도.png', dpi=80)
    print('ok')


if __name__ == '__main__':
    main()
