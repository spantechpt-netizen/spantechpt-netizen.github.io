/**
 * The cost comparison study's arithmetic.
 *
 * These numbers go in front of a building owner to argue for a price, so the
 * sums have to be right and the study has to be willing to say when the answer
 * does not favour us.
 *
 *   npm test
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { computeStudy, CONVENTIONAL_SYSTEMS } from '../server/study.js';

/** A Riyadh tower: six floors of 2,500 m², priced at 70 SAR/m². */
const project = {
  floors: 6,
  area_sqm: 2500,
  pt_thickness_mm: 220,
  pt_rebar_kg_sqm: 8,
  pt_rate_sqm: 70,
  concrete_rate_m3: 950,
  rebar_rate_ton: 3800,
  formwork_rate_sqm: 55,
  conv_cycle_days: 21,
  pt_cycle_days: 12,
};

test('the per-square-metre build-up is the sum of its parts', () => {
  const r = computeStudy({ ...project, system: 'solid', conv_thickness_mm: 250, conv_rebar_kg_sqm: 22 });

  // Conventional: 0.25 m³ × 950 + 22 kg × 3.80 + 55 formwork.
  assert.equal(r.conventional.concrete, 237.5);
  assert.equal(r.conventional.rebar, 83.6);
  assert.equal(r.conventional.formwork, 55);
  assert.equal(r.conventional.per_sqm, 376.1);
  assert.equal(r.conventional.post_tension, 0, 'the conventional option carries no PT cost');

  // Post-tensioned: thinner slab, a third of the passive steel, plus our rate.
  assert.equal(r.post_tension.concrete, 209);
  assert.equal(r.post_tension.rebar, 30.4);
  assert.equal(r.post_tension.post_tension, 70);
  assert.equal(r.post_tension.per_sqm, 364.4);

  assert.equal(r.total_area_sqm, 15000, '2,500 m² over six floors');
  assert.equal(r.conventional.total, 376.1 * 15000);
});

test('a hollow block slab pours less concrete than its depth suggests', () => {
  const solid = computeStudy({ ...project, system: 'solid', conv_thickness_mm: 300 });
  const hollow = computeStudy({ ...project, system: 'hollow_block', conv_thickness_mm: 300 });

  assert.equal(solid.conventional.concrete_m3_sqm, 0.3);
  assert.equal(
    hollow.conventional.concrete_m3_sqm,
    0.3 * CONVENTIONAL_SYSTEMS.hollow_block.concrete_factor,
    'the blocks displace part of the depth',
  );
  assert.ok(hollow.conventional.per_sqm < solid.conventional.per_sqm);
});

test('the study says so when post-tensioning loses on slab cost alone', () => {
  // Against hollow block, a post-tensioned slab often costs more per m² — and
  // a study that hid that would be caught out in the first technical meeting.
  const r = computeStudy({ ...project, system: 'hollow_block', conv_thickness_mm: 300, conv_rebar_kg_sqm: 18 });

  assert.ok(r.saving.slab_per_sqm < 0, 'the slab comparison is genuinely negative here');
  assert.equal(r.saving.favours_pt_on_slab_alone, false);
  assert.equal(r.saving.favours_pt, false, 'with no wider savings entered, it stays negative');
});

test('foundations and programme are credited separately, not folded in silently', () => {
  const base = { ...project, system: 'hollow_block', conv_thickness_mm: 300, conv_rebar_kg_sqm: 18 };
  const slabOnly = computeStudy(base);
  const full = computeStudy({ ...base, foundation_saving_sqm: 45, day_value: 9000 });

  assert.equal(full.saving.slab_total, slabOnly.saving.slab_total, 'the slab figure is untouched');
  assert.equal(full.saving.foundation_total, 45 * 15000);
  assert.equal(full.saving.programme_total, (21 - 12) * 6 * 9000);
  assert.equal(
    full.saving.total,
    full.saving.slab_total + full.saving.foundation_total + full.saving.programme_total,
  );
  assert.equal(full.saving.favours_pt, true, 'the whole-building case turns positive');
  assert.equal(full.saving.favours_pt_on_slab_alone, false, 'but the slab one is still reported honestly');
});

test('the consequences of a thinner, lighter slab are counted', () => {
  const r = computeStudy({ ...project, system: 'solid', conv_thickness_mm: 250, conv_rebar_kg_sqm: 22 });

  assert.equal(r.benefits.thickness_saved_mm, 30);
  assert.equal(r.benefits.concrete_saved_m3, (0.25 - 0.22) * 15000);
  assert.equal(r.benefits.rebar_saved_ton, ((22 - 8) / 1000) * 15000);
  // 30 mm less concrete over 15,000 m² at 2.5 t/m³. Written out rather than as
  // (0.625 - 0.55) * 15000, which floating point makes 1124.9999999999993.
  assert.equal(r.benefits.weight_saved_ton, 1125);
  assert.equal(r.benefits.days_saved, (21 - 12) * 6);
  assert.equal(r.benefits.height_saved_mm, 30 * 6, 'over six floors that is 180 mm of building');
});

test('an unfilled study reports what is missing instead of a saving from zeros', () => {
  const r = computeStudy({ system: 'solid' });
  assert.equal(r.complete, false);
  assert.deepEqual(
    [...r.missing].sort(),
    ['area_sqm', 'concrete_rate_m3', 'pt_rate_sqm', 'rebar_rate_ton'].sort(),
  );
  assert.equal(r.saving.total, 0);
});

test('nonsense input cannot produce a number', () => {
  const r = computeStudy({ ...project, area_sqm: 'abc', floors: 0, concrete_rate_m3: null });
  assert.equal(r.area_sqm, 0);
  assert.equal(r.floors, 1, 'a building has at least one floor');
  assert.ok(Number.isFinite(r.saving.total));
});
