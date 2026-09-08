import { pool } from '../config/db.js';

/**
 * Writes one row to audit_log. Call this inside the same request handler
 * that performs a create/update/delete on an audited table (base_items,
 * trade_items). Not wrapped in the same DB transaction as the write itself
 * by default — call within a client.query transaction if you need atomicity.
 */
export async function writeAudit({ tableName, recordId, action, changedBy, oldValue, newValue }) {
  await pool.query(
    `INSERT INTO audit_log (table_name, record_id, action, changed_by, old_value, new_value)
     VALUES ($1, $2, $3, $4, $5, $6)`,
    [tableName, recordId, action, changedBy, oldValue ? JSON.stringify(oldValue) : null, newValue ? JSON.stringify(newValue) : null]
  );
}
