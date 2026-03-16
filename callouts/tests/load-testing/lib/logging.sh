#!/bin/bash
# Logging functions for load testing framework

# Colors
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly CYAN='\033[0;36m'
readonly NC='\033[0m' # No Color

# Log levels
LOG_LEVEL="${LOG_LEVEL:-INFO}"

log_debug() {
    [[ "$LOG_LEVEL" == "DEBUG" ]] && echo -e "${CYAN}[DEBUG]${NC} $*"
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*" >&2
}

# Progress indicator
show_progress() {
    local current="$1"
    local total="$2"
    local width=50
    local percent=$((current * 100 / total))
    local filled=$((width * current / total))
    local empty=$((width - filled))
    
    printf "\r[%-${width}s] %3d%%" "$(printf '#%.0s' $(seq 1 $filled))" "$percent"
    [[ $current -eq $total ]] && echo
}

# Timer functions
declare -A TIMERS

start_timer() {
    local name="$1"
    TIMERS["$name"]=$(date +%s%N)
}

stop_timer() {
    local name="$1"
    local start="${TIMERS[$name]}"
    local end=$(date +%s%N)
    local duration_ns=$((end - start))
    local duration_ms=$((duration_ns / 1000000))
    echo "$duration_ms"
}

# Print section header
print_section() {
    local title="$1"
    echo
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  $title${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
}

