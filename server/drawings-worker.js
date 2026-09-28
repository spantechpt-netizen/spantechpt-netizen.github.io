/**
 * Runs one drawing generation off the main thread. Generating a package is
 * pure CPU for seconds to a minute; on the request thread it would freeze the
 * CRM for everybody until it finished.
 */
import { parentPort, workerData } from 'node:worker_threads';
import { generate } from '../shopdrawings/cli.mjs';

try {
  const { input, out, meta, spec, levelNames, mode } = workerData;
  const t0 = Date.now();
  const { model, pack } = generate({ inputDxf: input, out, meta, spec, svg: true, levelNames, mode });
  parentPort.postMessage({
    ok: true,
    duration_ms: Date.now() - t0,
    sheets: pack.sheets.map((s) => ({
      no: s.drawingNo,
      title: s.title,
      block: s.blockName,
      level: s.level,
      level_name: s.levelName,
      scale: s.scale || null,
      weight: s.weight ? Math.round(s.weight) : null,
      file: `${s.drawingNo}_${s.blockName}`,
    })),
    assumptions: model.assumptions.map((a) => (a.level ? `[${a.level}] ` : '') + a.text),
    findings: model.findings,
    levels: model.levels.map((l) => ({ id: l.id, name: l.name, thickness: l.thickness, columns: (l.columns || []).length })),
  });
} catch (error) {
  parentPort.postMessage({ ok: false, error: String(error && error.stack || error) });
}
