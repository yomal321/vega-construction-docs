import pg from 'pg';
import dotenv from 'dotenv';

dotenv.config();

const { Pool } = pg;

export const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
});

// Fail loudly on startup if the DB is unreachable, rather than on first request.
pool.query('SELECT 1').catch((err) => {
  console.error('Database connection failed on startup:', err.message);
});
