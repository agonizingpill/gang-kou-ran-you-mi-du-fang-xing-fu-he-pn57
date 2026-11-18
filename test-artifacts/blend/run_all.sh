#!/bin/bash
# 全量验证：重置DB → seed → fixture → E2E → 重置DB → seed → fixture → 回归
set -e
export PATH=/tmp/pg/usr/lib/postgresql/15/bin:$PATH
export DATABASE_URL='postgresql+psycopg://bunker@127.0.0.1:15432/bunker'
reset_db(){ psql -h 127.0.0.1 -p 15432 -U bunker -d bunker -qc 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;' >/dev/null 2>&1; (python3 -c "from scripts.seed_demo import seed; seed()" >/dev/null); python3 /workspace/test-artifacts/blend/fixture.py >/dev/null; }
cd /workspace/backend
reset_db
echo "=== E2E ==="
python3 /workspace/test-artifacts/blend/test_blend_e2e.py
reset_db
echo "=== REGRESSION ==="
python3 /workspace/test-artifacts/blend/test_regression.py
