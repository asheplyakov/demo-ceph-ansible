
import os
import subprocess

KNOWN_HOSTS_FILE = os.path.expanduser('~/.ssh/known_hosts')
SSH_KEYSCAN_TIMEOUT = 10


def check_ssh_known_host(name_or_ip, known_hosts_file=KNOWN_HOSTS_FILE):
    """Check if the known_hosts_file contains ssh key of the given host"""
    try:
        subprocess.check_call(['ssh-keygen', '-F', name_or_ip,
                               '-f', known_hosts_file])
        return True
    except subprocess.CalledProcessError as e:
        if e.returncode == 1:
            return False
        else:
            raise


def remove_ssh_known_host(name_or_ip, known_hosts_file=KNOWN_HOSTS_FILE):
    """Remove ssh keys of the given host from known_hosts_file"""
    if not known_hosts_file:
        known_hosts_file = os.path.expanduser('~/.ssh/known_hosts')
    while check_ssh_known_host(name_or_ip, known_hosts_file=known_hosts_file):
        subprocess.call(['ssh-keygen', '-f', known_hosts_file,
                         '-R', name_or_ip])


def get_ssh_host_key(ips, hostname, timeout=SSH_KEYSCAN_TIMEOUT):
    for ip in ips:
        cmd = ['ssh-keyscan', '-t', 'rsa', '-T', str(timeout),
               '{ip},{hostname}'.format(ip=ip, hostname=hostname)]
        try:
            out = subprocess.check_output(cmd).strip()
        except subprocess.CalledProcessError:
            continue
        if len(out) == 0:
            continue
        hostids, prefix, key_data = out.partition('ssh-rsa')
        return prefix + key_data
    return None


def update_ssh_known_hosts(ips, hostname, ssh_key=None,
                           known_hosts_file=KNOWN_HOSTS_FILE):
    remove_ssh_known_host(hostname)
    for ip in ips:
        remove_ssh_known_host(ip)
    if ssh_key is None:
        return
    with open(known_hosts_file, 'a') as f:
        for ip in ips:
            f.write('{hostname},{ip} {ssh_key}\n'.
                    format(ssh_key=ssh_key, ip=ip, hostname=hostname))
        f.flush()
