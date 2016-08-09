#!/usr/bin/env python
# encoding: utf-8
# Set power parameters of VMs managed by MAAS so that MAAS can power on/off
# virtual nodes. As a side effect the DNS names of MAAS nodes are set to
# the corresponding libvirt VMs names.
# MAAS nodes are matched to libvirt VMs by the set of MAC addresses.

import json
import oauth.oauth as oauth
import requests
import subprocess
import uuid

from optparse import OptionParser
from urlparse import urlparse
from xml.etree import ElementTree


DEFAULT_LIBVIRT_URL = 'qemu:///system'
MAAS_HOST = '127.0.0.1'
MAAS_USER = 'root'


def maas_auth_headers(api_url, token=None):
    consumer_key, key, secret = token.split(':')
    resource_token = oauth.OAuthToken(key, secret)
    consumer_token = oauth.OAuthConsumer(consumer_key, '')
    oauth_request = oauth.OAuthRequest.from_consumer_and_token(
        consumer_token,
        token=resource_token,
        http_url=api_url,
        parameters={
            'auth_nonce': uuid.uuid4().get_hex(),
        },
    )
    oauth_request.sign_request(oauth.OAuthSignatureMethod_PLAINTEXT(),
                               consumer_token,
                               resource_token)
    return oauth_request.to_header()


def get_maas_nodes_by_macs(api_url, token=None):
    url = '%s/nodes/?op=list' % api_url
    rq = requests.get(url, headers=maas_auth_headers(api_url, token))
    rq.raise_for_status()
    nodes = json.loads(rq.text)

    def to_tuple(macset):
        return tuple(sorted(addr['mac_address'] for addr in macset))

    return dict((to_tuple(n['macaddress_set']), n) for n in nodes)


def update_maas_node(system_id, params=None, api_url=None, token=None):
    url = '%s/nodes/%s/' % (api_url, system_id)
    auth_headers = maas_auth_headers(api_url, token)
    rq = requests.put(url, data=params, headers=auth_headers)
    rq.raise_for_status()


def get_maas_token(maas_host=MAAS_HOST, maas_user=MAAS_USER,
                   remote_user='ubuntu'):
    cmd = [
        'ssh', '%s@%s' % (remote_user, maas_host),
        'sudo', 'maas-region-admin', 'apikey',
        '--username=%s' % maas_user,
    ]
    token = subprocess.check_output(cmd).strip()
    return token


def get_vm_macs(name, conn=DEFAULT_LIBVIRT_URL):
    raw_xml = subprocess.check_output(['virsh', '-c', conn, 'dumpxml', name])
    vmxml = ElementTree.fromstring(raw_xml.strip())
    macs = vmxml.findall("devices/interface/[@type='network']/mac")
    return tuple(sorted(e.get('address') for e in macs))


def get_libvirt_vms_by_macs(vms, conn=DEFAULT_LIBVIRT_URL):
    if vms is None or len(vms) == 0:
        vms = get_libvirt_vms(conn)
    return dict((get_vm_macs(vm, conn), vm) for vm in vms)


def get_libvirt_vms(conn='qemu:///system'):
    cmd = ['virsh', '-c', conn, '-q', 'list', '--all']
    raw_out = subprocess.check_output(cmd).strip()
    for line in raw_out.split('\n'):
        vmid, vmname, vmstate = line.split(None, 2)
        yield vmname


def verify_libvirt_connection(libvirt_conn,
                              host=None,
                              remote_user='ubuntu'):
    """Check if libvirt connection is reachable from host"""
    cmd = []
    if host:
        cmd.extend(['ssh', '%s@%s' % (remote_user, host)])
    cmd.extend(['virsh', '-c', libvirt_conn, '-q', 'list', '--all'])
    subprocess.check_output(cmd)


def set_maas_power_params(libvirt_conn=DEFAULT_LIBVIRT_URL,
                          local_libvirt_conn=DEFAULT_LIBVIRT_URL,
                          maas_api=None,
                          maas_host=None,
                          maas_user=MAAS_USER,
                          maas_token=None):

    if maas_host is None and maas_api is None:
        maas_host = MAAS_HOST
    if maas_host is None:
        maas_host = urlparse(maas_api).hostname
    if maas_api is None:
        maas_api = 'http://%s/MAAS/api/1.0' % maas_host
    if maas_token is None:
        maas_token = get_maas_token(maas_host=maas_host, maas_user=maas_user)

    verify_libvirt_connection(libvirt_conn, host=maas_host)

    # Identify the nodes by set of their MACs
    maas_nodes_by_macs = get_maas_nodes_by_macs(maas_api, token=maas_token)
    vms_by_macs = get_libvirt_vms_by_macs(None, local_libvirt_conn)
    for macset, node in maas_nodes_by_macs.iteritems():
        vm_name = vms_by_macs.get(macset)
        if vm_name is None:
            continue
        old_hostname, domain = node['hostname'].split('.', 1)
        params = {
            'power_parameters_power_address': libvirt_conn,
            'power_parameters_power_id': vm_name,
            'power_type': 'virsh',
            'hostname': '%s.%s' % (vm_name, domain),
        }
        update_maas_node(node['system_id'], params=params,
                         api_url=maas_api, token=maas_token)


def main():
    parser = OptionParser()
    parser.add_option('-c', '--libvirt-connection',
                      dest='libvirt_conn',
                      help='how to connect to libvirt from the MAAS server')
    parser.add_option('-l', '--local-libvirt-connection',
                      dest='local_libvirt_conn', default=DEFAULT_LIBVIRT_URL,
                      help='how to connect to libvirt from the local host')
    parser.add_option('-u', '--maas-user', dest='maas_user', default='root')
    parser.add_option('-m', '--maas-host', dest='maas_host')
    parser.add_option('-a', '--maas-api', dest='maas_api_url')
    parser.add_option('-t', '--maas-token', dest='maas_token')
    options, vms = parser.parse_args()
    set_maas_power_params(libvirt_conn=options.libvirt_conn,
                          local_libvirt_conn=options.local_libvirt_conn,
                          maas_api=options.maas_api_url,
                          maas_host=options.maas_host,
                          maas_user=options.maas_user,
                          maas_token=options.maas_token)


if __name__ == '__main__':
    main()
