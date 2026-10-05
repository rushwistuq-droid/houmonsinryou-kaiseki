"""院別アクションシート（やる / 様子見 / やらない）。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .hq_analysis import ClinicMarketRow, HQPipelineResult


@dataclass
class ActionItem:
    clinic_id: str
    clinic_name: str
    decision: str  # やる / 様子見 / やらない / 横展開
    priority: str  # 高 / 中 / 低
    rationale: str
    actions: list[str]
    kpis: list[str]
    dont: list[str]


def build_action_sheets(result: HQPipelineResult) -> list[ActionItem]:
    rows = {r.id: r for r in result.clinics}
    fac = {f["id"]: f for f in result.facility_kpi}
    items: list[ActionItem] = []

    # クラスター定義
    mitaka_cluster = {"shakujii", "hibarigaoka", "mitaka", "chofu", "fuchu", "koenji"}

    for r in result.clinics:
        f = fac.get(r.id, {})
        fac_pct = f.get("facility_share_of_panel_pct")
        decision, priority, rationale, actions, kpis, dont = _decide(r, fac_pct, mitaka_cluster)
        items.append(
            ActionItem(
                clinic_id=r.id,
                clinic_name=r.name,
                decision=decision,
                priority=priority,
                rationale=rationale,
                actions=actions,
                kpis=kpis,
                dont=dont,
            )
        )

    # クラスター横断アクション
    cluster_rows = [rows[i] for i in mitaka_cluster if i in rows]
    if cluster_rows:
        items.append(
            ActionItem(
                clinic_id="cluster_mitaka",
                clinic_name="三鷹クラスター（石神井・ひばり・三鷹・調布・府中・高円寺）",
                decision="やる",
                priority="高",
                rationale=(
                    "8km圏が相互に大きく重複。院別市場の単純比較ではなく、"
                    "排他的居宅市場での役割分担が必要。"
                ),
                actions=[
                    "排他的居宅市場が大きい院を居宅の主担当エリアとする",
                    "重複メッシュでは施設契約と居宅の役割を院間で明文化する",
                    "新規居宅案件の一次受付ルール（最寄り院優先）を定める",
                ],
                kpis=[
                    "クラスター合算の居宅獲得率（ユニオン分母）",
                    "院別排他的居宅市場に対する実績比",
                ],
                dont=[
                    "重複圏で居宅ノルマを院ごとに独立設定する（カニバリを招く）",
                ],
            )
        )
    return items


def _decide(
    r: ClinicMarketRow,
    fac_pct: float | None,
    mitaka_cluster: set[str],
) -> tuple[str, str, str, list[str], list[str], list[str]]:
    if r.id == "urawa":
        return (
            "様子見",
            "中",
            "開院直後。獲得率の低さは立ち上がり要因であり、期待帯との差は経過観察。",
            [
                "3/6/12か月の居宅獲得率軌跡を固定フォーマットで追跡する",
                "5kmコア圏の居宅リスト化と初期紹介経路の整備",
                "施設契約は無理に伸ばさず、居宅の型を先に作る",
            ],
            [
                "居宅獲得率（5km/8km）の月次",
                "新規居宅患者数/月",
                "排他的居宅市場に対する実績比",
            ],
            ["開院直後に施設偏重へ舵を切る", "8km市場規模そのものを短期KPIにする"],
        )

    if r.id == "ichikawa":
        return (
            "やる",
            "高",
            f"居宅獲得率 {r.home_capture_pct}% が期待帯 {r.expected_share_low_pct}–{r.expected_share_high_pct}% を下回る。",
            [
                "居宅未開拓エリア（排他的メッシュ）の訪問リストを作る",
                "紹介元（居宅介護支援・訪問看護）のカバレッジ点検",
                "5kmコアの獲得率を先行KPIにし、8kmは監視指標とする",
            ],
            [
                "居宅獲得率（期待帯との差）",
                "新規居宅/月",
                "紹介元別の新規件数",
            ],
            ["施設市場需要とのシェア比較で評価する", "半径だけ広げて市場を水増し解釈する"],
        )

    if r.capture_vs_band == "above":
        return (
            "横展開",
            "高",
            f"居宅獲得率 {r.home_capture_pct}% が期待帯上限超え。強い獲得パターンの抽出対象。",
            [
                "居宅獲得の成功要因（紹介経路・営業範囲・人員配置）を文書化する",
                "類似密度帯の低シェア院へ横展開可能な型を切り出す",
                "5kmコアの高獲得が維持されているか感度表で確認する",
            ],
            [
                "5km/8km獲得率",
                "居宅新規の継続率",
                "パネル内居宅比率",
            ],
            ["成功院の絶対患者数を、密度の違う院にそのまま目標転記する"],
        )

    if r.id in mitaka_cluster:
        return (
            "やる",
            "中",
            (
                f"{r.density_tier}・グループ近接{r.sibling_clinics_in_radius}院。"
                f"排他的居宅市場≈{r.exclusive_market_home:,.0f} を院KPIの母数にする。"
            ),
            [
                "排他的居宅市場を院別目標の母数に切り替える",
                "クラスター役割分担表に当該院の主エリアを記入する",
                "施設パネル構成比が高い場合は居宅の時間配分を見直す",
            ],
            [
                "排他的居宅市場に対する実績比",
                "施設/パネル構成比",
                "グループ他院との重複案件数",
            ],
            ["重複する単純8km市場規模で院間ランキングする"],
        )

    # 標準（帯内）
    decision = "様子見"
    priority = "低"
    rationale = (
        f"居宅獲得率は期待帯内（{r.home_capture_pct}% / "
        f"{r.expected_share_low_pct}–{r.expected_share_high_pct}%）。現状維持モニタリング。"
    )
    actions = [
        "四半期ごとに獲得率と期待帯の位置を確認する",
        "施設契約KPIはパネル構成比で別管理する",
    ]
    if fac_pct is not None and fac_pct >= 70:
        actions.append("施設偏重（パネル≥70%）のため、居宅新規の下限件数を設定する")
        priority = "中"
        decision = "やる"
        rationale += " ただし施設偏重が強い。"
    kpis = [
        "居宅獲得率（8km）",
        "施設/パネル構成比",
        "排他的居宅市場比",
    ]
    dont = ["市場規模の増減だけで院の優劣を決める"]
    return decision, priority, rationale, actions, kpis, dont


def format_action_sheets(items: list[ActionItem]) -> str:
    lines = ["=" * 90, "院別アクションシート（本部意思決定）", "=" * 90, ""]
    order = {"やる": 0, "横展開": 1, "様子見": 2, "やらない": 3}
    for it in sorted(items, key=lambda x: (order.get(x.decision, 9), x.priority, x.clinic_name)):
        lines.append(f"■ {it.clinic_name}  【{it.decision}】優先度:{it.priority}")
        lines.append(f"  理由: {it.rationale}")
        lines.append("  やる:")
        for a in it.actions:
            lines.append(f"    - {a}")
        lines.append("  KPI:")
        for k in it.kpis:
            lines.append(f"    - {k}")
        lines.append("  やらない:")
        for d in it.dont:
            lines.append(f"    - {d}")
        lines.append("")
    lines.append("=" * 90)
    return "\n".join(lines)


def action_sheets_to_dicts(items: list[ActionItem]) -> list[dict[str, Any]]:
    return [asdict(x) for x in items]
