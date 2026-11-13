#!/bin/sh
# Idle pooled pg client killed by the server (as on a Postgres restart / failover / admin terminate).
# Local throwaway instance only. Usage: sh pool_error_check.sh <server pid> <server log>
PID=$1; LOG=$2
before=$(wc -l < "$LOG")
echo "server pid $PID alive before: $(tasklist //FI "PID eq $PID" | grep -c node)"
for i in 1 2 3 4 5 6; do curl -s -o /dev/null http://localhost:3201/api/ready & done; wait
sleep 1
echo "app connections (idle) before terminate:"
docker exec vega-perf-pg psql -U vega -d postgres -tAc "select count(*) from pg_stat_activity where datname='vega_sec5' and state='idle'"
docker exec vega-perf-pg psql -U vega -d postgres -tAc "select count(pg_terminate_backend(pid)) from pg_stat_activity where datname='vega_sec5' and state='idle'"
sleep 3
echo "server pid alive after: $(tasklist //FI "PID eq $PID" | grep -c node)"
echo "healthz after: $(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://localhost:3201/api/healthz)"
echo "ready after:   $(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://localhost:3201/api/ready)"
echo "--- server log lines added:"
tail -n +$((before+1)) "$LOG" | head -30
