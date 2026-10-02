#!/usr/bin/env bash
#
# check_github_access.sh
# ----------------------
# Checks whether this VM can reach GitHub, and how:
#   1. HTTPS  -> github.com:443
#   2. SSH    -> github.com:22
#   3. If SSH:22 is blocked, tries SSH through the corporate proxy
#      (proxy.infosec.fedex.com:443) using the ssh.github.com:443 endpoint.
#
# Exit code: 0 if GitHub is reachable by ANY method, 1 if all methods fail.
#
# Usage:   ./check_github_access.sh
# Requires: bash, plus (optionally) nc/ncat, openssl, ssh, git.

set -u

# ---- Config -----------------------------------------------------------------
GH_HOST="github.com"
HTTPS_PORT=443
SSH_PORT=22
SSH_HOST_ALT="ssh.github.com"   # GitHub's SSH-over-443 endpoint
SSH_ALT_PORT=443

PROXY_HOST="proxy.infosec.fedex.com"
PROXY_PORT=443

TIMEOUT=8   # seconds per network probe

# ---- Pretty output ----------------------------------------------------------
GREEN=$'\033[32m'; RED=$'\033[31m'; YELLOW=$'\033[33m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
pass() { printf "  ${GREEN}[ PASS ]${RESET} %s\n" "$1"; }
fail() { printf "  ${RED}[ FAIL ]${RESET} %s\n" "$1"; }
info() { printf "  ${YELLOW}[ INFO ]${RESET} %s\n" "$1"; }
head() { printf "\n${BOLD}== %s ==${RESET}\n" "$1"; }

have() { command -v "$1" >/dev/null 2>&1; }

# ---- Generic TCP reachability check -----------------------------------------
# Tries, in order: nc, ncat, /dev/tcp (bash builtin). Returns 0 if port open.
tcp_check() {
    local host="$1" port="$2"
    if have nc; then
        nc -z -w "$TIMEOUT" "$host" "$port" >/dev/null 2>&1 && return 0 || return 1
    elif have ncat; then
        ncat -z -w "${TIMEOUT}s" "$host" "$port" >/dev/null 2>&1 && return 0 || return 1
    else
        # Bash /dev/tcp fallback (no external tools)
        timeout "$TIMEOUT" bash -c "exec 3<>/dev/tcp/${host}/${port}" >/dev/null 2>&1 && return 0 || return 1
    fi
}

# ---- 1. HTTPS 443 -----------------------------------------------------------
check_https() {
    head "1. HTTPS  ->  ${GH_HOST}:${HTTPS_PORT}"
    if tcp_check "$GH_HOST" "$HTTPS_PORT"; then
        pass "TCP connect to ${GH_HOST}:${HTTPS_PORT} succeeded"
        if have openssl; then
            if echo | timeout "$TIMEOUT" openssl s_client -connect "${GH_HOST}:${HTTPS_PORT}" \
                    -servername "$GH_HOST" 2>/dev/null | grep -q "CN *= *github.com\|subject="; then
                pass "TLS handshake OK (valid GitHub certificate presented)"
            else
                info "TCP open but TLS handshake could not be confirmed (possible TLS-inspecting proxy)"
            fi
        fi
        return 0
    fi
    fail "Cannot reach ${GH_HOST}:${HTTPS_PORT}"
    return 1
}

# ---- 2. SSH 22 (direct) -----------------------------------------------------
check_ssh_direct() {
    head "2. SSH  ->  ${GH_HOST}:${SSH_PORT} (direct)"
    if tcp_check "$GH_HOST" "$SSH_PORT"; then
        pass "TCP connect to ${GH_HOST}:${SSH_PORT} succeeded"
        if have ssh; then
            # GitHub returns a banner + "successfully authenticated" note even without a shell.
            if ssh -T -o BatchMode=yes -o StrictHostKeyChecking=no \
                   -o ConnectTimeout="$TIMEOUT" "git@${GH_HOST}" 2>&1 | grep -q "successfully authenticated"; then
                pass "SSH authenticated to git@${GH_HOST} (key works)"
            else
                info "Port 22 open; SSH reachable (auth banner not confirmed — check your SSH key)"
            fi
        fi
        return 0
    fi
    fail "Cannot reach ${GH_HOST}:${SSH_PORT} directly"
    return 1
}

# ---- 3. SSH via corporate proxy (CONNECT to ssh.github.com:443) -------------
check_ssh_via_proxy() {
    head "3. SSH via proxy  ->  ${PROXY_HOST}:${PROXY_PORT}  ==>  ${SSH_HOST_ALT}:${SSH_ALT_PORT}"

    # 3a. Is the proxy itself reachable?
    if ! tcp_check "$PROXY_HOST" "$PROXY_PORT"; then
        fail "Proxy ${PROXY_HOST}:${PROXY_PORT} is not reachable"
        return 1
    fi
    pass "Proxy ${PROXY_HOST}:${PROXY_PORT} is reachable"

    # 3b. Need a CONNECT helper: prefer ncat --proxy, else corkscrew.
    local proxy_cmd=""
    if have ncat; then
        proxy_cmd="ncat"
    elif have corkscrew; then
        proxy_cmd="corkscrew"
    else
        info "No 'ncat' or 'corkscrew' found — cannot tunnel SSH through the proxy from this script."
        info "Install one of them, or add the ProxyCommand block below to ~/.ssh/config."
        print_ssh_config_hint
        return 1
    fi

    # 3c. Try an actual SSH handshake through the proxy using ProxyCommand.
    if have ssh; then
        local pc
        if [ "$proxy_cmd" = "ncat" ]; then
            pc="ncat --proxy ${PROXY_HOST}:${PROXY_PORT} --proxy-type http %h %p"
        else
            pc="corkscrew ${PROXY_HOST} ${PROXY_PORT} %h %p"
        fi

        info "Using ProxyCommand: ${pc}"
        if ssh -T -o BatchMode=yes -o StrictHostKeyChecking=no \
               -o ConnectTimeout="$TIMEOUT" \
               -o ProxyCommand="$pc" \
               -p "$SSH_ALT_PORT" "git@${SSH_HOST_ALT}" 2>&1 | grep -q "successfully authenticated"; then
            pass "SSH via proxy authenticated to git@${SSH_HOST_ALT}:${SSH_ALT_PORT}"
            print_ssh_config_hint
            return 0
        else
            # Tunnel may still open even if key auth isn't set up; test raw CONNECT.
            if [ "$proxy_cmd" = "ncat" ] && \
               timeout "$TIMEOUT" ncat --proxy "${PROXY_HOST}:${PROXY_PORT}" --proxy-type http \
                   "$SSH_HOST_ALT" "$SSH_ALT_PORT" </dev/null 2>&1 | grep -q "SSH-2.0"; then
                pass "Proxy tunnel to ${SSH_HOST_ALT}:${SSH_ALT_PORT} works (SSH banner received)"
                info "Tunnel OK — if auth failed, check your SSH key on GitHub."
                print_ssh_config_hint
                return 0
            fi
            fail "Could not establish SSH through the proxy"
            return 1
        fi
    fi

    info "ssh client not installed — cannot complete proxy SSH test."
    return 1
}

# ---- Persistent config the user can paste into ~/.ssh/config ----------------
print_ssh_config_hint() {
    cat <<EOF

  ${BOLD}To make this permanent, add to ~/.ssh/config:${RESET}

    Host github.com
        HostName ssh.github.com
        Port 443
        User git
        ProxyCommand ncat --proxy ${PROXY_HOST}:${PROXY_PORT} --proxy-type http %h %p
        # (or, with corkscrew:)
        # ProxyCommand corkscrew ${PROXY_HOST} ${PROXY_PORT} %h %p

  Then test with:  ssh -T git@github.com
EOF
}

# ---- Main -------------------------------------------------------------------
main() {
    printf "${BOLD}GitHub connectivity check${RESET}  (host: ${GH_HOST}, timeout: ${TIMEOUT}s)\n"
    printf "Date: %s\n" "$(date)"

    local https_ok=1 ssh_ok=1 proxy_ok=1

    check_https      && https_ok=0
    check_ssh_direct && ssh_ok=0

    if [ "$ssh_ok" -ne 0 ]; then
        info "Direct SSH:22 failed — attempting SSH through the corporate proxy..."
        check_ssh_via_proxy && proxy_ok=0
    else
        head "3. SSH via proxy"
        pass "Skipped — direct SSH:22 already works, no proxy needed."
        proxy_ok=0
    fi

    # ---- Summary ----
    head "SUMMARY"
    [ "$https_ok" -eq 0 ] && pass "HTTPS github.com:443       reachable"      || fail "HTTPS github.com:443       BLOCKED"
    [ "$ssh_ok"   -eq 0 ] && pass "SSH   github.com:22        reachable"      || fail "SSH   github.com:22        BLOCKED"
    if [ "$ssh_ok" -ne 0 ]; then
        [ "$proxy_ok" -eq 0 ] && pass "SSH   via proxy:443        reachable" || fail "SSH   via proxy:443        BLOCKED"
    fi

    if [ "$https_ok" -eq 0 ] || [ "$ssh_ok" -eq 0 ] || [ "$proxy_ok" -eq 0 ]; then
        printf "\n${GREEN}${BOLD}RESULT: GitHub is reachable from this VM.${RESET}\n"
        exit 0
    fi
    printf "\n${RED}${BOLD}RESULT: GitHub is NOT reachable by any tested method.${RESET}\n"
    exit 1
}

main "$@"
