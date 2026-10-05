"""紙・スライド用の静的図表（ライトモード、IPAゴシック）。

配色は dataviz リファレンスパレット:
  カテゴリ 1=青 #2a78d6, 2=橙 #eb6834 / 連続量は青の単色ランプ / 文字は墨色。
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

for f in ("/usr/share/fonts/opentype/ipafont-gothic/ipagp.ttf", "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf"):
    if Path(f).exists():
        font_manager.fontManager.addfont(f)
plt.rcParams["font.family"] = ["IPAPGothic", "IPAGothic", "sans-serif"]

SURFACE = "#ffffff"
TEXT = "#0b0b0b"
TEXT2 = "#52514e"
MUTED = "#8a8985"
GRID = "#e6e5e1"
S1, S2 = "#2a78d6", "#eb6834"  # 青, 橙
BLUE_RAMP = ["#e8f1fd", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
SEQ = LinearSegmentedColormap.from_list("seq_blue", BLUE_RAMP)
# スライドに貼る版はスライド側にタイトルがあるため、図のタイトル・副題を省いて余白を詰める
SHOW_TITLES = True


def _top(default: float) -> float:
    return default if SHOW_TITLES else 0.95


def _style(ax, grid_axis="y"):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=TEXT2, labelsize=9, length=0)
    if grid_axis:
        ax.grid(axis=grid_axis, color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)


def _title(fig, title, subtitle=None):
    if not SHOW_TITLES:
        return
    fig.text(0.02, 0.97, title, fontsize=15, color=TEXT, ha="left", va="top", weight="bold")
    if subtitle:
        fig.text(0.02, 0.925, subtitle, fontsize=9.5, color=TEXT2, ha="left", va="top")


def _source(fig, text):
    fig.text(0.02, 0.015, text, fontsize=7.5, color=MUTED, ha="left", va="bottom")


def _save(fig, path: Path):
    fig.savefig(path, dpi=200, facecolor=SURFACE)
    plt.close(fig)


def _map_base(ax, grid: pd.DataFrame, values, vmin, vmax, cmap=SEQ):
    sc = ax.scatter(grid.lon, grid.lat, c=values, cmap=cmap, vmin=vmin, vmax=vmax, s=9, marker="s", linewidths=0)
    ax.set_aspect(1 / np.cos(np.radians(35.7)))
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    return sc


def _clinics(ax, clinics, label=True):
    for c in clinics:
        ax.scatter(c.lon, c.lat, s=46, marker="o", color=S2, edgecolor=SURFACE, linewidth=1.5, zorder=5)
        if label:
            left = c.name in ("ひばりが丘", "本院")
            ax.annotate(c.name, (c.lon, c.lat), xytext=(-4, 4) if left else (4, 3), textcoords="offset points",
                        fontsize=7.5, color=TEXT, zorder=6, ha="right" if left else "left")


def map_underserved(grid: pd.DataFrame, clinics, path: Path):
    fig, ax = plt.subplots(figsize=(10, 7.2))
    fig.subplots_adjust(left=0.02, right=0.9, top=_top(0.88), bottom=0.05)
    sc = _map_base(ax, grid, grid.underserved_ratio, 1.0, 2.6)
    _clinics(ax, clinics)
    cb = fig.colorbar(sc, ax=ax, shrink=0.6, pad=0.01)
    cb.set_label("未充足度（潜在需要 ÷ 顕在需要）", color=TEXT2, fontsize=9)
    cb.outline.set_visible(False)
    cb.ax.tick_params(colors=TEXT2, labelsize=8)
    _title(fig, "在宅医療の未充足度（各地点の半径8km）",
           "東京都並みに訪問診療が普及した場合の居宅需要が、現在の何倍か。濃いほど「まだ取られていない需要」が大きい。●＝わかさ各院")
    _source(fig, "出典: 国勢調査メッシュ(2020)・社人研推計(2025)・NDBオープンデータ第10回(2022年度)・介護サービス情報公表 から算出")
    _save(fig, path)


def map_site_score(grid: pd.DataFrame, top: pd.DataFrame, clinics, path: Path):
    fig = plt.figure(figsize=(12.6, 7.2))
    ax = fig.add_axes([0.01, 0.05, 0.6, _top(0.85) - 0.05])
    sc = _map_base(ax, grid, grid.score, 0, 100)
    _clinics(ax, clinics, label=False)
    for i, r in top.iterrows():
        ax.scatter(r.lon, r.lat, s=170, facecolor=SURFACE, edgecolor=TEXT, linewidth=1.4, zorder=7)
        ax.annotate(f"{i + 1}", (r.lon, r.lat), ha="center", va="center", fontsize=7.5, color=TEXT, zorder=8)
    cax = fig.add_axes([0.62, 0.2, 0.012, 0.5])
    cb = fig.colorbar(sc, cax=cax)
    cb.set_label("立地スコア（0〜100）", color=TEXT2, fontsize=9)
    cb.outline.set_visible(False)
    cb.ax.tick_params(colors=TEXT2, labelsize=8)
    # 右側の順位表
    x0, y0 = 0.67, _top(0.83) - 0.02
    for dx, lab, ha in ((0, "順位", "left"), (0.03, "地域", "left"), (0.19, "未充足度", "right"), (0.25, "3年後予測*", "right"), (0.3, "到達目安", "right")):
        fig.text(x0 + dx, y0, lab, fontsize=8.5, color=TEXT2, va="top", ha=ha)
    for i, r in top.iterrows():
        y = y0 - 0.045 * (i + 1)
        area = r.area.replace("神奈川県", "神奈川 ").replace("埼玉県", "埼玉 ").replace("千葉県", "千葉 ").replace("東京都", "東京 ")
        fig.text(x0, y, f"{i + 1:>2}", fontsize=10, color=TEXT, va="top")
        fig.text(x0 + 0.03, y, area, fontsize=10, color=TEXT, va="top")
        fig.text(x0 + 0.19, y, f"{r.underserved_ratio:.1f}", fontsize=10, color=TEXT, va="top", ha="right")
        fig.text(x0 + 0.25, y, f"{r.pred_home_36m_group_net:,.0f}人", fontsize=10, color=TEXT, va="top", ha="right")
        fig.text(x0 + 0.3, y, f"{r.reach_target:,.0f}人", fontsize=10, color=TEXT, va="top", ha="right")
    fig.text(x0, y0 - 0.045 * (len(top) + 1.6),
             "* 未充足度が既存院の実績範囲（最大2.1）を超える地点は\n  予測を上限値で頭打ちにしている。順位は主に到達目安で決まる",
             fontsize=8, color=TEXT2, va="top")
    _title(fig, "出店立地スコア（1都3県・2km格子）",
           "3年後の居宅患者予測（既存院との重複を除いたグループ純増）と到達目安の総合順位。○番号＝上位10地点、●＝既存院")
    _source(fig, "既存院から4km以内は候補から除外。スコアは相対順位であり、物件・人員・現地調査と組み合わせて判断する前提")
    _save(fig, path)


def model_fit(diag: pd.DataFrame, model, path: Path):
    d = diag[diag.months_open >= 6]
    fig, ax = plt.subplots(figsize=(8.6, 6.4))
    fig.subplots_adjust(left=0.1, right=0.97, top=_top(0.84), bottom=0.12)
    _style(ax, grid_axis="both")
    lo, hi = 40, 700
    xs = np.geomspace(lo, hi, 50)
    band = model.loo_pct
    ax.fill_between(xs, xs / (1 + band), xs * (1 + band), color="#f0efec", zorder=0, label=f"誤差の目安 ±{band:.0%}")
    ax.plot(xs, xs, color=MUTED, linewidth=1, zorder=1)
    for era, col in (("転換期", S1), ("施設重視期", S2)):
        e = d[d.era == era]
        ax.scatter(e.expected_home, e.home, s=70, color=col, edgecolor=SURFACE, linewidth=2, zorder=3, label=f"{era}に開院")
        for _, r in e.iterrows():
            ax.annotate(r["name"], (r.expected_home, r.home), xytext=(6, 2), textcoords="offset points", fontsize=8.5, color=TEXT)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ticks = [50, 100, 200, 400]
    ax.set_xticks(ticks, [str(t) for t in ticks])
    ax.set_yticks(ticks, [str(t) for t in ticks])
    ax.minorticks_off()
    ax.set_xlabel("モデルが予測する居宅患者数（人）", color=TEXT2, fontsize=9.5)
    ax.set_ylabel("実際の居宅患者数（人, 2026-07）", color=TEXT2, fontsize=9.5)
    leg = ax.legend(loc="upper left", frameon=False, fontsize=9)
    for t in leg.get_texts():
        t.set_color(TEXT)
    _title(fig, "居宅患者数は「開院後の年数」「地域の未充足度」「立ち上げ方針」でほぼ説明できる",
           f"12院で検証: 決定係数 R²={model.r2:.2f}、1院ずつ抜いて予測した誤差 ±{model.loo_pct:.0%}。斜線より上＝地域・年数の割に多い")
    _source(fig, "浦和（開院3か月）は推定から除外。モデル: log(居宅) = a + b·log(月数) + c·log(未充足度) + d·[施設重視期]")
    _save(fig, path)


def saturation_bars(diag: pd.DataFrame, path: Path):
    d = diag[(diag.index != "honin") & (diag.months_open >= 12)].sort_values("penetration_of_target")
    fig, ax = plt.subplots(figsize=(9.6, 6.2))
    fig.subplots_adjust(left=0.13, right=0.92, top=_top(0.8), bottom=0.11)
    _style(ax, grid_axis="x")
    y = np.arange(len(d))
    ax.barh(y, d.reach_target, height=0.62, color="#cde2fb", label="到達目安（本院並みの浸透・競合補正）")
    ax.barh(y, d.home, height=0.62, color=S1, label="現在の居宅患者")
    ax.barh(y, d.home_in_3y, height=0.18, color="#0d366b", label="現在のペースで3年後")
    for yi, (_, r) in zip(y, d.iterrows()):
        ax.annotate(f"{r.penetration_of_target:.0%}", (r.reach_target, yi), xytext=(6, 0), textcoords="offset points",
                    va="center", fontsize=9, color=TEXT)
    ax.set_yticks(y, d["name"], color=TEXT, fontsize=9.5)
    ax.set_xlabel("居宅患者数（人）", color=TEXT2, fontsize=9.5)
    leg = ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, frameon=False, fontsize=8.5)
    for t in leg.get_texts():
        t.set_color(TEXT)
    _title(fig, "どの院も「到達目安」まで大きな余地がある（数字＝現在の到達率）",
           "到達目安＝自院が最寄りとなる潜在居宅需要 × 本院の浸透率 × 競合密度の補正。本院は基準のため除外、開院12か月未満は判定保留")
    _source(fig, "上限の判定は月次推移（伸びの鈍化）で確定させる。ここでの目安は「地域構造から見た到達可能量」")
    _save(fig, path)


LABEL_OFFSETS = {"西日暮里": (6, 6), "高円寺": (6, -12), "府中": (8, -6), "調布": (8, 4), "三軒茶屋": (-6, -16)}


def growth_curves(diag: pd.DataFrame, model, path: Path, ramps: pd.DataFrame | None = None):
    """転換期型（居宅重視）で立ち上げた場合の基準カーブ。新規院の進捗管理に使う。"""
    fig, ax = plt.subplots(figsize=(9.6, 6.2))
    fig.subplots_adjust(left=0.09, right=0.97, top=_top(0.84), bottom=0.11)
    _style(ax, grid_axis="y")
    t = np.arange(1, 61)
    curves = ((1.0, S1, "東京都内（未充足度1.0）"), (1.5, "#1baf7a", "県境・神奈川（1.5）"), (2.0, S2, "埼玉・千葉の郊外（2.0）"))
    for u, col, lab in curves:
        ax.plot(t, model.predict(t, u, False), color=col, linewidth=2, label=lab, zorder=2)
    if ramps is not None and len(ramps):
        for _, g in ramps.groupby("clinic"):
            ax.plot(g.months_open, g.home, color=MUTED, linewidth=0.8, zorder=1)
    d = diag[(diag.era == "転換期") & (diag.months_open <= 60)]
    ax.scatter(d.months_open, d.home, s=60, color=TEXT, edgecolor=SURFACE, linewidth=2, zorder=3)
    for _, r in d.iterrows():
        ax.annotate(f"{r['name']}（{r.underserved_ratio:.1f}）", (r.months_open, r.home),
                    xytext=LABEL_OFFSETS.get(r["name"], (6, 3)), textcoords="offset points", fontsize=8.5, color=TEXT,
                    ha="right" if r["name"] == "三軒茶屋" else "left")
    for m in (12, 24, 36):
        ax.axvline(m, color=GRID, linewidth=0.8, zorder=0)
    ax.set_xlabel("在宅開始からの月数", color=TEXT2, fontsize=9.5)
    ax.set_ylabel("居宅患者数（人）", color=TEXT2, fontsize=9.5)
    ax.set_xlim(0, 62)
    ax.set_ylim(0, None)
    leg = ax.legend(loc="upper left", frameon=False, fontsize=9, title="地域タイプ別の基準カーブ", title_fontsize=9)
    for t_ in leg.get_texts():
        t_.set_color(TEXT)
    _title(fig, "立ち上げ基準カーブ：新規院が「順調か」を月数で判定する",
           "線＝居宅重視（転換期型）で立ち上げた場合のモデル予測。点＝転換期に開院した各院の現在値（括弧内＝その院の未充足度）")
    _source(fig, "施設重視で立ち上げた院は同じ条件で約4割少ない。月次データ投入後は各院の実際の軌跡（灰色の線）を重ねる")
    _save(fig, path)
