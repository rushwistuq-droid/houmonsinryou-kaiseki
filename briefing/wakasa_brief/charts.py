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
    x0, y0 = 0.69, _top(0.83) - 0.02
    for dx, lab, ha in ((0, "順位", "left"), (0.03, "地域", "left"), (0.19, "未充足度", "right"), (0.25, "3年後予測*", "right"), (0.3, "到達目安", "right")):
        fig.text(x0 + dx, y0, lab, fontsize=8.5, color=TEXT2, va="top", ha=ha)
    for i, r in top.iterrows():
        y = y0 - 0.045 * (i + 1)
        area = r.area.replace("茨城県", "茨城 ").replace("神奈川県", "神奈川 ").replace("埼玉県", "埼玉 ").replace("千葉県", "千葉 ").replace("東京都", "東京 ")
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
           f"{model.n}院で検証: 決定係数 R²={model.r2:.2f}、1院ずつ抜いて予測した誤差 ±{model.loo_pct:.0%}。斜線より上＝地域・年数の割に多い")
    _source(fig, "推定から除外: 浦和（開院直後）・本院（先行者。図には参考表示）。モデル: log(居宅) = a + b·log(月数) + c·log(未充足度) + d·[施設重視期]")
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


# ---------------------------------------------------------------- 月次推移（機密）
CAT5 = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
FACILITY_TINT = "#9ec5f4"
EVENT_MONTHS = {"2025-04": "高円寺開院・施設移管", "2025-08": "複数院で一斉減少"}


def _month_axis(ax, months):
    idx = np.arange(len(months))
    ticks = [i for i, m in enumerate(months) if m.endswith("-01") or m.endswith("-07")]
    ax.set_xticks(ticks, [months[i].replace("-", "/") for i in ticks], fontsize=8.5, color=TEXT2)
    return idx


def group_trend(gt: pd.DataFrame, path: Path):
    months = [str(m) for m in gt.index]
    fig, ax = plt.subplots(figsize=(9.6, 6.2))
    fig.subplots_adjust(left=0.09, right=0.9, top=_top(0.84), bottom=0.1)
    _style(ax, grid_axis="y")
    x = _month_axis(ax, months)
    ax.stackplot(x, gt.facility_patients, gt.home_patients, colors=[FACILITY_TINT, S1], edgecolor=SURFACE, linewidth=0.5)
    end = len(x) - 1
    ax.annotate(f"居宅 {gt.home_patients.iloc[-1]:,}人", (end, gt.facility_patients.iloc[-1] + gt.home_patients.iloc[-1] / 2),
                xytext=(8, 0), textcoords="offset points", va="center", fontsize=10, color=TEXT)
    ax.annotate(f"施設 {gt.facility_patients.iloc[-1]:,}人", (end, gt.facility_patients.iloc[-1] / 2),
                xytext=(8, 0), textcoords="offset points", va="center", fontsize=10, color=TEXT)
    for i, ha in ((0, "left"), (end, "right")):
        ax.annotate(f"居宅比 {gt.home_mix.iloc[i]:.0%}", (i, gt.total_patients.iloc[i]), xytext=(0, 8),
                    textcoords="offset points", ha=ha, fontsize=9, color=TEXT2)
    ax.set_xlim(-0.5, end + 0.5)
    ax.set_ylabel("患者数（人、月末）", color=TEXT2, fontsize=9.5)
    _title(fig, "グループ全体：施設は1年半横ばい、伸びはすべて居宅",
           "全院合計の月末患者数。下＝施設、上＝居宅（がん医総を含む）")
    _source(fig, "院内月次データ（機密）。居宅はがん医総を含めて全期間で揃えた。2025年8月の報告値修正はそれ以前の値に反映")
    _save(fig, path)


def clinic_small_multiples(df: pd.DataFrame, order: list[str], path: Path):
    months = sorted({str(m) for m in df.month})
    fig, axes = plt.subplots(4, 4, figsize=(12, 8.6), sharex=True)
    fig.subplots_adjust(left=0.05, right=0.98, top=_top(0.86), bottom=0.06, hspace=0.45, wspace=0.28)
    for ax, c in zip(axes.flat, order):
        _style(ax, grid_axis="y")
        g = df[df.clinic == c].set_index(df[df.clinic == c].month.astype(str)).reindex(months)
        x = np.arange(len(months))
        for m in EVENT_MONTHS:
            if m in months:
                ax.axvline(months.index(m), color=GRID, linewidth=1.2, zorder=0)
        ax.plot(x, g.facility_patients, color=FACILITY_TINT, linewidth=2)
        ax.plot(x, g.home_patients, color=S1, linewidth=2)
        ax.set_title(c, fontsize=10.5, color=TEXT, loc="left")
        ax.set_ylim(0, None)
        ax.tick_params(labelsize=7.5)
        ticks = [i for i, m in enumerate(months) if m.endswith("-01")]
        ax.set_xticks(ticks, [months[i][2:4] + "年" for i in ticks])
    for ax in list(axes.flat)[len(order):]:
        ax.axis("off")
    legend_ax = list(axes.flat)[len(order)]
    legend_ax.plot([], [], color=S1, linewidth=2, label="居宅（がん医総含む）")
    legend_ax.plot([], [], color=FACILITY_TINT, linewidth=2, label="施設")
    legend_ax.plot([], [], color=GRID, linewidth=1.2, label="2025年4月（移管）・8月（集計修正）")
    leg = legend_ax.legend(loc="center left", frameon=False, fontsize=10)
    for t in leg.get_texts():
        t.set_color(TEXT)
    _title(fig, "院別の月次推移（補正後、2023年12月〜2026年9月）", "各院で縦軸の目盛りが異なる。青＝居宅、薄青＝施設")
    _source(fig, "補正: 2025年4月の高円寺への施設移管と、2025年8月の報告値の修正による段差を、それ以前の値をずらして除いた（確認済み）")
    _save(fig, path)


def launch_curves(df: pd.DataFrame, clinics: list[str], underserved: dict[str, float], model, path: Path):
    fig, ax = plt.subplots(figsize=(9.6, 6.2))
    fig.subplots_adjust(left=0.09, right=0.86, top=_top(0.84), bottom=0.11)
    _style(ax, grid_axis="y")
    tmax = int(df[df.clinic.isin(clinics)].months_open.max()) + 1
    t = np.arange(1, tmax + 1)
    levels = sorted({round(min(underserved[c], model.underserved_range[1]), 1) for c in clinics})
    for u in levels:
        yv = model.predict(t, u, False)
        ax.plot(t, yv, color=MUTED, linewidth=1, linestyle=(0, (4, 3)), zorder=1)
        ax.annotate(f"基準{u:.1f}", (t[-1], yv[-1]), xytext=(4, 0), textcoords="offset points", va="center", fontsize=8, color=TEXT2)
    for c, col in zip(clinics, CAT5):
        g = df[(df.clinic == c) & (df.months_open >= 0)]
        ax.plot(g.months_open, g.home_patients, color=col, linewidth=2.2, zorder=2)
        ax.annotate(f"{c}（{underserved[c]:.1f}）", (g.months_open.iloc[-1], g.home_patients.iloc[-1]), xytext=(6, 0),
                    textcoords="offset points", va="center", fontsize=9, color=TEXT)
    ax.plot([], [], color=MUTED, linewidth=2.2, label="実績")
    ax.plot([], [], color=MUTED, linewidth=1, linestyle=(0, (4, 3)), label="モデルの基準カーブ（数字＝未充足度、転換期型）")
    leg = ax.legend(loc="upper left", frameon=False, fontsize=9)
    for t_ in leg.get_texts():
        t_.set_color(TEXT)
    ax.set_xlabel("在宅開始からの月数", color=TEXT2, fontsize=9.5)
    ax.set_ylabel("居宅患者数（人）", color=TEXT2, fontsize=9.5)
    ax.set_xlim(0, tmax + 1)
    ax.set_ylim(0, None)
    _title(fig, "新しい院の立ち上げ：実績（実線）と基準カーブ（点線）", "括弧内＝その院の未充足度。自院の未充足度の点線を上回れば基準より順調（2.1以上は2.1で頭打ち）")
    _source(fig, "院内月次データ（機密）")
    _save(fig, path)


def forecast_bars(fc: pd.DataFrame, order: list[str], path: Path):
    d = fc.reindex(order)
    fig, ax = plt.subplots(figsize=(9.6, 6.2))
    fig.subplots_adjust(left=0.13, right=0.95, top=_top(0.8), bottom=0.1)
    _style(ax, grid_axis="x")
    y = np.arange(len(d))
    ax.barh(y, d.high, height=0.6, color="#cde2fb", label="12か月後の見通し（幅）")
    ax.barh(y, d.low, height=0.6, color="#9ec5f4")
    ax.barh(y, d.home_now, height=0.25, color="#0d366b", label="現在（2026年9月）")
    for yi, r in zip(y, d.itertuples()):
        ax.annotate(f"{r.home_now}→{r.low:.0f}〜{r.high:.0f}人", (max(r.high, r.home_now), yi), xytext=(6, 0),
                    textcoords="offset points", va="center", fontsize=9, color=TEXT)
    ax.set_yticks(y, d.index, color=TEXT, fontsize=9.5)
    ax.set_xlim(0, d.high.max() * 1.28)
    ax.invert_yaxis()
    ax.set_xlabel("居宅患者数（人）", color=TEXT2, fontsize=9.5)
    leg = ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, frameon=False, fontsize=8.5)
    for t in leg.get_texts():
        t.set_color(TEXT)
    _title(fig, "居宅患者の12か月後の見通し（2027年9月）", "低い方＝直近12か月の傾きの延長、高い方＝獲得予測モデルの成長カーブ（逆の場合もあり）")
    _source(fig, "見通しは施策を変えない場合の延長。医師増員・営業エリアの見直しで上振れしうる")
    _save(fig, path)


def peer_position(diag: pd.DataFrame, path: Path):
    """同条件（地域タイプ）の上位院の取り込み率を100%としたときの各院の水準。"""
    d = diag[(diag.index != "honin") & (diag.months_open >= 12)].copy()
    d = d.sort_values("penetration_of_target")
    stalled = d.verdict.str.startswith("停滞")
    fig, ax = plt.subplots(figsize=(9.6, 6.2))
    fig.subplots_adjust(left=0.2, right=0.93, top=_top(0.8), bottom=0.11)
    _style(ax, grid_axis="x")
    y = np.arange(len(d))
    ax.barh(y, 100 * d.penetration_of_target, height=0.6, color=np.where(stalled, S2, S1))
    ax.axvline(100, color=TEXT2, linewidth=1, linestyle=(0, (4, 3)))
    ax.annotate("同条件の上位院の水準", (100, len(d) - 0.4), xytext=(4, 0), textcoords="offset points", fontsize=8.5, color=TEXT2)
    for yi, r in zip(y, d.itertuples()):
        ax.annotate(f"{100 * r.penetration_of_target:.0f}%", (max(100 * r.penetration_of_target, 100), yi), xytext=(5, 0),
                    textcoords="offset points", va="center", fontsize=9, color=TEXT)
    ax.set_yticks(y, [f"{n}（{t}）" for n, t in zip(d["name"], d.area_type)], color=TEXT, fontsize=9.5)
    ax.set_xlim(0, max(125, 100 * d.penetration_of_target.max() + 15))
    ax.set_xlabel("自院が最寄りの潜在居宅需要の取り込み率（同条件の上位院＝100%）", color=TEXT2, fontsize=9.5)
    from matplotlib.patches import Patch

    handles = [Patch(color=S2, label="停滞（直近6か月横ばい・減少）"), Patch(color=S1, label="増加中")]
    leg = ax.legend(handles=handles, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, frameon=False, fontsize=9)
    for t in leg.get_texts():
        t.set_color(TEXT)
    _title(fig, "同じ条件の院と比べた取り込みの水準", "上位院＝都市型はひばりが丘・調布、未充足型は津田沼・所沢の平均（在宅24か月以上、本院は先行者のため除外）")
    _source(fig, "100%前後で停滞＝自院の担当エリアは取り切りつつある（エリアが狭いのが制約）。100%を大きく下回って停滞＝エリア内に余地がある")
    _save(fig, path)


def group_flow(gf: pd.DataFrame, path: Path):
    """グループ全体の月間新規と終了（3か月移動平均）。左＝居宅、右＝施設。"""
    months = [str(m) for m in gf.index]
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 6.2), sharey=False)
    fig.subplots_adjust(left=0.08, right=0.97, top=_top(0.8), bottom=0.12, wspace=0.22)
    for ax, kind, label in ((axes[0], "home", "居宅"), (axes[1], "facility", "施設")):
        _style(ax, grid_axis="y")
        x = _month_axis(ax, months)
        last = {}
        for col, color, name in ((f"new_{kind}", S1, "新規"), (f"end_{kind}", S2, "終了")):
            ax.scatter(x, gf[col], s=10, color=color, alpha=0.3, linewidths=0)
            ma3 = gf[col].rolling(3, min_periods=2).mean()
            ax.plot(x, ma3, color=color, linewidth=2.2)
            last[name] = (ma3.iloc[-1], color)
        # 末尾ラベルが重なる場合は上下に離す
        (vn, cn), (ve, ce) = last["新規"], last["終了"]
        sep = 9 if abs(vn - ve) < 0.08 * ax.get_ylim()[1] else 0
        for name, (v, color), dy in (("新規", (vn, cn), sep if vn >= ve else -sep), ("終了", (ve, ce), -sep if vn >= ve else sep)):
            ax.annotate(f"{name} {v:.0f}", (x[-1], v), xytext=(4, dy), textcoords="offset points",
                        va="center", fontsize=9.5, color=color)
        ax.set_xlim(-0.5, len(x) + 3.5)
        ax.set_ylim(0, max(gf[f"new_{kind}"].max(), gf[f"end_{kind}"].max()) * 1.12)
        ax.set_title(label, loc="left", fontsize=12, color=TEXT, weight="bold")
    axes[0].set_ylabel("人／月（線は3か月移動平均）", color=TEXT2, fontsize=9.5)
    _title(fig, "グループ全体の新規と終了：居宅の新規は2024年夏から月150人前後で横ばい",
           "新規と終了の差が純増。終了は患者数にほぼ比例して増えるため、新規が横ばいなら純増はしだいに細る")
    _source(fig, "院内月次データ（機密）。移管・報告値修正の月は、その人数を終了から除いた")
    _save(fig, path)


def flow_balance(cls: pd.DataFrame, order: list[str], path: Path):
    """院別：現在の居宅患者数と、今の新規・終了のペースが続いた場合の落ち着き先（均衡患者数）。"""
    d = cls.reindex([c for c in order if c in cls.index])
    fig, ax = plt.subplots(figsize=(9.6, 6.2))
    fig.subplots_adjust(left=0.13, right=0.97, top=_top(0.8), bottom=0.1)
    _style(ax, grid_axis="x")
    y = np.arange(len(d))
    flat = d.flow_outlook.str.startswith("横ばい") | d.flow_outlook.str.startswith("縮小")
    launch = d.flow_outlook == "立ち上げ中"
    colors = np.where(flat, S2, np.where(launch, "#9ec5f4", S1))
    ax.barh(y, d.home, height=0.6, color=colors)
    ax.scatter(d.eq_home, y, marker="D", s=34, color=TEXT, zorder=3)
    for yi, r in zip(y, d.itertuples()):
        ax.plot([r.home, r.eq_home], [yi, yi], color=TEXT, linewidth=1, zorder=2)
        tag = r.stall_cause if isinstance(r.stall_cause, str) and r.stall_cause and not r.stall_cause.startswith("（") else ""
        ax.annotate(f"{r.home:.0f}→{r.eq_home:.0f}人  {tag}", (max(r.home, r.eq_home), yi), xytext=(7, 0),
                    textcoords="offset points", va="center", fontsize=9, color=TEXT)
    ax.set_yticks(y, d.index, color=TEXT, fontsize=9.5)
    ax.set_xlim(0, d[["home", "eq_home"]].max().max() * 1.45)
    ax.invert_yaxis()
    ax.set_xlabel("居宅患者数（人）　棒＝現在、◆＝均衡患者数（月間新規 ÷ 終了率）", color=TEXT2, fontsize=9.5)
    from matplotlib.patches import Patch

    handles = [Patch(color=S2, label="横ばい（均衡に到達）"), Patch(color=S1, label="まだ伸びる"), Patch(color="#9ec5f4", label="立ち上げ中")]
    leg = ax.legend(handles=handles, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, frameon=False, fontsize=9)
    for t in leg.get_texts():
        t.set_color(TEXT)
    _title(fig, "今の新規ペースが続くと、居宅患者はどこで落ち着くか",
           "直近12か月の月間新規と終了率から。◆が棒の先と重なる院は、新規を増やさない限り横ばいが続く")
    _source(fig, "A＝担当エリアを取り切った／B＝新規が少ない（エリアの大きさ比）／C＝終了が多い。院内月次データ（機密）")
    _save(fig, path)
