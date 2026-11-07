#!/usr/bin/env bash
# 운영 데이터 기준점. 지금 운영 DB를 기준점으로 떠 두고(snapshot), 언제든 그 상태로 되돌린다(restore).
#
#   scripts/demo/baseline.sh restore    기준점으로 되돌린다 (서비스가 1~2분 멈추고 모두 로그아웃된다)
#   scripts/demo/baseline.sh snapshot   지금 상태를 새 기준점으로 뜬다 (이전 기준점은 최근 5개까지 남긴다)
#   scripts/demo/baseline.sh status     기준점 목록
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
    docker run --rm -i --user "$(id -u):$(id -g)" --group-add "$(stat -c %g "$DIR")" \
        -e PGPASSWORD -e PGSSLMODE=verify-full -e PGSSLROOTCERT=/ca.pem \
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
    local sql=$DIR/restore.sql
    # 복원이 실패해도 서비스는 다시 띄운다
    trap 'rm -f "$sql"; "${COMPOSE[@]}" up -d --no-build backend ai worker' EXIT
    # SQL로 먼저 풀어 본다. 기준점 파일이 깨졌으면 DB를 건드리기 전에 멈춘다
    pg pg_restore --no-owner --no-privileges -f /baseline/restore.sql /baseline/baseline.dump </dev/null
    "${COMPOSE[@]}" stop backend worker ai
    # 기준점 뒤에 생긴 표가 남으면 vector 확장을 지우지 못하고 alembic도 막힌다. 두 스키마를 통째로 지우고 다시 만든다.
    # 한 트랜잭션이라 실패하면 DB는 그대로다
    pg psql -d "$database" --single-transaction -v ON_ERROR_STOP=1 -q -o /dev/null \
        -c 'DROP SCHEMA IF EXISTS ai CASCADE' -c 'DROP SCHEMA IF EXISTS public CASCADE' -c 'CREATE SCHEMA public' \
        -f /baseline/restore.sql </dev/null
    rm -f "$sql"
    "${COMPOSE[@]}" exec -T redis redis-cli FLUSHALL
    # 기준점 이후 배포로 스키마가 바뀌었으면 최신으로 올린다. backend(Flyway)는 시작할 때 올린다
    "${COMPOSE[@]}" run --rm --no-deps ai alembic upgrade head
    trap - EXIT
    "${COMPOSE[@]}" up -d --no-build backend ai worker
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
    *)
        echo "사용법: $0 restore|snapshot|status" >&2
        exit 2
        ;;
esac
