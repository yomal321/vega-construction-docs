import { pool } from '../config/db.js';

const FLOOR_ORDER = ['ground', 'first', 'second', 'third', 'fourth'];

/**
 * Resolves the fully-costed rate (per unit) of a trade item, recursively
 * expanding any components that are themselves trade items (e.g. a column's
 * concrete rate references the "Mixing Concrete 1:2:4" trade item).
 *
 * Mirrors the client's real workbook: sum(component qty * component rate)
 * over the "Analysis for N unit" basis, divided by that basis, then scaled
 * by a per-floor multiplier (labour costs more the higher you build).
 *
 * @param {number} tradeItemId
 * @param {string} floor - one of FLOOR_ORDER, defaults to 'ground'
 * @param {Set<number>} visiting - internal cycle guard, do not pass manually
 * @returns {Promise<{ rate: number, baseRate: number, breakdown: object[] }>}
 */
export async function resolveTradeItemRate(tradeItemId, floor = 'ground', visiting = new Set()) {
  if (visiting.has(tradeItemId)) {
    throw new Error(
      `Circular reference detected in trade item recipe (item #${tradeItemId} references itself indirectly).`
    );
  }
  visiting.add(tradeItemId);

  const { rows: itemRows } = await pool.query(
    'SELECT id, description, unit, analysis_qty FROM trade_items WHERE id = $1',
    [tradeItemId]
  );
  const item = itemRows[0];
  if (!item) {
    throw new Error(`Trade item #${tradeItemId} not found.`);
  }

  const { rows: components } = await pool.query(
    `SELECT tic.id, tic.component_kind, tic.quantity, tic.note,
            bi.id AS base_item_id, bi.description AS base_description, bi.unit_price,
            ct.id AS child_trade_item_id, ct.description AS child_description
     FROM trade_item_components tic
     LEFT JOIN base_items bi ON bi.id = tic.base_item_id
     LEFT JOIN trade_items ct ON ct.id = tic.child_trade_item_id
     WHERE tic.trade_item_id = $1`,
    [tradeItemId]
  );

  let total = 0;
  const breakdown = [];

  for (const c of components) {
    let unitCost;
    let label;

    if (c.component_kind === 'base_item') {
      unitCost = Number(c.unit_price);
      label = c.base_description;
    } else {
      // Recurse into the child trade item. Floor is passed through so nested
      // items (e.g. concrete mix inside a column) escalate consistently too.
      const childResult = await resolveTradeItemRate(c.child_trade_item_id, floor, new Set(visiting));
      unitCost = childResult.rate;
      label = c.child_description;
    }

    const lineCost = Number(c.quantity) * unitCost;
    total += lineCost;
    breakdown.push({
      description: label,
      quantity: Number(c.quantity),
      unitCost,
      lineCost,
      note: c.note || null,
    });
  }

  const baseRate = total / Number(item.analysis_qty);

  const { rows: floorRows } = await pool.query(
    'SELECT multiplier FROM trade_item_floor_rates WHERE trade_item_id = $1 AND floor = $2',
    [tradeItemId, floor]
  );
  const multiplier = floorRows[0] ? Number(floorRows[0].multiplier) : 1.0;

  return {
    tradeItemId,
    description: item.description,
    unit: item.unit,
    analysisQty: Number(item.analysis_qty),
    baseRate,
    floor,
    multiplier,
    rate: baseRate * multiplier,
    breakdown,
  };
}

export { FLOOR_ORDER };
