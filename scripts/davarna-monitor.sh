#!/usr/bin/env bash
set -uo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/davarna}"
ENV_FILE="${ENV_FILE:-${PROJECT_DIR}/.env.prod}"
BOT_ENV_FILE="${BOT_ENV_FILE:-${PROJECT_DIR}/davarna-bot/.env.prod}"
STATE_DIR="${MONITOR_STATE_DIR:-/var/tmp/davarna-monitor}"
STATE_FILE="${STATE_DIR}/state"
LOG_PREFIX="[davarna-monitor]"

DISK_WARN_PCT="${MONITOR_DISK_WARN_PCT:-85}"
BACKUP_MAX_AGE_HOURS="${MONITOR_BACKUP_MAX_AGE_HOURS:-14}"
REPEAT_ALERT_MINUTES="${MONITOR_REPEAT_ALERT_MINUTES:-60}"
BACKEND_HOST_PORT="${BACKEND_HOST_PORT:-18080}"

mkdir -p "${STATE_DIR}" 2>/dev/null || true

failures=()
warnings=()

add_failure() {
  failures+=("$1")
}

add_warning() {
  warnings+=("$1")
}

read_env_value() {
  local file="$1"
  local key="$2"
  [[ -f "${file}" ]] || return 0
  awk -v k="${key}" '
    /^[[:space:]]*#/ { next }
    index($0, "=") == 0 { next }
    {
      line=$0
      sub(/^[[:space:]]*/, "", line)
      key=line
      sub(/=.*/, "", key)
      gsub(/[[:space:]]/, "", key)
      if (key == k) {
        sub(/^[^=]*=/, "", line)
        sub(/\r$/, "", line)
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", line)
        sq=sprintf("%c", 39)
        if ((substr(line,1,1) == "\"" && substr(line,length(line),1) == "\"") ||
            (substr(line,1,1) == sq && substr(line,length(line),1) == sq)) {
          line=substr(line,2,length(line)-2)
        }
        print line
        exit
      }
    }
  ' "${file}"
}

env_or_default() {
  local key="$1"
  local fallback="${2:-}"
  local val
  val="$(read_env_value "${ENV_FILE}" "${key}")"
  if [[ -z "${val}" ]]; then
    val="$(read_env_value "${BOT_ENV_FILE}" "${key}")"
  fi
  printf '%s' "${val:-${fallback}}"
}

send_telegram() {
  local text="$1"
  local token chat_id topic_id
  token="$(env_or_default MONITOR_BOT_TOKEN)"
  [[ -n "${token}" ]] || token="$(env_or_default BACKUP_BOT_TOKEN)"
  [[ -n "${token}" ]] || token="$(env_or_default TELEGRAM_BOT_TOKEN)"

  chat_id="$(env_or_default MONITOR_ALERT_CHAT_ID)"
  [[ -n "${chat_id}" ]] || chat_id="$(env_or_default ADMIN_FORUM_CHAT_ID)"
  [[ -n "${chat_id}" ]] || chat_id="$(env_or_default BACKUP_CHAT_ID)"

  topic_id="$(env_or_default MONITOR_ALERT_TOPIC_ID)"
  [[ -n "${topic_id}" ]] || topic_id="$(env_or_default ADMIN_TOPIC_ALERTS_ID)"

  if [[ -z "${token}" || -z "${chat_id}" ]]; then
    echo "${LOG_PREFIX} telegram alert skipped: missing MONITOR_BOT_TOKEN/TELEGRAM_BOT_TOKEN or MONITOR_ALERT_CHAT_ID/ADMIN_FORUM_CHAT_ID" >&2
    return 1
  fi

  local args=(
    --fail --silent --show-error
    -X POST "https://api.telegram.org/bot${token}/sendMessage"
    -d "chat_id=${chat_id}"
    --data-urlencode "text=${text}"
    -d "disable_web_page_preview=true"
  )
  if [[ -n "${topic_id}" ]]; then
    args+=(-d "message_thread_id=${topic_id}")
  fi

  curl "${args[@]}" >/dev/null
}

check_project() {
  if [[ ! -d "${PROJECT_DIR}" ]]; then
    add_failure "PROJECT_DIR not found: ${PROJECT_DIR}"
    return
  fi
  if [[ ! -f "${ENV_FILE}" ]]; then
    add_failure ".env.prod not found or not readable: ${ENV_FILE}"
  fi
  if ! command -v docker >/dev/null 2>&1; then
    add_failure "docker command not found"
  fi
  if ! command -v curl >/dev/null 2>&1; then
    add_failure "curl command not found"
  fi
}

compose_exec() {
  cd "${PROJECT_DIR}" && docker compose --env-file "${ENV_FILE}" "$@"
}

check_container() {
  local name="$1"
  local require_health="${2:-yes}"
  local state health
  state="$(docker inspect -f '{{.State.Status}}' "${name}" 2>/dev/null || true)"
  if [[ -z "${state}" ]]; then
    add_failure "container missing: ${name}"
    return
  fi
  if [[ "${state}" != "running" ]]; then
    add_failure "container not running: ${name} status=${state}"
    return
  fi
  if [[ "${require_health}" == "yes" ]]; then
    health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}no-health{{end}}' "${name}" 2>/dev/null || true)"
    if [[ "${health}" != "healthy" ]]; then
      add_failure "container unhealthy: ${name} health=${health}"
    fi
  fi
}

check_containers() {
  check_container "davarna-mysql" "yes"
  check_container "davarna-redis" "yes"
  check_container "davarna-backend" "yes"
  check_container "davarna-bot" "no"
}

check_health() {
  local port
  port="$(read_env_value "${ENV_FILE}" BACKEND_HOST_PORT)"
  port="${port:-${BACKEND_HOST_PORT}}"

  if ! curl --fail --silent --show-error --max-time 8 "http://127.0.0.1:${port}/health/db" >/dev/null; then
    add_failure "backend health failed: http://127.0.0.1:${port}/health/db"
  fi

  local server_name
  server_name="$(read_env_value "${ENV_FILE}" NGINX_SERVER_NAME)"
  if [[ -n "${server_name}" && "${server_name}" != "_" ]]; then
    if ! curl --fail --silent --show-error --max-time 12 "https://${server_name}/health/db" >/dev/null; then
      add_failure "public health failed: https://${server_name}/health/db"
    fi
  fi
}

check_datastores() {
  if ! compose_exec exec -T mysql sh -c 'mysqladmin ping -h 127.0.0.1 -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" --silent' >/dev/null 2>&1; then
    add_failure "mysql ping failed"
  fi
  if ! compose_exec exec -T redis redis-cli ping 2>/dev/null | grep -q '^PONG$'; then
    add_failure "redis ping failed"
  fi
}

systemctl_active_any() {
  local svc
  for svc in "$@"; do
    if systemctl list-unit-files "${svc}.service" >/dev/null 2>&1; then
      systemctl is-active --quiet "${svc}" && return 0
    fi
  done
  return 1
}

check_host_services() {
  if command -v systemctl >/dev/null 2>&1; then
    if ! systemctl_active_any nginx; then
      if docker inspect davarna-nginx >/dev/null 2>&1; then
        check_container "davarna-nginx" "yes"
      else
        add_failure "nginx service is not active"
      fi
    fi

    if ! systemctl_active_any cron crond; then
      add_failure "cron service is not active"
    fi

    if ! systemctl_active_any fail2ban; then
      add_failure "fail2ban service is not active"
    fi
  else
    add_warning "systemctl not available; host service checks skipped"
  fi

  if command -v nginx >/dev/null 2>&1; then
    if ! nginx -t >/dev/null 2>&1; then
      add_failure "nginx config test failed"
    fi
  fi

  if command -v fail2ban-client >/dev/null 2>&1; then
    if ! fail2ban-client status >/dev/null 2>&1; then
      add_failure "fail2ban-client status failed"
    fi
  fi
}

check_disk_path() {
  local path="$1"
  [[ -e "${path}" ]] || return 0
  local usage
  usage="$(df -P "${path}" 2>/dev/null | awk 'NR==2 {gsub("%","",$5); print $5}')"
  [[ -n "${usage}" ]] || return 0
  if (( usage >= DISK_WARN_PCT )); then
    add_failure "disk usage high: ${path} ${usage}% >= ${DISK_WARN_PCT}%"
  fi
}

check_disk() {
  check_disk_path "/"
  check_disk_path "${PROJECT_DIR}"
  check_disk_path "/var/log"
}

file_age_hours() {
  local file="$1"
  local now mtime
  now="$(date +%s)"
  mtime="$(stat -c %Y "${file}" 2>/dev/null || echo 0)"
  echo $(( (now - mtime) / 3600 ))
}

last_nonempty_line() {
  local file="$1"
  grep -v '^[[:space:]]*$' "${file}" 2>/dev/null | tail -n 1
}

check_backup_log() {
  local file="$1"
  local label="$2"
  [[ -f "${file}" ]] || return 0

  local age last_line
  age="$(file_age_hours "${file}")"
  if (( age > BACKUP_MAX_AGE_HOURS )); then
    add_failure "${label} log is stale: ${file} age=${age}h > ${BACKUP_MAX_AGE_HOURS}h"
    return
  fi

  last_line="$(last_nonempty_line "${file}")"
  if [[ -z "${last_line}" ]]; then
    add_failure "${label} log is empty: ${file}"
    return
  fi

  if [[ "${file}" == *"davarna-backup.log" ]]; then
    if [[ "${last_line}" != *"Backup sent to chat"* ]]; then
      add_failure "${label} last run does not look successful: ${last_line}"
    fi
    return
  fi

  if echo "${last_line}" | grep -Eiq 'fail|failed|error|denied|not found|traceback|exception'; then
    add_failure "${label} last run looks failed: ${last_line}"
  fi
}

check_backup_dir() {
  local dir="$1"
  local label="$2"
  [[ -n "${dir}" && -d "${dir}" ]] || return 0

  local newest
  newest="$(find "${dir}" -maxdepth 1 -type f \( -name '*.sql' -o -name '*.sql.gz' -o -name '*.gz' \) -printf '%T@ %p\n' 2>/dev/null | sort -nr | awk 'NR==1 {print $2}')"
  if [[ -z "${newest}" ]]; then
    add_failure "${label} backup directory has no backup files: ${dir}"
    return
  fi

  local age
  age="$(file_age_hours "${newest}")"
  if (( age > BACKUP_MAX_AGE_HOURS )); then
    add_failure "${label} newest backup is stale: ${newest} age=${age}h > ${BACKUP_MAX_AGE_HOURS}h"
  fi
}

check_backups() {
  check_backup_log "${MONITOR_TELEGRAM_BACKUP_LOG:-/var/log/davarna-backup.log}" "telegram backup"
  check_backup_log "${MONITOR_LOCAL_BACKUP_LOG:-/var/log/davarna-local-backup.log}" "local backup"
  check_backup_dir "${MONITOR_LOCAL_BACKUP_DIR:-}" "local mysql"

  if [[ -f /etc/cron.d/davarna-maintenance ]]; then
    if ! grep -q 'backup-db-to-telegram.sh' /etc/cron.d/davarna-maintenance; then
      add_failure "backup cron entry missing from /etc/cron.d/davarna-maintenance"
    fi
  else
    add_failure "cron file missing: /etc/cron.d/davarna-maintenance"
  fi
}

fingerprint_failures() {
  if ((${#failures[@]} == 0)); then
    echo "OK"
    return
  fi
  printf '%s\n' "${failures[@]}" | sort | sha256sum | awk '{print $1}'
}

read_state_value() {
  local key="$1"
  [[ -f "${STATE_FILE}" ]] || return 0
  awk -F= -v k="${key}" '$1 == k {print $2; exit}' "${STATE_FILE}" 2>/dev/null
}

write_state() {
  local fp="$1"
  local ts="$2"
  {
    echo "fingerprint=${fp}"
    echo "last_alert_ts=${ts}"
  } > "${STATE_FILE}" 2>/dev/null || true
}

format_message() {
  local title="$1"
  local now
  now="$(date '+%Y-%m-%d %H:%M:%S %Z')"
  {
    echo "${title}"
    echo "host: $(hostname)"
    echo "time: ${now}"
    echo
    if ((${#failures[@]} > 0)); then
      echo "Failures:"
      local item
      for item in "${failures[@]}"; do
        echo "- ${item}"
      done
    fi
    if ((${#warnings[@]} > 0)); then
      echo
      echo "Warnings:"
      local warn
      for warn in "${warnings[@]}"; do
        echo "- ${warn}"
      done
    fi
  } | head -c 3800
}

main() {
  check_project

  if ((${#failures[@]} == 0)); then
    check_containers
    check_health
    check_datastores
    check_host_services
    check_disk
    check_backups
  fi

  local fp old_fp last_alert now repeat_sec
  fp="$(fingerprint_failures)"
  old_fp="$(read_state_value fingerprint)"
  last_alert="$(read_state_value last_alert_ts)"
  now="$(date +%s)"
  repeat_sec=$(( REPEAT_ALERT_MINUTES * 60 ))

  if ((${#failures[@]} == 0)); then
    echo "${LOG_PREFIX} OK"
    if [[ -n "${old_fp}" && "${old_fp}" != "OK" ]]; then
      send_telegram "$(format_message "[RECOVERED] Davarna recovered")" || true
    fi
    write_state "OK" "${now}"
    exit 0
  fi

  echo "${LOG_PREFIX} FAIL"
  printf '%s\n' "${failures[@]}" >&2

  if [[ "${fp}" != "${old_fp}" || -z "${last_alert}" || $((now - last_alert)) -ge ${repeat_sec} ]]; then
    send_telegram "$(format_message "[ALERT] Davarna monitoring alert")" || true
    write_state "${fp}" "${now}"
  else
    echo "${LOG_PREFIX} alert suppressed; same failure fingerprint"
  fi

  exit 1
}

main "$@"
