#!/bin/sh
set -eu

if [ "$(id -u)" -eq 0 ]; then
    echo "runner acceptance workload must not run as root" >&2
    exit 41
fi

cap_eff="$(/bin/busybox awk '/^CapEff:/ { print $2 }' /proc/self/status)"
no_new_privs="$(/bin/busybox awk '/^NoNewPrivs:/ { print $2 }' /proc/self/status)"
if [ "$cap_eff" != "0000000000000000" ]; then
    echo "runner acceptance workload unexpectedly has effective capabilities: $cap_eff" >&2
    exit 41
fi
if [ "$no_new_privs" != "1" ]; then
    echo "runner acceptance workload is missing no-new-privileges" >&2
    exit 41
fi

for interface_path in /sys/class/net/*; do
    interface_name="${interface_path##*/}"
    if [ "$interface_name" != "lo" ]; then
        echo "runner acceptance workload unexpectedly has network interface: $interface_name" >&2
        exit 42
    fi
done

# Keep these probes separate from the assertions: with `set -e`, a missing or
# broken `ip` implementation fails the acceptance workload instead of being
# mistaken for an empty route table.
ipv4_routes="$(/bin/busybox ip -4 route show)"
ipv6_routes="$(/bin/busybox ip -6 route show)"
if [ -n "$ipv4_routes" ] || [ -n "$ipv6_routes" ]; then
    echo "runner acceptance workload unexpectedly has a network route" >&2
    exit 42
fi

if [ -z "${ELMOS_INPUT_DIR:-}" ] || [ ! -d "$ELMOS_INPUT_DIR" ]; then
    echo "runner input directory is unavailable" >&2
    exit 43
fi
request_path="$ELMOS_INPUT_DIR/request.json"
checkpoint_path="$ELMOS_INPUT_DIR/checkpoint.json"
if [ ! -r "$request_path" ] || [ ! -r "$checkpoint_path" ]; then
    echo "runner lease inputs are missing or unreadable" >&2
    exit 43
fi
request_size="$(/bin/busybox wc -c "$request_path" | /bin/busybox awk '{ print $1 }')"
checkpoint_size="$(/bin/busybox wc -c "$checkpoint_path" | /bin/busybox awk '{ print $1 }')"
request_digest="$(/bin/busybox sha256sum "$request_path" | /bin/busybox awk '{ print $1 }')"
checkpoint_digest="$(/bin/busybox sha256sum "$checkpoint_path" | /bin/busybox awk '{ print $1 }')"
if [ "$request_size" != "20" ] \
    || [ "$request_digest" != "1ebb4bcc6a2e74c072a099794a1d631b6427d3da78c506a5e0c08065a027fc65" ]; then
    echo "runner request bytes do not match the leased workload" >&2
    exit 43
fi
if [ "$checkpoint_size" != "2" ] \
    || [ "$checkpoint_digest" != "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a" ]; then
    echo "runner checkpoint bytes do not match the leased cursor" >&2
    exit 43
fi
request_payload="$(/bin/busybox cat "$request_path")"
checkpoint_payload="$(/bin/busybox cat "$checkpoint_path")"
if [ "$request_payload" != '{"targets":["java"]}' ]; then
    echo "runner request payload does not match the leased workload" >&2
    exit 43
fi
if [ "$checkpoint_payload" != '{}' ]; then
    echo "runner checkpoint payload does not match the leased cursor" >&2
    exit 43
fi
if /bin/busybox touch "$ELMOS_INPUT_DIR/write-probe" 2>/dev/null; then
    /bin/busybox rm -f "$ELMOS_INPUT_DIR/write-probe"
    echo "runner input directory is unexpectedly writable" >&2
    exit 43
fi

# The image deliberately includes a world-writable directory outside Podman's
# implicit tmpfs mounts. A successful write there proves that the image root was
# not mounted read-only; ordinary Unix permissions cannot make this check pass.
if /bin/busybox touch /elmos-root-probe/write-probe 2>/dev/null; then
    /bin/busybox rm -f /elmos-root-probe/write-probe
    echo "runner container root filesystem is unexpectedly writable" >&2
    exit 43
fi

if [ -z "${ELMOS_OUTPUT_DIR:-}" ] || [ ! -d "$ELMOS_OUTPUT_DIR" ]; then
    echo "runner output directory is unavailable" >&2
    exit 43
fi

printf 'request=%s\ncheckpoint=%s\n' \
    "$request_payload" "$checkpoint_payload" \
    > "$ELMOS_OUTPUT_DIR/project.zip"
