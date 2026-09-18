/**
 * The cost comparison study.
 *
 * A post-tensioned slab is sold on the saving it makes against the system the
 * owner was going to build anyway, and the owner is rarely persuaded by a rate
 * per square metre alone. This works the comparison out properly: concrete,
 * reinforcement, formwork, the post-tensioning itself, and the consequences
 * that follow from a thinner, lighter slab — foundation load, building height
 * and construction time.
 *
 * Every input is a number the engineer can change, because the honest answer
 * depends on the project. What is fixed here is the arithmetic and the
 * defaults, not the figures.
 */
import { round2 } from './pricing.js';

/**
 * The conventional systems a project might otherwise be built in. Egypt builds
 * a great deal of hollow block, the Gulf mostly solid flat slabs, so the
 * engineer picks rather than the system assuming.
 *
 * `thickness_mm` and `rebar_kg_sqm` are starting points for a typical span,
 * meant to be edited against the real design.
 */
export const CONVENTIONAL_SYSTEMS = {
  solid: {
    label_en: 'Conventional solid slab',
    label_ar: 'سقف خرساني مصمت تقليدي',
    thickness_mm: 250,
    rebar_kg_sqm: 22,
    // Solid slabs are poured over the whole soffit.
    concrete_factor: 1,
  },
  hollow_block: {
    label_en: 'Hollow block slab',
    label_ar: 'سقف هوردي (بلوك)',
    thickness_mm: 300,
    rebar_kg_sqm: 18,
    // Blocks displace roughly a third of the depth; the rest is ribs and topping.
    concrete_factor: 0.65,
  },
  ribbed: {
    label_en: 'Ribbed / waffle slab',
    label_ar: 'سقف أعصاب / وافل',
    thickness_mm: 320,
    rebar_kg_sqm: 17,
    concrete_factor: 0.6,
  },
};

export const CONVENTIONAL_KEYS = Object.keys(CONVENTIONAL_SYSTEMS);

/** Reinforced concrete weighs about 2.5 tonnes per cubic metre. */
const CONCRETE_DENSITY_T_M3 = 2.5;

/**
 * A study filled in from a quotation. The rates are left at zero rather than
 * invented: a made-up concrete price would quietly produce a made-up saving,
 * and the engineer would have no reason to look at it.
 */
export function defaultStudy(quote = {}, system = 'solid') {
  const base = CONVENTIONAL_SYSTEMS[system] || CONVENTIONAL_SYSTEMS.solid;
  return {
    system,
    floors: 1,
    area_sqm: Number(quote.area_sqm) || 0,

    // What it would have been built as.
    conv_thickness_mm: base.thickness_mm,
    conv_rebar_kg_sqm: base.rebar_kg_sqm,

    // What we are proposing. A post-tensioned slab is thinner and carries far
    // less passive steel.
    pt_thickness_mm: 220,
    pt_rebar_kg_sqm: 8,
    // The quoted rate per m² — the post-tensioning package itself.
    pt_rate_sqm: Number(quote.unit_price) || 0,

    // Rates. Zero means "not filled in yet" and the study says so.
    concrete_rate_m3: 0,
    rebar_rate_ton: 0,
    formwork_rate_sqm: 0,

    // Programme, in days per floor.
    conv_cycle_days: 21,
    pt_cycle_days: 12,

    // What a lighter, thinner slab is worth beyond the slab itself. These are
    // the engineer's own estimate for this project and start at zero, because
    // against a hollow block slab the post-tensioned option can lose on slab
    // cost alone and still be the cheaper building — the difference is here.
    foundation_saving_sqm: 0,   // smaller columns and footings under less weight
    day_value: 0,               // what a day off the programme is worth

    // Shown as supporting benefits rather than money.
    storey_height_saving_mm: 0,

    notes_ar: '',
    notes_en: '',
  };
}

const n = (value) => {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
};

/**
 * Volumes and weights per square metre are small numbers, and two decimals is
 * not enough: a hollow block slab at 0.195 m³/m² shown as 0.20 overstates its
 * concrete by 2.5% in a table the owner reads line by line.
 */
const round3 = (value) => Math.round(value * 1000) / 1000;

/**
 * Works the study out. Returns per-square-metre costs for both systems, the
 * project totals, and the supporting figures that make the case beyond price.
 */
export function computeStudy(input = {}) {
  const study = { ...defaultStudy(), ...input };
  const system = CONVENTIONAL_SYSTEMS[study.system] || CONVENTIONAL_SYSTEMS.solid;

  const area = Math.max(n(study.area_sqm), 0);
  const floors = Math.max(n(study.floors), 1);
  const totalArea = area * floors;

  const concreteRate = n(study.concrete_rate_m3);
  const rebarRate = n(study.rebar_rate_ton);
  const formworkRate = n(study.formwork_rate_sqm);

  // ---------------------------------------------------------------- volumes
  // A hollow block or ribbed slab is deeper than a solid one but pours less
  // concrete, because the blocks and the voids take up part of the depth.
  const convThickness = n(study.conv_thickness_mm) / 1000;
  const ptThickness = n(study.pt_thickness_mm) / 1000;
  const convVolume = convThickness * (system.concrete_factor ?? 1);
  const ptVolume = ptThickness;   // post-tensioned slabs are solid

  const side = (label, volumeM3PerSqm, rebarKgSqm, rateSqm) => {
    const concrete = volumeM3PerSqm * concreteRate;
    const rebar = (rebarKgSqm / 1000) * rebarRate;
    const formwork = formworkRate;
    const post = rateSqm;
    return {
      label,
      concrete_m3_sqm: round3(volumeM3PerSqm),
      rebar_kg_sqm: round2(rebarKgSqm),
      concrete: round2(concrete),
      rebar: round2(rebar),
      formwork: round2(formwork),
      post_tension: round2(post),
      per_sqm: round2(concrete + rebar + formwork + post),
      total: round2((concrete + rebar + formwork + post) * totalArea),
      // Self-weight drives the columns and the foundations underneath.
      weight_t_sqm: round3(volumeM3PerSqm * CONCRETE_DENSITY_T_M3),
    };
  };

  const conventional = side('conventional', convVolume, n(study.conv_rebar_kg_sqm), 0);
  const postTension = side('post_tension', ptVolume, n(study.pt_rebar_kg_sqm), n(study.pt_rate_sqm));

  // ---------------------------------------------------------------- savings
  // The slab on its own, which is the comparison an owner checks first.
  const slabSavingPerSqm = round2(conventional.per_sqm - postTension.per_sqm);
  const slabSavingTotal = round2(conventional.total - postTension.total);

  // ------------------------------------------------------------ consequences
  const concreteSavedM3 = round2((convVolume - ptVolume) * totalArea);
  const rebarSavedTon = round2(((n(study.conv_rebar_kg_sqm) - n(study.pt_rebar_kg_sqm)) / 1000) * totalArea);
  // From the raw volumes: multiplying a rounded per-m² weight by fifteen
  // thousand square metres turns a hundredth into seventy-five tonnes.
  const weightSavedTon = round2((convVolume - ptVolume) * CONCRETE_DENSITY_T_M3 * totalArea);
  const thicknessSavedMm = round2(n(study.conv_thickness_mm) - n(study.pt_thickness_mm));

  const convProgramme = Math.round(n(study.conv_cycle_days) * floors);
  const ptProgramme = Math.round(n(study.pt_cycle_days) * floors);

  // A thinner slab either buys headroom or, over enough floors, a whole extra
  // storey within the same permitted building height.
  const heightSavedMm = round2(
    (thicknessSavedMm + n(study.storey_height_saving_mm)) * floors,
  );

  // --------------------------------------------------------- wider savings
  // Credited to the post-tensioned option: the foundations it does not need,
  // and the months it takes off the programme.
  const foundationSaving = round2(n(study.foundation_saving_sqm) * totalArea);
  const programmeSaving = round2(Math.max(convProgramme - ptProgramme, 0) * n(study.day_value));

  const savingTotal = round2(slabSavingTotal + foundationSaving + programmeSaving);
  const savingPerSqm = totalArea > 0 ? round2(savingTotal / totalArea) : 0;
  const convTotalWithExtras = conventional.total;
  const savingPct = convTotalWithExtras > 0
    ? round2((savingTotal / convTotalWithExtras) * 100)
    : 0;

  // ------------------------------------------------------------- completeness
  // Say plainly which rates are still missing rather than presenting a saving
  // computed from zeros as though it were a result.
  const missing = [];
  if (!concreteRate) missing.push('concrete_rate_m3');
  if (!rebarRate) missing.push('rebar_rate_ton');
  if (!n(study.pt_rate_sqm)) missing.push('pt_rate_sqm');
  if (!area) missing.push('area_sqm');

  return {
    input: study,
    system: {
      key: study.system,
      label_en: system.label_en,
      label_ar: system.label_ar,
    },
    area_sqm: round2(area),
    floors,
    total_area_sqm: round2(totalArea),
    conventional,
    post_tension: postTension,
    saving: {
      // The slab-for-slab figure, kept separate so the document can show the
      // narrow comparison and the whole-building one without conflating them.
      slab_per_sqm: slabSavingPerSqm,
      slab_total: slabSavingTotal,
      foundation_total: foundationSaving,
      programme_total: programmeSaving,
      per_sqm: savingPerSqm,
      total: savingTotal,
      pct: savingPct,
      // A study that shows post-tensioning costing more is still a true study;
      // the document says so rather than hiding it.
      favours_pt: savingTotal > 0,
      favours_pt_on_slab_alone: slabSavingPerSqm > 0,
    },
    benefits: {
      concrete_saved_m3: concreteSavedM3,
      rebar_saved_ton: rebarSavedTon,
      weight_saved_ton: weightSavedTon,
      thickness_saved_mm: thicknessSavedMm,
      height_saved_mm: heightSavedMm,
      conv_programme_days: convProgramme,
      pt_programme_days: ptProgramme,
      days_saved: convProgramme - ptProgramme,
    },
    missing,
    complete: missing.length === 0,
  };
}
