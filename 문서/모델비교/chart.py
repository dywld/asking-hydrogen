import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import sys

plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False
SURF, INK, INK2, GRID = '#fcfcfb', '#0b0b0b', '#52514e', '#e4e3df'
M = ['ChatGPT\n(지금 서비스)', 'Claude\nOpus 5.5', 'Gemini\n(무료)']
C = ['#2a78d6', '#eb6834', '#1baf7a']
score = [81, 83, 78]
won = [8, 52, 0]
cats = ['절차', '시설기준', '운영', '수수료', '벌칙', '최신성', '서식', '범위 밖·환각']
full = [24, 15, 9, 12, 6, 6, 9, 9]
byc = {0: [23, 14, 7, 12, 6, 2, 8, 9], 1: [24, 14, 7, 12, 6, 2, 9, 9], 2: [24, 12, 5, 12, 6, 2, 8, 9]}


def rbar(ax, x, h, w, color, horiz=False):
    # 데이터 끝만 둥글게(4px 느낌), 기준선 쪽은 각지게
    if horiz:
        ax.barh(x, h, height=w, color=color, edgecolor=SURF, linewidth=2)
    else:
        ax.bar(x, h, width=w, color=color, edgecolor=SURF, linewidth=2)


def clean(ax):
    for s in ['top', 'right', 'left']:
        ax.spines[s].set_visible(False)
    ax.spines['bottom'].set_color(GRID)
    ax.tick_params(colors=INK2, length=0)
    ax.set_facecolor(SURF)


fig = plt.figure(figsize=(12, 13), facecolor=SURF)
fig.text(0.05, 0.965, '수소 인허가 챗봇 · AI 모델 3종 비교', fontsize=22, weight='bold', color=INK)
fig.text(0.05, 0.94, '팀 30문항(문항당 3점, 90점 만점) · 같은 검색 근거를 넣고 같은 기준으로 채점 · 2026-11-18',
         fontsize=11.5, color=INK2)

# 1) 총점
ax1 = fig.add_axes([0.07, 0.62, 0.40, 0.27]); clean(ax1)
for i in range(3):
    rbar(ax1, i, score[i], 0.56, C[i])
    ax1.text(i, score[i] + 1.2, f'{score[i]}점', ha='center', va='bottom', fontsize=15, weight='bold', color=INK)
ax1.set_xticks(range(3)); ax1.set_xticklabels(M, fontsize=11, color=INK)
ax1.set_ylim(0, 90); ax1.set_yticks([0, 30, 60, 90]); ax1.yaxis.grid(True, color=GRID, lw=0.8); ax1.set_axisbelow(True)
ax1.set_title('총점 (90점 만점)', loc='left', fontsize=14, weight='bold', color=INK, pad=12)

# 2) 질문 1개 비용
ax2 = fig.add_axes([0.56, 0.62, 0.40, 0.27]); clean(ax2)
for i in range(3):
    rbar(ax2, i, max(won[i], 0.4), 0.56, C[i])
    ax2.text(i, won[i] + 1.5, '0원' if won[i] == 0 else f'약 {won[i]}원', ha='center', va='bottom', fontsize=15, weight='bold', color=INK)
ax2.set_xticks(range(3)); ax2.set_xticklabels(M, fontsize=11, color=INK)
ax2.set_ylim(0, 60); ax2.set_yticks([0, 20, 40, 60]); ax2.yaxis.grid(True, color=GRID, lw=0.8); ax2.set_axisbelow(True)
ax2.set_title('질문 1개당 비용 (원)', loc='left', fontsize=14, weight='bold', color=INK, pad=12)

# 3) 유형별 득점률
ax3 = fig.add_axes([0.15, 0.185, 0.81, 0.36]); clean(ax3)
ax3.spines['bottom'].set_visible(False); ax3.spines['left'].set_visible(True); ax3.spines['left'].set_color(GRID)
h = 0.26
for j in range(3):
    ys = [k + (j - 1) * (h + 0.02) for k in range(len(cats))]
    pct = [byc[j][k] / full[k] * 100 for k in range(len(cats))]
    rbar(ax3, ys, pct, h, C[j], horiz=True)
    for y, p, k in zip(ys, pct, range(len(cats))):
        ax3.text(p + 1, y, f'{byc[j][k]}/{full[k]}', va='center', fontsize=8.5, color=INK2)
ax3.set_yticks(range(len(cats))); ax3.set_yticklabels(cats, fontsize=11.5, color=INK)
ax3.invert_yaxis(); ax3.set_xlim(0, 112); ax3.set_xticks([0, 25, 50, 75, 100]); ax3.set_xticklabels(['0%', '25%', '50%', '75%', '100%'])
ax3.xaxis.grid(True, color=GRID, lw=0.8); ax3.set_axisbelow(True)
ax3.set_title('유형별 득점률 (막대 끝 숫자 = 얻은 점수 / 만점)', loc='left', fontsize=14, weight='bold', color=INK, pad=12)
handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in C]
ax3.legend(handles, [m.replace('\n', ' ') for m in M], loc='upper right', frameon=False, fontsize=10.5, ncol=3,
           bbox_to_anchor=(1.0, -0.04))

notes = [
    '결론: ChatGPT와 Claude는 정확도가 비슷하고(2점 차), Claude가 질문당 약 6배 비쌉니다. 지금처럼 ChatGPT 유지를 권장합니다.',
    '· 셋 다 틀린 곳: 24번(2026 산업통상부 공고 자료 없음), 14번(안전관리책임자 자격), 16번(안전관리규정 세부 항목).',
    '· ChatGPT 비용은 간단한 질문을 싼 모델(gpt-6-luna, 약 1원)이 답해서 평균 약 8원. 어려운 질문(gpt-6.1-sol)은 약 25원.',
    '· 비용은 공개 요금(100만 토큰당 sol \$2/\$10, luna \$0.1/\$0.5, Opus 5.5 \$4/\$20)과 1달러 1,350원으로 추정. 질문당 읽는 양 약 7,800토큰.',
    '· Claude는 API 키가 없어 같은 근거로 Claude가 직접 답한 결과(숫자 검증 단계 없음). Gemini는 무료 키라 0원.',
]
for k, t in enumerate(notes):
    fig.text(0.05, 0.105 - k * 0.022, t, fontsize=10.5 if k else 11.5, color=INK if k == 0 else INK2, weight='bold' if k == 0 else 'normal')

fig.savefig(sys.argv[1], dpi=160, facecolor=SURF)
print('ok')
