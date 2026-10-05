// 理事長面談スライドを生成する（機密: 出力は analysis/confidential/briefing/ のみ）
//   python3 briefing/build_all.py && python3 briefing/deck/export_deck_data.py
//   NODE_PATH=<pptxgenjs の node_modules> node briefing/deck/build_deck.js
const path = require("path");
const fs = require("fs");
const pptxgen = require("pptxgenjs");

const ROOT = path.resolve(__dirname, "../..");
const CONF = path.join(ROOT, "analysis/confidential/briefing");
const PUB = path.join(ROOT, "briefing/output");
const D = JSON.parse(fs.readFileSync(path.join(CONF, "deck_data.json"), "utf8"));
const OUT = path.join(CONF, "わかさ_理事長面談資料_2026-10.pptx");
const APPLY_THEME = process.env.PPTX_APPLY_THEME;

const THEME = {
  name: "Wakasa Briefing",
  headFontFace: "Yu Gothic",
  bodyFontFace: "Yu Gothic",
  colors: {
    dk1: "1A1A1A", lt1: "FFFFFF", dk2: "0F2D4A", lt2: "EEF3F8",
    accent1: "2A78D6", accent2: "EB6834", accent3: "1BAF7A", accent4: "0D366B",
    accent5: "8A8985", accent6: "CDE2FB", hlink: "2A78D6", folHlink: "4A3AA7",
  },
};
const HEX = THEME.colors;
const W = 13.333, H = 7.5, MX = 0.6;

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "訪問診療データ分析のご報告";
pres.author = "わかさクリニックグループ";
const C = pres.SchemeColor;
const FOOTER = "機密｜わかさクリニックグループ 理事長面談資料｜2026年10月（実績は2026年7月時点）";

// ---------------------------------------------------------------- layouts
pres.defineSlideMaster({
  title: "TITLE_DARK",
  background: { color: HEX.dk2 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: MX, y: 2.2, w: 11.5, h: 1.6, fontSize: 40, bold: true, color: C.background1, valign: "bottom", align: "left", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: MX, y: 4.0, w: 11.5, h: 1.6, fontSize: 18, color: C.accent6, valign: "top", align: "left", margin: 0 }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "CLOSING",
  background: { color: HEX.dk2 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: MX, y: 0.8, w: 11.5, h: 1.0, fontSize: 36, bold: true, color: C.background1, valign: "middle", align: "left", margin: 0 }, text: "" } },
  ],
  slideNumber: { x: W - 1.0, y: H - 0.45, w: 0.5, h: 0.3, fontSize: 10, color: HEX.accent6 },
});
pres.defineSlideMaster({
  title: "SECTION",
  background: { color: HEX.dk2 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: MX, y: 2.6, w: 11.5, h: 1.2, fontSize: 36, bold: true, color: C.background1, valign: "bottom", align: "left", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: MX, y: 4.0, w: 11.5, h: 1.2, fontSize: 16, color: C.accent6, valign: "top", align: "left", margin: 0 }, text: "" } },
  ],
  slideNumber: { x: W - 1.0, y: H - 0.45, w: 0.5, h: 0.3, fontSize: 10, color: HEX.accent6 },
});
pres.defineSlideMaster({
  title: "CONTENT",
  background: { color: HEX.lt1 },
  margin: [0.5, 0.6, 0.6, 0.6],
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: MX, y: 0.35, w: W - 2 * MX, h: 0.85, fontSize: 26, bold: true, color: C.text2, valign: "middle", align: "left", margin: 0 }, text: "" } },
    { text: { text: FOOTER, options: { x: MX, y: H - 0.45, w: 10, h: 0.3, fontSize: 10, color: HEX.accent5, margin: 0 } } },
  ],
  slideNumber: { x: W - 1.0, y: H - 0.45, w: 0.5, h: 0.3, fontSize: 10, color: HEX.accent5 },
});

let section = "";
function content(title, sectionTitle) {
  const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: sectionTitle || section });
  s.addText(title, { placeholder: "title" });
  return s;
}
function sectionSlide(title, sub) {
  section = title;
  pres.addSection({ title });
  const s = pres.addSlide({ masterName: "SECTION", sectionTitle: title });
  s.addText(title, { placeholder: "title" });
  if (sub) s.addText(sub, { placeholder: "body" });
  return s;
}
function txt(s, text, o) {
  s.addText(text, Object.assign({ isTextBox: true, fontSize: 14, color: C.text1, margin: 0, valign: "top" }, o));
}
function card(s, x, y, w, h, name, fill) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, fill: { color: fill || C.background2 }, line: { type: "none" }, rectRadius: 0.08, objectName: name });
}
function bullets(items, o) {
  return items.map((t, i) => ({ text: t, options: Object.assign({ bullet: true, breakLine: i < items.length - 1, paraSpaceAfter: 6 }, o || {}) }));
}
function img(s, file, x, y, maxW, maxH, pxW, pxH, name) {
  const r = pxW / pxH;
  let w = maxW, h = maxW / r;
  if (h > maxH) { h = maxH; w = maxH * r; }
  s.addImage({ path: file, x, y, w, h, objectName: name });
  return { w, h };
}
const fmt = (n) => Math.round(n).toLocaleString("ja-JP");
const pct = (x) => `${Math.round(x * 100)}%`;
const clinics = D.clinics;
const byId = Object.fromEntries(clinics.map((c) => [c.id, c]));
const judged = clinics.filter((c) => c.months >= 12 && c.id !== "honin");
const tight = clinics.filter((c) => c.per_fte >= 250);
const maxPen = Math.max(...judged.map((c) => c.penetration));

// ---------------------------------------------------------------- 1. 表紙
pres.addSection({ title: "表紙" });
{
  const s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "表紙" });
  s.addText("訪問診療データ分析のご報告", { placeholder: "title" });
  s.addText([
    { text: "患者獲得の予測指数と、各院の運営・出店への活用", options: { breakLine: true } },
    { text: "2026年10月　理事長面談資料（機密）", options: { fontSize: 14 } },
  ], { placeholder: "body" });
}

// ---------------------------------------------------------------- 2. 要旨
pres.addSection({ title: "要旨" });
{
  const s = content("本日お伝えしたいこと：差の大半は地域と年数で説明でき、次の伸びは「出店先」と「医師」で決まる", "要旨");
  const r2 = Math.round(D.model.r2 * 100);
  const items = [
    [`${r2}%`, "院ごとの居宅患者数の差は「在宅開始からの年数」「地域の未充足度」「立ち上げ方針」の3つで説明できる"],
    ["約3倍", "在宅医療がまだ行き渡っていない埼玉・千葉では、同じ年数でも東京の約3倍伸びる"],
    [pct(maxPen), "判定できる院の到達率は最大でもこの水準。全院が地域の到達目安の半分未満で、市場の上限に当たっている院はない"],
    [`${tight.length}院`, "医師1人あたり250人を超える院。次の伸びを止めるのは市場より医師の可能性が高い"],
  ];
  const cw = (W - 2 * MX - 3 * 0.3) / 4;
  items.forEach(([big, label], i) => {
    const x = MX + i * (cw + 0.3);
    card(s, x, 1.55, cw, 3.3, `要旨カード${i + 1}`);
    txt(s, big, { x: x + 0.3, y: 1.85, w: cw - 0.6, h: 1.0, fontSize: 40, bold: true, color: i === 3 ? C.accent2 : C.accent1, fontFace: "Yu Gothic" });
    txt(s, label, { x: x + 0.3, y: 3.0, w: cw - 0.6, h: 1.7, fontSize: 15 });
  });
  txt(s, "ご提案", { x: MX, y: 5.2, w: 2, h: 0.4, fontSize: 16, bold: true, color: C.text2 });
  s.addText(bullets([
    "院の評価は「年数・地域補正後の実力」で行い、本当に支援が要る院に絞る",
    "次の出店は埼玉東部・千葉北西部（未充足度2倍超・競合が薄い・既存院と重ならない）を軸に検討する",
    "院別の月次患者数をいただければ、各院の「上限」を成長曲線から確定できる",
  ]), { x: MX, y: 5.6, w: W - 2 * MX, h: 1.3, fontSize: 15, color: C.text1, margin: 0, isTextBox: true, valign: "top" });
}

// ---------------------------------------------------------------- 3. データ
sectionSlide("1. 現在保有しているデータ", "公的統計9種＋院内データ。信頼度と、まだ無いデータも合わせて整理しました");
{
  const s = content("保有データの全体像：公的統計で「需要」と「競合」を、院内実績で「成果」を測っている");
  const cols = [
    ["需要（どれだけ患者が生まれるか）", C.accent1, ["国勢調査 250mメッシュ人口（2020）", "社人研 将来推計人口（2025）", "NDB 在宅医療の受療率（年齢・県別）", "NDB 居宅/施設の比率", "総務省 人口推計"]],
    ["競合・施設（誰と取り合うか）", C.accent1, ["厚生局 在支診・在支病名簿（2026-06）", "JMAP 在支診点データ（機能強化型）", "医療施設調査（2023）", "介護施設 7,790か所・定員40万人"]],
    ["院内（機密）", C.accent2, ["院別 居宅・施設患者数（2026-07）", "院別 医師FTE", "開院日・立ち上げ時期", "浦和の立ち上げ推移", "【今後】院別の月次患者数"]],
    ["まだ無いデータ", C.accent5, ["居宅介護支援事業所（CM）の所在地", "訪問看護ステーションの所在地", "将来推計人口 2030〜2050年", "紹介元別の新規患者数", "施設の契約リスト"]],
  ];
  const cw = (W - 2 * MX - 3 * 0.3) / 4;
  cols.forEach(([head, col, items], i) => {
    const x = MX + i * (cw + 0.3);
    card(s, x, 1.5, cw, 4.6, `データ区分${i + 1}`);
    s.addShape(pres.shapes.OVAL, { x: x + 0.3, y: 1.8, w: 0.32, h: 0.32, fill: { color: col }, line: { type: "none" }, objectName: `区分マーク${i + 1}` });
    txt(s, head, { x: x + 0.75, y: 1.75, w: cw - 1.0, h: 0.75, fontSize: 15, bold: true, color: C.text2 });
    s.addText(bullets(items), { x: x + 0.3, y: 2.65, w: cw - 0.55, h: 3.3, fontSize: 14, color: C.text1, margin: 0, isTextBox: true, valign: "top" });
  });
  txt(s, "詳細（出典・時点・格納場所・信頼度）は付録「01 データカタログ」。生データは Excel（wakasa_briefing_data.xlsx）でもご覧いただけます", { x: MX, y: 6.35, w: W - 2 * MX, h: 0.5, fontSize: 12, color: C.accent5 });
}
{
  const s = content("これまでの指数を整理し、公式に使う指数を絞りました");
  const cols = [
    ["公式に使う", C.accent1, ["未充足度（潜在÷顕在の居宅需要）", "年数・地域補正後の実力", "到達目安・到達率", "排他率（グループ重複の少なさ）", "実効競合・競合密度", "居宅比率・医師1人あたり患者数", "立地スコア・3年後予測"]],
    ["参考に見る", C.accent5, ["顕在居宅需要（旧・居宅市場規模）", "居宅獲得率", "公平シェアKPI・実務KPI", "収益指数（施設0.4換算）", "ユニオン市場"]],
    ["使わない", C.accent2, ["努力指数・成果スコア（手入力の人口に誤り）", "推定居宅需要＝高齢者×4.5%", "期待獲得率帯（閾値に根拠がない）", "CM拠点あたり居宅数（CM数が概数）"]],
  ];
  const cw = (W - 2 * MX - 2 * 0.3) / 3;
  cols.forEach(([head, col, items], i) => {
    const x = MX + i * (cw + 0.3);
    card(s, x, 1.5, cw, 4.75, `指数区分${i + 1}`);
    s.addShape(pres.shapes.OVAL, { x: x + 0.3, y: 1.8, w: 0.32, h: 0.32, fill: { color: col }, line: { type: "none" }, objectName: `指数マーク${i + 1}` });
    txt(s, head, { x: x + 0.75, y: 1.75, w: cw - 1, h: 0.45, fontSize: 18, bold: true, color: C.text2 });
    s.addText(bullets(items), { x: x + 0.3, y: 2.45, w: cw - 0.55, h: 3.7, fontSize: 14, color: C.text1, margin: 0, isTextBox: true, valign: "top" });
  });
  txt(s, "定義と判断理由は付録「02 指数辞書」", { x: MX, y: 6.45, w: W - 2 * MX, h: 0.4, fontSize: 12, color: C.accent5 });
}
{
  const s = content("検証の過程で過去の分析の誤りを5点見つけ、すべて修正しました");
  const rows = [
    ["自治体データ（手入力）の誤り", "57件中20件が公式推計と10〜15%超ずれ（入間市の人口が半分など）", "公的原典ベースに一本化"],
    ["院の位置のずれ", "本院3.8km・三鷹2.4km・所沢1.3km・市川1.2km", "国土地理院の住所検索に差し替え"],
    ["機能強化型の判定漏れ", "名簿の全角数字を読めず、全件「従来型」扱い", "判定を修正し自動テストを追加"],
    ["県境での需要のずれ", "圏全体に1県の受療率を適用（本院・所沢・市川で±20〜60%）", "メッシュごとに所在県の率を適用"],
    ["競合の座標欠落", "在支診の36%に位置情報なし", "名簿突合で79%まで回復＋県別補正"],
  ];
  const head = ["問題", "影響", "対応"].map((t) => ({ text: t, options: { bold: true, color: HEX.lt1, fill: { color: HEX.dk2 } } }));
  s.addTable([head, ...rows.map((r) => r.map((t) => ({ text: t })))], {
    x: MX, y: 1.55, w: W - 2 * MX, colW: [3.0, 5.6, 3.53], fontSize: 14, color: HEX.dk1,
    border: { type: "solid", pt: 0.75, color: "D9DEE5" }, rowH: 0.62, valign: "middle", margin: 0.08, fontFace: "Yu Gothic",
  });
  txt(s, "結果として、院ごとの市場規模や獲得率の数字は過去資料から変わっています。今後は本資料の数値を基準とします", { x: MX, y: 5.6, w: W - 2 * MX, h: 0.6, fontSize: 15, color: C.text2, bold: true });
}

// ---------------------------------------------------------------- 4. 予測指数
sectionSlide("2. 患者獲得の予測指数", "13種類の候補を、12院の実績で比べました");
{
  const s = content("「人が多い所」ではなく「まだ取られていない所」が伸びる：未充足度が最も効く指数");
  const sc = D.screen;
  const labels = sc.map((r) => r["モデル"].replace("【採用】", "（採用）"));
  const vals = sc.map((r) => Math.round(r["予測誤差(LOO)"] * 100));
  const colors = sc.map((r) => (r["モデル"].includes("採用") ? HEX.accent2 : r["モデル"].includes("未充足度") ? HEX.accent1 : "9EC5F4"));
  s.addChart(pres.charts.BAR, [{ name: "予測誤差(%)", labels: labels.slice().reverse(), values: vals.slice().reverse() }], {
    x: MX, y: 1.4, w: 7.6, h: 5.4, barDir: "bar", chartColors: colors.slice().reverse(),
    showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: '0"%"', dataLabelFontSize: 11, dataLabelColor: HEX.dk1,
    catAxisLabelFontSize: 11, valAxisLabelFontSize: 10, catAxisLabelColor: HEX.dk1, valAxisLabelColor: HEX.accent5,
    catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt", dataLabelFontFace: "+mn-lt",
    valGridLine: { color: "E6E5E1", size: 0.75 }, catGridLine: { style: "none" }, valAxisMaxVal: 90, valAxisMinVal: 0,
    showLegend: false, showTitle: true, title: "1院ずつ抜いて予測したときの誤差（小さいほど良い）", titleFontSize: 12, titleColor: HEX.dk1, titleFontFace: "+mn-lt",
    barGapWidthPct: 40,
  });
  const x = 8.6;
  card(s, x, 1.5, W - MX - x, 5.25, "比較の読み方");
  txt(s, "読み方", { x: x + 0.3, y: 1.75, w: 3.8, h: 0.4, fontSize: 16, bold: true, color: C.text2 });
  s.addText(bullets([
    "高齢者数・需要・競合の「量」は、多いほど居宅が少ない（都会度を測っているだけ）",
    "未充足度を加えると誤差が±65%→±34%に半減",
    `さらに立ち上げ方針（開院時期）を加えると±${Math.round(D.model.loo_error_pct)}%、R²=${D.model.r2.toFixed(2)}`,
    "施設重視期に開院した院は、同じ条件で居宅が約4割少ない",
  ]), { x: x + 0.3, y: 2.25, w: W - MX - x - 0.6, h: 4.3, fontSize: 14, color: C.text1, margin: 0, isTextBox: true, valign: "top" });
}
{
  const s = content(`予測モデルの当てはまり：12院中11院が誤差±${Math.round(D.model.loo_error_pct)}%の帯に入る`);
  const im = img(s, path.join(CONF, "figures/slide/fig_model_fit.png"), MX, 1.35, 7.4, 5.5, 1720, 1280, "モデル当てはまり図");
  const x = MX + im.w + 0.4;
  card(s, x, 1.5, W - MX - x, 5.25, "モデル説明");
  txt(s, "モデルの中身", { x: x + 0.3, y: 1.75, w: 3.8, h: 0.4, fontSize: 16, bold: true, color: C.text2 });
  s.addText(bullets([
    "年数が2倍になると居宅は約1.7倍",
    "未充足度2.0の地域は1.0の地域の約2.9倍",
    "施設重視期に開院した院は約44%少ない",
    "斜線より大きく上の院（西日暮里・所沢）は、地域と年数の割に多く取れている",
    "12院の横断データなので「強い傾向」として扱い、月次データで検証を続ける",
  ]), { x: x + 0.3, y: 2.25, w: W - MX - x - 0.6, h: 4.4, fontSize: 14, color: C.text1, margin: 0, isTextBox: true, valign: "top" });
}
{
  const s = content("有用な患者獲得予測指数として、次の5つを採用します");
  const rows = [
    ["1", "未充足度", "潜在居宅需要（東京都並みに普及した場合）÷ 現在の居宅需要", "出店地の選定・既存院の伸びしろ"],
    ["2", "在宅開始からの月数", "同じ地域条件なら、月数でおおむね伸び方が決まる", "立ち上げ基準カーブ"],
    ["3", "立ち上げ方針（開院時期）", "居宅重視で立ち上げた院は約1.8倍", "新規院はすべて居宅重視で"],
    ["4", "排他率", "圏内高齢者のうち、自院が一番近い人の割合", "出店時の食い合いチェック・役割分担"],
    ["5", "競合密度", "75歳以上1万人あたりの実効競合（機能強化型を重く）", "到達目安の補正・都内の候補比較"],
  ];
  rows.forEach(([n, name, def, use], i) => {
    const y = 1.5 + i * 1.0;
    s.addShape(pres.shapes.OVAL, { x: MX, y: y + 0.1, w: 0.6, h: 0.6, fill: { color: i < 3 ? C.accent1 : C.accent6 }, line: { type: "none" }, objectName: `番号${n}` });
    txt(s, n, { x: MX, y: y + 0.1, w: 0.6, h: 0.6, fontSize: 18, bold: true, color: i < 3 ? C.background1 : C.text2, align: "center", valign: "middle" });
    txt(s, name, { x: MX + 0.9, y: y + 0.12, w: 3.2, h: 0.55, fontSize: 18, bold: true, color: C.text2, valign: "middle" });
    txt(s, def, { x: MX + 4.2, y: y + 0.12, w: 5.0, h: 0.6, fontSize: 14, valign: "middle" });
    txt(s, use, { x: MX + 9.4, y: y + 0.12, w: W - 2 * MX - 9.4, h: 0.6, fontSize: 14, color: C.accent1, bold: true, valign: "middle" });
  });
}

// ---------------------------------------------------------------- 5. 既存院
sectionSlide("3. 既存院の診断", "上限に近いのか、まだ伸ばせるのか");
{
  const s = content("院別の診断：判定できる院はすべて「伸長余地あり」、課題は院ごとに異なる");
  const head = ["院", "在宅\n月数", "居宅", "施設", "居宅比", "医師1人\nあたり", "実力", "到達率", "判定"].map((t) => ({ text: t, options: { bold: true, color: HEX.lt1, fill: { color: HEX.dk2 }, align: "center" } }));
  const body = clinics.map((c) => {
    const warnFte = c.per_fte >= 250;
    const warnMix = c.home_mix < 0.3;
    const perfCol = c.months < 6 ? HEX.dk1 : c.perf >= 1.15 ? HEX.accent1 : c.perf <= 0.85 ? HEX.accent2 : HEX.dk1;
    const verdictShort = c.verdict.replace("（月次推移で判定）", "").replace("（判定保留）", "");
    return [
      { text: c.name, options: { bold: true } },
      { text: String(c.months), options: { align: "right" } },
      { text: fmt(c.home), options: { align: "right" } },
      { text: fmt(c.facility), options: { align: "right" } },
      { text: pct(c.home_mix), options: { align: "right", color: warnMix ? HEX.accent2 : HEX.dk1, bold: warnMix } },
      { text: fmt(c.per_fte), options: { align: "right", color: warnFte ? HEX.accent2 : HEX.dk1, bold: warnFte } },
      { text: c.months >= 6 ? c.perf.toFixed(2) : "—", options: { align: "right", color: perfCol, bold: perfCol !== HEX.dk1 } },
      { text: c.months >= 12 && c.id !== "honin" ? pct(c.penetration) : "—", options: { align: "right" } },
      { text: verdictShort },
    ];
  });
  s.addTable([head, ...body], {
    x: MX, y: 1.35, w: W - 2 * MX, colW: [1.55, 0.8, 0.85, 0.85, 0.9, 1.0, 0.8, 0.9, 4.48],
    fontSize: 12, color: HEX.dk1, border: { type: "solid", pt: 0.5, color: "D9DEE5" }, rowH: 0.34, valign: "middle", margin: [0.02, 0.08, 0.02, 0.08], fontFace: "Yu Gothic",
  });
  txt(s, "実力＝実績÷モデル期待値（1.15以上を青、0.85以下を橙）／到達率＝実績÷到達目安／橙字＝居宅比30%未満・医師1人あたり250人以上。本院は到達目安の基準のため到達率なし。在宅月数は本院2014-04・所沢2021-06を仮置き", { x: MX, y: 6.35, w: W - 2 * MX, h: 0.6, fontSize: 11, color: C.accent5 });
}
{
  const s = content("地域の到達目安から見ると、どの院もまだ半分未満：「上限」に当たっている院はない");
  const im = img(s, path.join(CONF, "figures/slide/fig_saturation.png"), MX, 1.3, 8.4, 5.6, 1920, 1240, "到達目安図");
  const x = MX + im.w + 0.35;
  card(s, x, 1.5, W - MX - x, 5.25, "到達目安の説明");
  txt(s, "到達目安とは", { x: x + 0.25, y: 1.75, w: 3, h: 0.4, fontSize: 16, bold: true, color: C.text2 });
  s.addText(bullets([
    "本院が14年かけて達成した浸透率（自院が最寄りの潜在需要の約19%）を、競合の厚さで割り引いて各院に当てはめた量",
    "所沢・津田沼が4割台で先行",
    "上限の確定は、月次データで「伸びの鈍化」を確認してから",
  ]), { x: x + 0.25, y: 2.25, w: W - MX - x - 0.45, h: 4.4, fontSize: 14, color: C.text1, margin: 0, isTextBox: true, valign: "top" });
}
{
  const s = content(`次の制約は医師：${tight.length}院で医師1人あたり250人を超えている`);
  const sorted = clinics.slice().sort((a, b) => b.per_fte - a.per_fte);
  s.addChart(pres.charts.BAR, [{ name: "医師1人あたり患者数", labels: sorted.map((c) => c.name), values: sorted.map((c) => Math.round(c.per_fte)) }], {
    x: MX, y: 1.4, w: 7.8, h: 5.4, barDir: "bar", chartColors: sorted.map((c) => (c.per_fte >= 250 ? HEX.accent2 : HEX.accent1)),
    showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 11, dataLabelColor: HEX.dk1, dataLabelFontFace: "+mn-lt",
    catAxisLabelFontSize: 12, valAxisLabelFontSize: 10, catAxisLabelColor: HEX.dk1, valAxisLabelColor: HEX.accent5,
    catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt", catAxisOrientation: "maxMin",
    valGridLine: { color: "E6E5E1", size: 0.75 }, catGridLine: { style: "none" }, valAxisMinVal: 0, valAxisMaxVal: 350,
    showLegend: false, showTitle: true, title: "医師1人（常勤換算）あたり患者数（居宅＋施設）　橙＝250人以上", titleFontSize: 12, titleColor: HEX.dk1, titleFontFace: "+mn-lt", barGapWidthPct: 40,
  });
  const x = 8.8;
  card(s, x, 1.5, W - MX - x, 5.25, "医師キャパの示唆");
  txt(s, "示唆", { x: x + 0.3, y: 1.75, w: 3, h: 0.4, fontSize: 16, bold: true, color: C.text2 });
  s.addText(bullets([
    `${tight.map((c) => c.name).join("・")}は、伸びしろがあっても医師が先に詰まる`,
    "到達率が低く医師が詰まっている院から、医師増員の優先順位を付ける",
    "到達率が高い院は、増員より隣接エリアへの出店（分院化）が効く",
  ]), { x: x + 0.3, y: 2.25, w: W - MX - x - 0.6, h: 4.4, fontSize: 14, color: C.text1, margin: 0, isTextBox: true, valign: "top" });
}
{
  const s = content("多摩〜区西部の4院は、圏内の半分以上で別のわかさ院のほうが近い：役割分担が論点");
  const sorted = clinics.slice().sort((a, b) => a.exclusive_ratio - b.exclusive_ratio);
  s.addChart(pres.charts.BAR, [{ name: "排他率", labels: sorted.map((c) => c.name), values: sorted.map((c) => Math.round(c.exclusive_ratio * 100)) }], {
    x: MX, y: 1.4, w: 7.8, h: 5.4, barDir: "bar", chartColors: sorted.map((c) => (c.exclusive_ratio < 0.5 ? HEX.accent2 : HEX.accent1)),
    showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: '0"%"', dataLabelFontSize: 11, dataLabelColor: HEX.dk1, dataLabelFontFace: "+mn-lt",
    catAxisLabelFontSize: 12, valAxisLabelFontSize: 10, catAxisLabelColor: HEX.dk1, valAxisLabelColor: HEX.accent5,
    catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt", catAxisOrientation: "maxMin",
    valGridLine: { color: "E6E5E1", size: 0.75 }, catGridLine: { style: "none" }, valAxisMinVal: 0, valAxisMaxVal: 110,
    showLegend: false, showTitle: true, title: "排他率：8km圏の高齢者のうち自院が一番近い人の割合（橙＝50%未満）", titleFontSize: 12, titleColor: HEX.dk1, titleFontFace: "+mn-lt", barGapWidthPct: 40,
  });
  const x = 8.8;
  card(s, x, 1.5, W - MX - x, 5.25, "重複の示唆");
  txt(s, "示唆", { x: x + 0.3, y: 1.75, w: 3, h: 0.4, fontSize: 16, bold: true, color: C.text2 });
  s.addText(bullets([
    "同じCM事業所に複数院が営業する重複を解消する",
    "最寄り院の地図をもとに新規受付・営業の担当エリアを決める",
    "空いた営業資源を未開拓エリア（例：ひばりが丘北側の東久留米・清瀬）へ",
  ]), { x: x + 0.3, y: 2.25, w: W - MX - x - 0.6, h: 4.4, fontSize: 14, color: C.text1, margin: 0, isTextBox: true, valign: "top" });
}

// ---------------------------------------------------------------- 6. 出店
sectionSlide("4. 出店と立ち上げ", "どこに出すと伸びるか、出した後に順調かをどう判定するか");
{
  const s = content("在宅医療の未充足度：埼玉・千葉は東京都並みに普及した場合の2倍超の需要が眠っている");
  img(s, path.join(CONF, "figures/slide/fig_map_underserved.png"), MX + 0.4, 1.25, W - 2 * MX - 0.8, 5.7, 2000, 1440, "未充足度マップ");
}
{
  const s = content("出店候補：上位は埼玉東部〜千葉北西部、いずれも既存院から16km以上離れ食い合いがない");
  img(s, path.join(CONF, "figures/slide/fig_map_site_score.png"), MX, 1.25, W - 2 * MX, 5.75, 2520, 1440, "立地スコアマップ");
}
{
  const s = content("立ち上げ基準カーブ：新規院が「順調か」を開院直後から月数で判定する");
  const im = img(s, path.join(CONF, "figures/slide/fig_growth_curves.png"), MX, 1.3, 8.4, 5.6, 1920, 1240, "立ち上げカーブ図");
  const x = MX + im.w + 0.35;
  card(s, x, 1.5, W - MX - x, 5.25, "立ち上げ管理ルール");
  txt(s, "運用ルール案", { x: x + 0.25, y: 1.75, w: 3, h: 0.4, fontSize: 16, bold: true, color: C.text2 });
  s.addText(bullets([
    "地域の未充足度に応じた基準線と毎月比べる",
    "3・6・12か月で基準の70%未満なら本部が立ち上げ支援に入る",
    `最初の対象：浦和（未充足度${byId.urawa.underserved.toFixed(1)}＝グループ最高）、市川`,
  ]), { x: x + 0.25, y: 2.25, w: W - MX - x - 0.45, h: 4.4, fontSize: 14, color: C.text1, margin: 0, isTextBox: true, valign: "top" });
}

// ---------------------------------------------------------------- 7. 活用提案
sectionSlide("5. 活用のご提案", "データを意思決定の道具として定着させる");
{
  const s = content("このデータで、評価・出店・人員配置・立ち上げ管理を同じ物差しで判断できるようになります");
  const items = [
    ["院の公平な評価", "「実力」指数を四半期の評価会議の最初の資料に"],
    ["出店先の選定", "候補住所を入れれば3年後予測と食い合いを即比較"],
    ["立ち上げ管理", "基準カーブで3・6・12か月に判定"],
    ["医師配置・採用", "到達率×医師1人あたり患者数で優先順位"],
    ["多摩の役割分担", "最寄り院の地図で営業エリアを決める"],
    ["居宅への構成転換", "施設偏重院は新規居宅を月次目標に"],
    ["紹介経路の診断", "紹介元別の新規データで弱い経路を特定（要データ）"],
    ["10年後の需要", "将来推計人口で院ごとの増減を先読み（要データ）"],
  ];
  const cw = (W - 2 * MX - 3 * 0.3) / 4, ch = 2.35;
  items.forEach(([head, body], i) => {
    const x = MX + (i % 4) * (cw + 0.3), y = 1.45 + Math.floor(i / 4) * (ch + 0.3);
    card(s, x, y, cw, ch, `活用${i + 1}`);
    s.addShape(pres.shapes.OVAL, { x: x + 0.3, y: y + 0.3, w: 0.5, h: 0.5, fill: { color: i < 6 ? C.accent1 : C.accent5 }, line: { type: "none" }, objectName: `活用番号${i + 1}` });
    txt(s, String(i + 1), { x: x + 0.3, y: y + 0.3, w: 0.5, h: 0.5, fontSize: 16, bold: true, color: C.background1, align: "center", valign: "middle" });
    txt(s, head, { x: x + 0.95, y: y + 0.3, w: cw - 1.2, h: 0.5, fontSize: 16, bold: true, color: C.text2, valign: "middle" });
    txt(s, body, { x: x + 0.3, y: y + 1.0, w: cw - 0.6, h: ch - 1.2, fontSize: 14 });
  });
}
pres.addSection({ title: "お願いと次のステップ" });
{
  const s = pres.addSlide({ masterName: "CLOSING", sectionTitle: "お願いと次のステップ" });
  s.addText("お願いしたいことと次のステップ", { placeholder: "title" });
  const asks = [
    ["院別の月次患者数（開院〜現在）", "各院の「上限」を成長曲線から確定"],
    ["紹介元別の新規患者数", "院ごとの弱い紹介経路を特定"],
    ["出店候補物件の住所", "その場で3年後予測・食い合いを比較"],
    ["評価会議での「実力」指数の試行", "四半期ごとに更新（再計算は約40秒）"],
  ];
  asks.forEach(([a, b], i) => {
    const y = 2.3 + i * 0.95;
    s.addShape(pres.shapes.OVAL, { x: MX, y: y + 0.08, w: 0.42, h: 0.42, fill: { color: C.accent2 }, line: { type: "none" }, objectName: `お願い${i + 1}` });
    txt(s, String(i + 1), { x: MX, y: y + 0.08, w: 0.42, h: 0.42, fontSize: 14, bold: true, color: C.background1, align: "center", valign: "middle" });
    txt(s, a, { x: MX + 0.65, y: y + 0.05, w: 5.4, h: 0.5, fontSize: 18, bold: true, color: C.background1, valign: "middle" });
    txt(s, `→ ${b}`, { x: MX + 6.2, y: y + 0.05, w: 6.0, h: 0.5, fontSize: 16, color: C.accent6, valign: "middle" });
  });
  txt(s, "いただいたデータは機密として院内環境でのみ扱い、共有リポジトリには保存しません", { x: MX, y: 6.2, w: 11.5, h: 0.4, fontSize: 14, color: C.accent6 });
}

pres.writeFile({ fileName: OUT }).then(async (f) => {
  if (APPLY_THEME) {
    const { applyTheme } = require(APPLY_THEME);
    await applyTheme(f, THEME);
  }
  console.log(f);
});
