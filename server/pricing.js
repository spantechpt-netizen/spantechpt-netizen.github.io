import { CURRENCY_WORDS } from './templates.js';

export const round2 = (n) => Math.round((Number(n) + Number.EPSILON) * 100) / 100;

/**
 * Recomputes every derived money field of a quotation from its items and
 * cost inputs. The client never sends totals — they are always produced here.
 */
export function computeTotals(quote, items) {
  const billable = items.filter((item) => !item.is_optional);

  const priced = items.map((item) => ({
    ...item,
    amount: round2(Number(item.qty || 0) * Number(item.unit_price || 0)),
  }));

  const subtotal = round2(
    priced
      .filter((item) => !item.is_optional)
      .reduce((sum, item) => sum + item.amount, 0),
  );

  let discountAmount = 0;
  if (quote.discount_type === 'percent') {
    discountAmount = round2(subtotal * (Number(quote.discount_value || 0) / 100));
  } else if (quote.discount_type === 'amount') {
    discountAmount = round2(Number(quote.discount_value || 0));
  }
  discountAmount = Math.min(Math.max(discountAmount, 0), subtotal);

  const net = round2(subtotal - discountAmount);
  const vatRate = Number(quote.vat_rate || 0);
  // When prices already include VAT, back it out of the net rather than adding it.
  const vatAmount = quote.vat_included
    ? round2(net - net / (1 + vatRate / 100))
    : round2(net * (vatRate / 100));
  const total = quote.vat_included ? net : round2(net + vatAmount);

  // --- internal cost model (never printed on the client-facing document) ----
  const area = round2(
    billable
      .filter((item) => (item.unit_en || '').toLowerCase().startsWith('m'))
      .reduce((sum, item) => sum + Number(item.qty || 0), 0),
  );

  const strandTons = (area * Number(quote.strand_kg_sqm || 0)) / 1000;
  const strandCost = strandTons * Number(quote.strand_price_ton || 0);
  const anchorCount = strandTons * Number(quote.anchors_per_ton || 0);
  const anchorCost = anchorCount * Number(quote.anchor_cost || 0);
  const ductCost = area * Number(quote.duct_cost_sqm || 0);
  const groutCost = area * Number(quote.grout_cost_sqm || 0);
  const labourCost = area * Number(quote.labour_cost_sqm || 0);
  const designCost = area * Number(quote.design_cost_sqm || 0);

  const direct = strandCost + anchorCost + ductCost + groutCost + labourCost + designCost;
  const overhead = direct * (Number(quote.overhead_pct || 0) / 100);
  const costTotal = round2(direct + overhead);

  const marginAmount = round2(net - costTotal);
  const marginPct = net > 0 ? round2((marginAmount / net) * 100) : 0;

  return {
    items: priced,
    subtotal,
    discount_amount: discountAmount,
    net_amount: net,
    vat_amount: vatAmount,
    total,
    cost_total: costTotal,
    margin_amount: marginAmount,
    margin_pct: marginPct,
    breakdown: {
      area_sqm: area,
      strand_tons: round2(strandTons),
      strand_kg: round2(area * Number(quote.strand_kg_sqm || 0)),
      anchor_count: Math.ceil(anchorCount),
      strand_cost: round2(strandCost),
      anchor_cost: round2(anchorCost),
      duct_cost: round2(ductCost),
      grout_cost: round2(groutCost),
      labour_cost: round2(labourCost),
      design_cost: round2(designCost),
      direct_cost: round2(direct),
      overhead_cost: round2(overhead),
      cost_per_sqm: area > 0 ? round2(costTotal / area) : 0,
      price_per_sqm: area > 0 ? round2(net / area) : 0,
      // Price that would hit the target margin, e.g. cost 45 at 20% → 56.25
      suggested_price_sqm:
        area > 0 && Number(quote.target_margin || 0) < 100
          ? round2(costTotal / area / (1 - Number(quote.target_margin || 0) / 100))
          : 0,
    },
  };
}

// ============================================================ number to words
const EN_ONES = ['', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine',
  'Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen', 'Seventeen',
  'Eighteen', 'Nineteen'];
const EN_TENS = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety'];
const EN_SCALES = ['', 'Thousand', 'Million', 'Billion', 'Trillion'];

function enGroup(n) {
  const parts = [];
  if (n >= 100) {
    parts.push(`${EN_ONES[Math.floor(n / 100)]} Hundred`);
    n %= 100;
    if (n) parts.push('and');
  }
  if (n >= 20) {
    const tens = EN_TENS[Math.floor(n / 10)];
    const ones = EN_ONES[n % 10];
    parts.push(ones ? `${tens}-${ones}` : tens);
  } else if (n > 0) {
    parts.push(EN_ONES[n]);
  }
  return parts.join(' ');
}

export function numberToWordsEn(value) {
  let n = Math.floor(Math.abs(Number(value) || 0));
  if (n === 0) return 'Zero';
  const groups = [];
  while (n > 0) {
    groups.push(n % 1000);
    n = Math.floor(n / 1000);
  }
  const words = [];
  for (let i = groups.length - 1; i >= 0; i -= 1) {
    if (!groups[i]) continue;
    words.push(`${enGroup(groups[i])}${EN_SCALES[i] ? ` ${EN_SCALES[i]}` : ''}`);
  }
  return words.join(' ').replace(/\s+/g, ' ').trim();
}

const AR_ONES = ['', 'واحد', 'اثنان', 'ثلاثة', 'أربعة', 'خمسة', 'ستة', 'سبعة', 'ثمانية', 'تسعة',
  'عشرة', 'أحد عشر', 'اثنا عشر', 'ثلاثة عشر', 'أربعة عشر', 'خمسة عشر', 'ستة عشر',
  'سبعة عشر', 'ثمانية عشر', 'تسعة عشر'];
const AR_TENS = ['', '', 'عشرون', 'ثلاثون', 'أربعون', 'خمسون', 'ستون', 'سبعون', 'ثمانون', 'تسعون'];
const AR_HUNDREDS = ['', 'مائة', 'مائتان', 'ثلاثمائة', 'أربعمائة', 'خمسمائة', 'ستمائة',
  'سبعمائة', 'ثمانمائة', 'تسعمائة'];
// [singular, dual, plural 3–10, singular used for 11+]
const AR_SCALES = [
  null,
  ['ألف', 'ألفان', 'آلاف', 'ألفاً'],
  ['مليون', 'مليونان', 'ملايين', 'مليوناً'],
  ['مليار', 'ملياران', 'مليارات', 'ملياراً'],
  ['تريليون', 'تريليونان', 'تريليونات', 'تريليوناً'],
];

function arGroup(n) {
  const parts = [];
  const hundreds = Math.floor(n / 100);
  const rest = n % 100;
  if (hundreds) parts.push(AR_HUNDREDS[hundreds]);
  if (rest) {
    if (rest < 20) {
      parts.push(AR_ONES[rest]);
    } else {
      const ones = rest % 10;
      const tens = AR_TENS[Math.floor(rest / 10)];
      // Arabic puts the unit before the ten: "خمسة وأربعون".
      parts.push(ones ? `${AR_ONES[ones]} و${tens}` : tens);
    }
  }
  return parts.join(' و');
}

/** Picks the correct Arabic form of a scale word for the given count. */
function arScaleWord(count, scaleIndex) {
  const forms = AR_SCALES[scaleIndex];
  if (!forms) return '';
  if (count === 1) return forms[0];
  if (count === 2) return forms[1];
  if (count >= 3 && count <= 10) return forms[2];
  return forms[3];
}

export function numberToWordsAr(value) {
  let n = Math.floor(Math.abs(Number(value) || 0));
  if (n === 0) return 'صفر';
  const groups = [];
  while (n > 0) {
    groups.push(n % 1000);
    n = Math.floor(n / 1000);
  }
  const words = [];
  for (let i = groups.length - 1; i >= 0; i -= 1) {
    const count = groups[i];
    if (!count) continue;
    if (i === 0) {
      words.push(arGroup(count));
    } else if (count === 1 || count === 2) {
      // "ألف" / "ألفان" stand alone — no preceding digit word.
      words.push(arScaleWord(count, i));
    } else {
      words.push(`${arGroup(count)} ${arScaleWord(count, i)}`);
    }
  }
  return words.join(' و').replace(/\s+/g, ' ').trim();
}

/**
 * Renders an amount as a legal "amount in words" line.
 * e.g. amountInWords(31416, 'SAR', 'ar') →
 *      "واحد وثلاثون ألفاً وأربعمائة وستة عشر ريال سعودي فقط لا غير"
 */
export function amountInWords(amount, currency, lang = 'ar') {
  const words = CURRENCY_WORDS[currency] || CURRENCY_WORDS.SAR;
  const value = Math.abs(Number(amount) || 0);
  const whole = Math.floor(value);
  const fraction = Math.round((value - whole) * 100);

  if (lang === 'ar') {
    const [major, minor] = words.ar;
    let text = `${numberToWordsAr(whole)} ${major}`;
    if (fraction > 0) text += ` و${numberToWordsAr(fraction)} ${minor}`;
    return `${text} فقط لا غير`;
  }

  const [major, minor] = words.en;
  let text = `${numberToWordsEn(whole)} ${major}${whole === 1 ? '' : 's'}`;
  if (fraction > 0) text += ` and ${numberToWordsEn(fraction)} ${minor}`;
  return `${text} Only`;
}
