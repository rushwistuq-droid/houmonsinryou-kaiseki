"""院別 月次の新規・終了（フロー）の解析（機密データ。出力は analysis/confidential/ のみ）。

入力: analysis/confidential/monthly_flow.csv
  clinic, month, new_home, new_facility, end_home, end_facility （その月内の人数）

考え方:
  患者数（ストック）の増減 ＝ 新規 − 終了。終了は患者数に比例する（毎月一定割合が看取り・入院・転居で終わる）
  とみなすと、患者数は「新規 ÷ 終了率」に向かって収束する（＝流れから見た上限、均衡患者数）。
    均衡患者数 > 現在   → 今の新規ペースのままでもまだ伸びる
    均衡患者数 ≒ 現在   → 今の新規ペースでは横ばいが続く（上げるには新規を増やすしかない）
  横ばいの院は、原因を3つに分ける。
    A 担当エリアを取り切った: 新規は担当エリアの大きさに見合っている（上位院並み）。エリア自体が小さい
    B 新規が少ない: 担当エリアの大きさに比べて新規が少ない（紹介が来ていない）
    C 終了が多い: 患者数に対する終了の割合が他院より高い（理由の内訳が要る。看取りの多さは質の裏返しの場合もある）
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

FLOW_COLS = ["new_home", "end_home", "new_facility", "end_facility"]
FLOW_LABELS = {"施設新規": "new_facility", "居宅新規": "new_home", "施設終了": "end_facility", "居宅終了": "end_home"}
STOCK_LABELS = {"施設": "facility_patients", "居宅": "home_reported", "居宅(がん医総)": "home_cancer_patients", "総数": "total_patients"}
HOME_INCLUDES_CANCER_FROM = "2026-04"
COMBINED_FLOW_BEFORE = "2024-01"  # これより前の新規・終了は居宅・施設の合計のみ（施設の欄に記入）
STOCK_GAP_TOL = 5  # この月から院の「居宅」欄にがん医総が含まれる
CLINIC_ALIAS = {"石神井": "石神井公園"}

WINDOW = 12  # 率を出す期間（直近12か月。季節の偏りをならす）
MIN_FLOW_MONTHS = 12  # 判定に必要なフローの月数
MIN_HOME_MONTHS = 24  # 判定対象＝在宅開始24か月以上（立ち上げ中の院は伸びて当然のため対象外）
EQ_GROWING = 1.15  # 均衡患者数／現在 がこれ以上なら「まだ伸びる」
EQ_SHRINKING = 0.9  # これ未満なら「縮小方向」
LOW_INFLOW = 0.6  # 新規率（到達目安あたり）が上位院比のこの倍率未満なら B
HIGH_OUTFLOW = 1.2  # 終了率が比較院の中央値のこの倍率以上なら C
RECONCILE_TOL = 3  # 患者数の増減と（新規−終了）の差がこれを超えたら記録の食い違い
ONE_OFF_GAP = 10  # 差がこれを超える月は一時的な数え直し等とみなし、記入された終了を使う


# ---------------------------------------------------------------- 読み込み

def parse_upload(path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """院から届く Excel（左に患者数、右に新規・終了）を整形する。

    左側の患者数は見出しの年が欠けているため、右側の見出し（年月つき）の最新月から列の並び順で月を割り当てる。
    返り値: (stock, flow)。stock の居宅は「総数−施設」（2026年4月の定義変更でがん医総の扱いが変わったため）。
    """
    v = pd.read_excel(path, header=None)
    hdr = v.iloc[0]
    flow_lab = next(j for j in range(v.shape[1]) if hdr[j] == "時期")
    flow_cols = [j for j in range(flow_lab + 1, v.shape[1]) if isinstance(hdr[j], (dt.datetime, pd.Timestamp))]
    latest = pd.Period(hdr[flow_cols[0]], freq="M")

    stock_cols = []
    for j in range(2, flow_lab - 1):
        if v.iloc[1:, j].notna().any():
            stock_cols.append(j)
        elif stock_cols:
            break
    stock_month = {j: latest - k for k, j in enumerate(stock_cols)}

    srows, frows = [], []
    s_clinic = f_clinic = None
    for i in range(1, v.shape[0]):
        if isinstance(v.iat[i, 0], str):
            s_clinic = CLINIC_ALIAS.get(v.iat[i, 0].strip(), v.iat[i, 0].strip())
        if isinstance(v.iat[i, flow_lab - 1], str):
            f_clinic = CLINIC_ALIAS.get(v.iat[i, flow_lab - 1].strip(), v.iat[i, flow_lab - 1].strip())
        lab = str(v.iat[i, 1]).strip()
        if lab in STOCK_LABELS:
            for j in stock_cols:
                srows.append((s_clinic, stock_month[j], STOCK_LABELS[lab], _num(v.iat[i, j])))
        flab = str(v.iat[i, flow_lab]).strip()
        if flab in FLOW_LABELS:
            for j in flow_cols:
                frows.append((f_clinic, pd.Period(hdr[j], freq="M"), FLOW_LABELS[flab], _num(v.iat[i, j])))

    stock = _wide(srows)
    # 総数が空欄の月は内訳から復元する（定義変更前は 居宅＋がん医総、変更後は 居宅 に がん医総 を含む）
    miss = stock.total_patients.isna() & stock.facility_patients.notna() & stock.home_reported.notna()
    before = stock.month < pd.Period(HOME_INCLUDES_CANCER_FROM, freq="M")
    stock.loc[miss, "total_patients"] = (
        stock.facility_patients + stock.home_reported + stock.home_cancer_patients.fillna(0).clip(lower=0).where(before, 0)
    )[miss]
    stock = stock[stock.total_patients.fillna(0) > 0].copy()
    stock["facility_patients"] = stock.facility_patients.fillna(0)  # 総数があり施設が空欄＝施設0人
    stock["home_cancer_patients"] = stock.home_cancer_patients.where(stock.home_cancer_patients >= 0)  # 負の値は入力の誤り
    stock["home_patients"] = stock.total_patients - stock.facility_patients
    # 総数が内訳（施設＋居宅＋がん医総）より大きい月は、差を施設とみなす（2022年9月以前の本院・所沢。
    # 翌月に施設がほぼ同じ人数だけ増えており、施設の一部が別区分で数えられていたため）
    before = stock.month < pd.Period(HOME_INCLUDES_CANCER_FROM, freq="M")
    comp_home = stock.home_reported + stock.home_cancer_patients.fillna(0).where(before, 0)
    gap = stock.total_patients - stock.facility_patients - comp_home
    fix = before & stock.home_reported.notna() & (gap > STOCK_GAP_TOL)
    stock.loc[fix, "home_patients"] = comp_home[fix]
    stock.loc[fix, "facility_patients"] = (stock.total_patients - comp_home)[fix]
    stock = stock[["clinic", "month", "home_patients", "facility_patients", "home_cancer_patients", "total_patients"]]
    flow = _wide(frows)
    # 開院前（全項目が空か0）の月は落とす
    flow = flow[flow[FLOW_COLS].fillna(0).sum(axis=1) > 0].copy()
    # 居宅・施設の内訳が無い古い月（居宅の欄が空欄）は、施設の欄に合計が入っている
    combined = flow.new_home.isna() & flow.end_home.isna() & (flow.month < pd.Period(COMBINED_FLOW_BEFORE, freq="M"))
    flow["new_total"] = flow.new_home.fillna(0) + flow.new_facility.fillna(0)
    flow["end_total"] = flow.end_home.fillna(0) + flow.end_facility.fillna(0)
    flow.loc[combined, ["new_facility", "end_facility"]] = np.nan
    flow["split"] = ~combined
    # 新規・終了の片方だけ空欄の月は、空欄＝0人と読む（両方空欄の月は不明のまま）
    for kind in ("home", "facility"):
        n, e = f"new_{kind}", f"end_{kind}"
        k = flow.split
        flow.loc[k & flow[n].isna() & flow[e].notna(), n] = 0
        flow.loc[k & flow[e].isna() & flow[n].notna(), e] = 0
    return stock.reset_index(drop=True), flow[["clinic", "month", *FLOW_COLS, "new_total", "end_total", "split"]].reset_index(drop=True)


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return np.nan


def _wide(rows) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["clinic", "month", "k", "v"])
    w = df.pivot_table(index=["clinic", "month"], columns="k", values="v", aggfunc="first", dropna=False).reset_index()
    w.columns.name = None
    return w.sort_values(["clinic", "month"]).reset_index(drop=True)


def load(path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["month"] = pd.PeriodIndex(df.month, freq="M")
    return df.sort_values(["clinic", "month"]).reset_index(drop=True)


# ---------------------------------------------------------------- 補正・突合

def adjust_flow(flow: pd.DataFrame, events: list[dict], kinds: tuple[str, ...] = ("移管", "集計修正")) -> pd.DataFrame:
    """移管・集計修正の月は、その人数が「終了」に計上されているため差し引く（実際の看取り・入院等ではない）。"""
    out = flow.copy()
    out["adjusted"] = ""
    for e in events:
        if e.get("kind") not in kinds or int(e["delta"]) >= 0:
            continue
        col = "end_home" if e["series"] == "home" else "end_facility"
        k = (out.clinic == e["clinic"]) & (out.month == pd.Period(e["month"], freq="M"))
        out.loc[k, col] = (out.loc[k, col] + int(e["delta"])).clip(lower=0)
        out.loc[k, "adjusted"] = (out.loc[k, "adjusted"] + f"{e['kind']}{col}{int(e['delta'])} ").str.strip()
    return out


def reconcile(flow: pd.DataFrame, stock: pd.DataFrame, tol: int = RECONCILE_TOL) -> pd.DataFrame:
    """患者数の前月差と（新規−終了）を突き合わせる。差が tol を超える月＝記録の食い違い（計上漏れ・二重計上・定義差）。"""
    s = stock.sort_values(["clinic", "month"]).copy()
    s["d_home"] = s.groupby("clinic").home_patients.diff()
    s["d_facility"] = s.groupby("clinic").facility_patients.diff()
    m = flow.merge(s[["clinic", "month", "d_home", "d_facility"]], on=["clinic", "month"], how="left")
    m["gap_home"] = m.d_home - (m.new_home - m.end_home)
    m["gap_facility"] = m.d_facility - (m.new_facility - m.end_facility)
    bad = (m.gap_home.abs() > tol) | (m.gap_facility.abs() > tol)
    return m[bad][["clinic", "month", "d_home", "new_home", "end_home", "gap_home",
                   "d_facility", "new_facility", "end_facility", "gap_facility"]].reset_index(drop=True)


def reconcile_summary(flow: pd.DataFrame, stock: pd.DataFrame) -> pd.DataFrame:
    """院別に、記録がどれだけ患者数の増減と合っているか（一致率と平均のずれ）。"""
    s = stock.sort_values(["clinic", "month"]).copy()
    s["d_home"] = s.groupby("clinic").home_patients.diff()
    s["d_facility"] = s.groupby("clinic").facility_patients.diff()
    m = flow.merge(s, on=["clinic", "month"], how="left")
    m["gap_home"] = m.d_home - (m.new_home - m.end_home)
    m["gap_facility"] = m.d_facility - (m.new_facility - m.end_facility)
    g = m.dropna(subset=["gap_home"]).groupby("clinic")
    return pd.DataFrame({
        "months": g.size(),
        "home_match_rate": g.gap_home.apply(lambda x: (x.abs() <= RECONCILE_TOL).mean()),
        "home_gap_mean": g.gap_home.mean(),
        "facility_match_rate": g.gap_facility.apply(lambda x: (x.abs() <= RECONCILE_TOL).mean()),
        "facility_gap_mean": g.gap_facility.mean(),
    })


# ---------------------------------------------------------------- 率・均衡

def _slope_t(y: np.ndarray) -> tuple[float, float]:
    y = np.asarray(y, float)
    ok = ~np.isnan(y)
    if ok.sum() < 4:
        return np.nan, np.nan
    x = np.arange(len(y))[ok]
    y = y[ok]
    b, a = np.polyfit(x, y, 1)
    resid = y - (a + b * x)
    se = np.sqrt(resid.var(ddof=2) / ((x - x.mean()) ** 2).sum())
    return float(b), float(b / se) if se > 0 else float("inf")


def flow_table(flow: pd.DataFrame, stock: pd.DataFrame, window: int = WINDOW, ends: str = "implied") -> pd.DataFrame:
    """院別の新規・終了の水準と率、均衡患者数。

    end_rate = 終了 ÷ 患者数（月あたり）。平均在籍月数 ≒ 1 ÷ end_rate。
    eq = 新規 ÷ end_rate ＝ 今のペースが続いた場合に患者数が落ち着く水準。
    ends="implied": 終了を「新規 − 患者数の前月差」で求める（患者数は請求ベースで確か。終了の記入漏れがあっても
    患者数の実際の動きと矛盾しない）。ただし差が ONE_OFF_GAP を超える月は一時的な数え直しとみなし、記入値を使う
    （将来も続く流出ではないため）。"recorded": 記入された終了をそのまま使う。
    """
    latest = flow.month.max()
    st = stock.sort_values(["clinic", "month"]).copy()
    st["d_home"] = st.groupby("clinic").home_patients.diff()
    st["d_facility"] = st.groupby("clinic").facility_patients.diff()
    m = flow.merge(st, on=["clinic", "month"], how="left")
    for kind in ("home", "facility"):
        m[f"end_{kind}_recorded"] = m[f"end_{kind}"]
        m[f"end_{kind}_implied"] = m[f"new_{kind}"] - m[f"d_{kind}"]
        if ends == "implied":
            one_off = (m[f"end_{kind}_implied"] - m[f"end_{kind}_recorded"]).abs() > ONE_OFF_GAP
            m[f"end_{kind}"] = m[f"end_{kind}_implied"].where(~one_off).fillna(m[f"end_{kind}_recorded"])
    rows = []
    for c, g in m.groupby("clinic"):
        g = g.sort_values("month")
        w = g[g.month > latest - window]
        prev = g[(g.month <= latest - window) & (g.month > latest - 2 * window)]
        sc = st[st.clinic == c]
        cur = sc[sc.month == sc.month.max()].iloc[0]
        r = {"clinic": c, "flow_months": int(len(w)), "home": cur.home_patients, "facility": cur.facility_patients}
        for kind, s_col in (("home", "home_patients"), ("facility", "facility_patients")):
            new, end, stk = w[f"new_{kind}"].mean(), w[f"end_{kind}"].mean(), w[s_col].mean()
            rate = end / stk if stk and stk > 0 else np.nan
            r[f"new_{kind}_m"] = new
            r[f"end_{kind}_m"] = end
            r[f"end_{kind}_recorded_m"] = w[f"end_{kind}_recorded"].mean()
            r[f"net_{kind}_m"] = new - end
            r[f"end_rate_{kind}"] = rate
            r[f"stay_{kind}_months"] = 1 / rate if rate and rate > 0 else np.nan
            r[f"eq_{kind}"] = new / rate if rate and rate > 0 else np.nan
            r[f"eq_ratio_{kind}"] = r[f"eq_{kind}"] / r[kind] if r[kind] else np.nan
            r[f"new_{kind}_prev12_m"] = prev[f"new_{kind}"].mean() if len(prev) >= 6 else np.nan
            r[f"new_{kind}_chg_yoy"] = new / r[f"new_{kind}_prev12_m"] - 1 if r[f"new_{kind}_prev12_m"] else np.nan
            r[f"new_{kind}_6m"] = w[f"new_{kind}"].tail(6).mean()
            b, t = _slope_t(w[f"new_{kind}"].to_numpy())
            r[f"new_{kind}_slope"] = b
            r[f"new_{kind}_t"] = t
        rows.append(r)
    out = pd.DataFrame(rows).set_index("clinic")
    out["new_home_trend"] = [_trend(b, t, n) for b, t, n in zip(out.new_home_slope, out.new_home_t, out.new_home_m)]
    return out


def _trend(slope, t, level) -> str:
    if np.isnan(slope) or level <= 0:
        return ""
    if abs(t) < 2 or abs(slope) * 12 < 0.15 * level:
        return "横ばい"
    return "増加" if slope > 0 else "減少"


# ---------------------------------------------------------------- 原因の分類

def classify(ft: pd.DataFrame, diag: pd.DataFrame, first_mover: str = "本院") -> pd.DataFrame:
    """院別に「流れから見た見通し」と、横ばいの原因（A/B/C）を付ける。

    diag: model.diagnose の結果（name, months_open, reach_target, penetration_of_target を使う）。
    比較の物差し（新規率・終了率）は、在宅開始24か月以上・先行院を除く院の値から取る。
    """
    d = diag.set_index("name") if "name" in diag.columns else diag
    out = ft.copy()
    out["months_open"] = d.months_open.reindex(out.index)
    out["reach_target"] = d.reach_target.reindex(out.index)
    out["penetration_of_target"] = d.penetration_of_target.reindex(out.index)
    # 新規率: 到達目安（担当エリアの潜在需要×上位院の取り込み率）100人あたりの月間新規。担当エリアの大きさで割った新規の強さ
    out["inflow_per_target"] = 100 * out.new_home_m / out.reach_target
    # 到達目安に届くために必要な月間新規（今の終了率のまま）
    out["new_home_needed"] = out.reach_target * out.end_rate_home
    out["new_home_gap"] = out.new_home_needed - out.new_home_m

    peers = out[(out.months_open >= MIN_HOME_MONTHS) & (out.index != first_mover) & (out.flow_months >= MIN_FLOW_MONTHS)]
    ref_inflow = float(peers.inflow_per_target.nlargest(4).mean()) if len(peers) else np.nan  # 上位院並みの新規率
    ref_end = float(peers.end_rate_home.median()) if len(peers) else np.nan
    out["inflow_vs_ref"] = out.inflow_per_target / ref_inflow
    out["end_rate_vs_ref"] = out.end_rate_home / ref_end

    outlook, cause, note = [], [], []
    for c, r in out.iterrows():
        if c == first_mover:
            outlook.append(_outlook(r.eq_ratio_home))
            cause.append("（先行院）")
            note.append("地域で確立。比較の物差しからは除外")
            continue
        if not (r.months_open >= MIN_HOME_MONTHS and r.flow_months >= MIN_FLOW_MONTHS):
            outlook.append("立ち上げ中")
            cause.append("")
            note.append("在宅開始24か月未満。立ち上げ基準カーブで管理")
            continue
        o = _outlook(r.eq_ratio_home)
        outlook.append(o)
        if o == "まだ伸びる":
            cause.append("")
            note.append(f"今の新規ペースで約{r.eq_home:.0f}人まで伸びる見込み")
            continue
        tags = []
        if r.inflow_vs_ref < LOW_INFLOW:
            tags.append("B 新規が少ない")
        if r.end_rate_vs_ref >= HIGH_OUTFLOW:
            tags.append("C 終了が多い")
        if not tags and r.penetration_of_target >= 0.85:
            tags.append("A 担当エリアを取り切った")
        if not tags:
            tags.append("B' 新規がやや少ない")
        cause.append("＋".join(tags))
        note.append(_note(r, tags))
    out["flow_outlook"] = outlook
    out["stall_cause"] = cause
    out["flow_note"] = note
    out.attrs.update(ref_inflow=ref_inflow, ref_end_rate=ref_end)
    return out


def _outlook(eq_ratio) -> str:
    if np.isnan(eq_ratio):
        return ""
    if eq_ratio >= EQ_GROWING:
        return "まだ伸びる"
    if eq_ratio < EQ_SHRINKING:
        return "縮小方向"
    return "横ばい（均衡）"


def _note(r, tags) -> str:
    parts = []
    if any(t.startswith("A") for t in tags):
        parts.append("新規は担当エリアの大きさに見合う。上積みにはエリアの再設定・隣接地域の開拓が要る")
    if any(t.startswith("B") for t in tags):
        parts.append(f"到達目安に届くには月{r.new_home_needed:.0f}人の新規が要る（現在{r.new_home_m:.1f}人）")
    if any(t.startswith("C") for t in tags):
        parts.append(f"平均在籍{r.stay_home_months:.0f}か月と短め。終了理由（看取り・入院・他院へ）の内訳を確認")
    return "。".join(parts)


def group_flow(flow: pd.DataFrame) -> pd.DataFrame:
    """グループ全体の月次の新規・終了（補正後）。居宅・施設の内訳がそろっている月だけ。"""
    if "split" in flow:
        ok = flow.groupby("month").split.transform("all").astype(bool)
        flow = flow[ok]
    g = flow.groupby("month")[FLOW_COLS].sum(min_count=1)
    g["net_home"] = g.new_home - g.end_home
    g["net_facility"] = g.new_facility - g.end_facility
    return g
