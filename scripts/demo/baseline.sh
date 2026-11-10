#!/usr/bin/env bash
# 운영 데이터 기준점. 지금 운영 DB를 기준점으로 떠 두고(snapshot), 언제든 그 상태로 되돌린다(restore).
#
#   scripts/demo/baseline.sh restore    기준점으로 되돌린다 (서비스가 1~2분 멈추고 모두 로그아웃된다)
#   scripts/demo/baseline.sh snapshot   지금 상태를 새 기준점으로 뜬다 (이전 기준점은 최근 5개까지 남긴다)
#   scripts/demo/baseline.sh status     기준점 목록
#   scripts/demo/baseline.sh cleanup    취소되거나 실패한 실행이 남긴 DB 작업을 끝내고 서비스를 다시 띄운다
#
# 운영 서버(EC2)에서 저장소 루트를 현재 폴더로 두고 실행한다. 보통은 GitHub Actions의 'demo baseline'으로 부른다.
# DB(backend public 스키마와 ai 스키마: 지원서 · 전형 · 분석 결과 · 프로필 · 검색 색인 · Chat 기록)를 통째로 되돌린다.
# 지원자 서류는 S3에 있고 지우지 않으므로 그대로 이어진다. Redis(로그인 세션, 작업 대기열)는 비운다.
set -euo pipefail

ENV_FILE=${ENV_FILE:-/opt/hiremate/runtime.env}
DIR=${BASELINE_DIR:-/opt/hiremate/baseline}
CA=${RDS_CA:-/opt/hiremate/rds-ca-bundle.pem}
COMPOSE=(docker compose -f compose.production.yaml)
PG_IMAGE=postgres:18
KEEP=5
# 기준점과 내용이 같은 참고 자료 표. 복원할 때 DB에 있으면 지우지 않고 그대로 둔다.
# NCS 표의 HNSW 색인을 다시 만들면 운영 DB에서 20분이 넘게 걸려 워크플로 시간 제한에 걸린다.
# 남겨 두는 표는 다른 표를 참조하지 않아야 한다(외래 키가 없어야 한다).
KEEP_TABLES=(ai.ncs_reference_chunks)
# 이 스크립트가 띄운 클라이언트 컨테이너와 DB 세션의 이름. 취소된 실행이 남긴 것을 이 이름으로 찾아 끝낸다
LABEL=hiremate.baseline
export PGAPPNAME=hiremate-baseline

set -a
# shellcheck source=/dev/null
. "$ENV_FILE"
set +a
# jdbc:postgresql://host:5432/db?... 에서 호스트와 DB 이름을 뽑는다
target=${SPRING_DATASOURCE_URL#jdbc:postgresql://}
host=${target%%[:/]*}
database=${PGDATABASE_OVERRIDE:-$(sed -E 's#^[^/]*/([^?]*).*#\1#' <<<"$target")}
export PGPASSWORD=$SPRING_DATASOURCE_PASSWORD

# PostgreSQL 클라이언트 도구를 RDS와 같은 18 버전 컨테이너로 실행한다. 비밀번호는 명령 인자에 남기지 않는다.
# 기준점 폴더의 그룹(실행기 그룹)을 더해 실행기와 root 어느 쪽으로 실행해도 파일을 읽고 쓴다
pg() {
    docker run --rm -i --label "$LABEL" --user "$(id -u):$(id -g)" --group-add "$(stat -c %g "$DIR")" \
        -e PGPASSWORD -e PGAPPNAME -e PGSSLMODE=verify-full -e PGSSLROOTCERT=/ca.pem \
        -v "$CA:/ca.pem:ro" -v "$DIR:/baseline" "$PG_IMAGE" \
        "$1" -h "$host" -U "$SPRING_DATASOURCE_USERNAME" "${@:2}"
}

wait_healthy() {
    for _ in $(seq 1 60); do
        if curl --fail --silent --max-time 5 --resolve hiremate.yuumin.com:443:127.0.0.1 \
            https://hiremate.yuumin.com/healthz >/dev/null; then
            echo "서비스가 정상으로 올라왔다"
            return 0
        fi
        sleep 5
    done
    "${COMPOSE[@]}" ps
    echo "서비스 상태 확인이 끝나지 않았다" >&2
    return 1
}

# 취소된 실행은 docker 명령만 끝나고 클라이언트 컨테이너와 DB 트랜잭션이 남아 다음 복원을 잠금으로 막는다.
# 워크플로는 배포와 같은 묶음이라 동시에 돌지 않으므로, 남은 것은 모두 끝난 실행의 것이다
stop_leftovers() {
    docker ps -q --filter "label=$LABEL" | xargs -r docker rm -f >/dev/null
    pg psql -d "$database" -Atq -o /dev/null -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity
        WHERE application_name = '$PGAPPNAME' AND pid <> pg_backend_pid()" </dev/null
    rm -f "$DIR/restore.sql" "$DIR/restore.list"
}

snapshot() {
    local stamp file
    stamp=$(date -u +%Y%m%dT%H%MZ)
    file=baseline-$stamp.dump
    pg pg_dump -d "$database" -Fc --no-owner --no-privileges -f "/baseline/$file"
    chmod 640 "$DIR/$file"
    ln -sfn "$file" "$DIR/baseline.dump"
    # 기준점 파일은 최근 KEEP개만 남긴다
    find "$DIR" -maxdepth 1 -name 'baseline-*.dump' -printf '%T@ %p\n' | sort -rn | tail -n +$((KEEP + 1)) |
        cut -d' ' -f2- | xargs -r rm -f
    echo "새 기준점: $file"
    status
}

restore() {
    [[ -e $DIR/baseline.dump ]] || { echo "기준점이 없다: $DIR/baseline.dump" >&2; exit 1; }
    echo "기준점 $(readlink "$DIR/baseline.dump")로 되돌린다"
    # 복원이 실패하거나 중간에 멈춰도 남은 작업을 끝내고 서비스를 다시 띄운다
    trap 'stop_leftovers || true; "${COMPOSE[@]}" up -d --no-build backend ai worker </dev/null' EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    stop_leftovers

    local keep present skip=('SCHEMA - ai') schema table indexes index
    keep="'{$(IFS=,; echo "${KEEP_TABLES[*]}")}'::text[]"
    # 남겨 둘 표 중 DB에 있는 것은 기준점에서 표 · 데이터 · 제약 · 색인을 빼고 복원한다. 없으면 기준점에서 만든다.
    # 제약(기본 키 등)이 만드는 색인은 제약 항목으로 빠지므로 따로 적지 않는다
    present=$(pg psql -d "$database" -Atq -F ' ' -c "SELECT n.nspname, c.relname,
            coalesce(string_agg(i.relname, ' ') FILTER (WHERE i.oid IS NOT NULL AND con.oid IS NULL), '')
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_index x ON x.indrelid = c.oid LEFT JOIN pg_class i ON i.oid = x.indexrelid
        LEFT JOIN pg_constraint con ON con.conindid = i.oid AND con.conrelid = c.oid AND con.contype IN ('p', 'u', 'x')
        WHERE c.relkind = 'r' AND n.nspname || '.' || c.relname = ANY ($keep)
        GROUP BY 1, 2" </dev/null)
    while read -r schema table indexes; do
        [[ -n $schema ]] || continue
        echo "그대로 둔다: $schema.$table"
        skip+=("$schema $table")
        for index in $indexes; do skip+=("INDEX $schema $index"); done
    done <<<"$present"
    pg pg_restore -l /baseline/baseline.dump </dev/null |
        grep -v -F "$(printf ' %s \n' "${skip[@]}")" >"$DIR/restore.list"
    # SQL로 먼저 풀어 본다. 기준점 파일이 깨졌으면 DB를 건드리기 전에 멈춘다
    pg pg_restore --no-owner --no-privileges -L /baseline/restore.list -f /baseline/restore.sql \
        /baseline/baseline.dump </dev/null
    "${COMPOSE[@]}" stop backend worker ai
    # 남겨 둘 표와 확장 기능(vector)만 빼고 두 스키마의 객체를 지운 뒤 기준점을 넣는다.
    # 기준점 뒤에 생긴 표도 지운다. 한 트랜잭션이라 실패하면 DB는 그대로다
    pg psql -d "$database" --single-transaction -v ON_ERROR_STOP=1 -q -o /dev/null -c "
        CREATE SCHEMA IF NOT EXISTS ai;
        DO \$\$
        DECLARE
            r record;
        BEGIN
            FOR r IN
                SELECT CASE c.relkind WHEN 'v' THEN 'VIEW' WHEN 'm' THEN 'MATERIALIZED VIEW'
                        WHEN 'S' THEN 'SEQUENCE' ELSE 'TABLE' END AS kind,
                    format('%I.%I', n.nspname, c.relname) AS name
                FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname IN ('public', 'ai') AND c.relkind IN ('r', 'p', 'v', 'm', 'S')
                    AND n.nspname || '.' || c.relname <> ALL ($keep)
                    AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_class'::regclass
                        AND d.objid = c.oid AND d.deptype IN ('e', 'a', 'i'))
            LOOP
                EXECUTE format('DROP %s IF EXISTS %s CASCADE', r.kind, r.name);
            END LOOP;
            FOR r IN
                SELECT p.oid::regprocedure AS name FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname IN ('public', 'ai') AND NOT EXISTS (SELECT 1 FROM pg_depend d
                    WHERE d.classid = 'pg_proc'::regclass AND d.objid = p.oid AND d.deptype = 'e')
            LOOP
                EXECUTE format('DROP ROUTINE IF EXISTS %s CASCADE', r.name);
            END LOOP;
            FOR r IN
                SELECT t.oid::regtype AS name FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                WHERE n.nspname IN ('public', 'ai') AND t.typtype IN ('e', 'd', 'r') AND NOT EXISTS (
                    SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_type'::regclass AND d.objid = t.oid
                        AND d.deptype = 'e')
            LOOP
                EXECUTE format('DROP TYPE IF EXISTS %s CASCADE', r.name);
            END LOOP;
        END
        \$\$;" \
        -f /baseline/restore.sql </dev/null
    rm -f "$DIR/restore.sql" "$DIR/restore.list"
    "${COMPOSE[@]}" exec -T redis redis-cli FLUSHALL </dev/null
    # 기준점 이후 배포로 스키마가 바뀌었으면 최신으로 올린다. backend(Flyway)는 시작할 때 올린다
    "${COMPOSE[@]}" run --rm -T --no-deps ai alembic upgrade head </dev/null
    trap - EXIT INT TERM
    "${COMPOSE[@]}" up -d --no-build backend ai worker </dev/null
    wait_healthy
}

# 워크플로가 취소되거나 시간 제한에 걸리면 실행기는 스크립트를 끝까지 멈추지 못하고, 서비스를 다시 띄우는 정리도
# 돌지 않는다. 워크플로의 마지막 단계가 이것을 불러 남은 DB 작업을 끝내고 서비스를 다시 띄운다.
# 복원 트랜잭션이 이미 커밋됐을 수 있으므로 ai 스키마를 최신으로 올린 뒤 띄운다
cleanup() {
    # 멈추지 않은 이전 단계의 스크립트가 서비스를 다시 멈추지 않게 먼저 끝낸다
    pkill -KILL -f 'baseline\.sh (restore|snapshot)' || true
    stop_leftovers
    "${COMPOSE[@]}" run --rm -T --no-deps ai alembic upgrade head </dev/null
    "${COMPOSE[@]}" up -d --no-build backend ai worker </dev/null
    wait_healthy
}

status() {
    echo "기준점: $(readlink "$DIR/baseline.dump" 2>/dev/null || echo 없음)"
    find "$DIR" -maxdepth 1 -name 'baseline-*.dump' -printf '%TY-%Tm-%Td %TH:%TM  %s bytes  %f\n' | sort -r
}

case ${1:-} in
    snapshot) snapshot ;;
    restore) restore ;;
    status) status ;;
    cleanup) cleanup ;;
    *)
        echo "사용법: $0 restore|snapshot|status|cleanup" >&2
        exit 2
        ;;
esac
