#!/bin/sh
# Install the throwaway public key handed in via AUTHORIZED_KEY, then run sshd in
# the foreground. Test-only (see ssh-test.Dockerfile).
set -e

if [ -z "$AUTHORIZED_KEY" ]; then
    echo "AUTHORIZED_KEY not set; refusing to start a keyless sshd" >&2
    exit 1
fi

mkdir -p /home/agent/.ssh
printf '%s\n' "$AUTHORIZED_KEY" > /home/agent/.ssh/authorized_keys
chmod 700 /home/agent/.ssh
chmod 600 /home/agent/.ssh/authorized_keys
chown -R agent:agent /home/agent/.ssh

ssh-keygen -A  # generate host keys
exec /usr/sbin/sshd -D -e
