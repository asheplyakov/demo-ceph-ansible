#!/usr/bin/env python
# encoding: utf-8
# tag all nodes as OSDs
# tag all unused storage as OSD data

import json
import oauth.oauth as oauth
import requests
import subprocess
import uuid

from collections import defaultdict
from optparse import OptionParser
from urlparse import urlparse

MAAS_HOST = '127.0.0.1'
MAAS_USER = 'root'
CLIENT_TAG = 'ansible_clients'
OSD_TAG = 'ansible_osds'
OSD_DATA_TAG = 'ansible_osd_data'
SHELL_USER = 'ubuntu'


class MaasClient(object):
    def __init__(self, api_url=None, token=None,
                 host=None, user=None,
                 shell_user=None):
        if not api_url and not host:
            host = MAAS_HOST
        if not token and not user:
            user = MAAS_USER
        if not token and not shell_user:
            shell_user = SHELL_USER
        if not api_url:
            api_url = 'http://%s:5240/MAAS/api/1.0' % host
        if not host:
            host = urlparse(api_url).hostname
        if not token:
            token = self._get_token(host, user, shell_user)
        dissected_api_url = urlparse(api_url)
        self._token = token
        self._api_url = api_url
        self._base_url = '{0}://{1}'.format(dissected_api_url.scheme,
                                            dissected_api_url.netloc)

    def _auth(self):
        consumer_key, key, secret = self._token.split(':')
        resource_token = oauth.OAuthToken(key, secret)
        consumer_token = oauth.OAuthConsumer(consumer_key, '')
        oauth_request = oauth.OAuthRequest.from_consumer_and_token(
            consumer_token,
            token=resource_token,
            http_url=self._api_url,
            parameters={
                'auth_nonce': uuid.uuid4().get_hex(),
            }
        )
        oauth_request.sign_request(oauth.OAuthSignatureMethod_PLAINTEXT(),
                                   consumer_token,
                                   resource_token)
        return oauth_request.to_header()

    def _get_token(self, host, user, shell_user):
        cmd = [
            'ssh', '%s@%s' % (shell_user, host),
            'sudo', 'maas-region-admin', 'apikey',
            '--username=%s' % user
        ]
        return subprocess.check_output(cmd).strip()

    def tag_nodes(self, system_ids, tag):
        url = '%s/tags/%s/?op=update_nodes' % (self._api_url, tag)
        rq = requests.post(url, data={'add': system_ids},
                           headers=self._auth())
        rq.raise_for_status()

    def tag_drive(self, drive_uri, tag, remove=False):
        drive_url = self._base_url + drive_uri
        params = {
            'tag': tag,
            'op': 'remove_tag' if remove else 'add_tag',
        }
        rq = requests.get(drive_url, params=params, headers=self._auth())
        rq.raise_for_status()

    def unlink_iface(self, iface_uri, link_id=None):
        url = '{0}{1}/?op=unlink_subnet'.format(self._base_url, iface_uri)
        rq = requests.post(url, data={'id': link_id}, headers=self._auth())
        rq.raise_for_status()

    def link_iface(self, iface_uri, subnet_id=None, link_id=None,
                   mode='LINK_UP'):
        if mode.lower() == 'link_up':
            self.unlink_iface(iface_uri, link_id=link_id)
        else:
            url = '{0}{1}?op=link_subnet'.format(self._base_url, iface_uri)
            data = {
                'mode': mode,
                'subnet': subnet_id,
            }
            rq = requests.post(url, data=data, headers=self._auth())
            rq.raise_for_status()

    def update_node(self, system_id, params=None):
        # note: trailing slash is mandatory
        url = '%s/nodes/%s/' % (self._api_url, system_id)
        rq = requests.put(url, data=params, headers=self._auth())
        rq.raise_for_status()

    def nodes(self):
        url = '%s/nodes/?op=list' % self._api_url
        rq = requests.get(url, headers=self._auth())
        rq.raise_for_status()
        return json.loads(rq.text)


def tag_nodes(maas_client, nodes=None,
              osd_tag=None, storage_tag=None, client_tag=None):
    if not nodes:
        nodes = maas_client.nodes()
    nodes_to_tag = defaultdict(list)
    osd_drives = []
    for node in nodes:
        drives = filter(lambda blk: blk['used_for'] == 'Unused',
                        node['physicalblockdevice_set'])
        if len(drives) == 0:
            nodes_to_tag[client_tag].append(node['system_id'])
        else:
            nodes_to_tag[osd_tag].append(node['system_id'])
            osd_drives.extend([disk['resource_uri'] for disk in drives])
    for tag, node_ids in dict(nodes_to_tag).iteritems():
        maas_client.tag_nodes(node_ids, tag)
    for drive_uri in osd_drives:
        maas_client.tag_drive(drive_uri, storage_tag)


def _set_links_mode(maas_client, iface, mode='DHCP'):
    links = (link for link in iface['links']
             if link['mode'].lower() != mode.lower())
    for link in links:
        maas_client.link_iface(iface['resource_uri'],
                               subnet_id=link['subnet']['id'],
                               link_id=link['id'],
                               mode=mode)


def _set_nonpxe_ifaces_mode(maas_client, node, mode='DHCP'):
    pxe_mac = node['pxe_mac']['mac_address']
    ifaces = (iface for iface in node['interface_set']
              if iface['mac_address'] != pxe_mac)
    for iface in ifaces:
        try:
            _set_links_mode(maas_client, iface, mode)
        except:
            print("{host}: failed to set {ifname} to {mode}".format(
                host=node['hostname'],
                mode=mode,
                ifname=iface['name']))


def set_nonpxe_ifaces_mode(maas_client, nodes=None, mode='DHCP'):
    if not nodes:
        nodes = maas_client.nodes()
    for node in nodes:
        _set_nonpxe_ifaces_mode(maas_client, node, mode=mode)


def main():
    parser = OptionParser()
    parser.add_option('-m', '--maas-host', dest='maas_host', default=MAAS_HOST)
    parser.add_option('-u', '--maas-user', dest='maas_user', default=MAAS_USER)
    parser.add_option('-t', '--osd-tag', dest='osd_tag', default=OSD_TAG)
    parser.add_option('-s', '--storage-tag', dest='storage_tag',
                      default=OSD_DATA_TAG)
    parser.add_option('-c', '--client-tag', dest='client_tag',
                      default=CLIENT_TAG)
    parser.add_option('-d', '--net-dhcp', dest='ifaces_dhcp',
                      default=False, action='store_true',
                      help='mark all non-PXE interfaces as DHCP')
    options, args = parser.parse_args()
    maas_client = MaasClient(host=options.maas_host, user=options.maas_user)
    if options.ifaces_dhcp:
        set_nonpxe_ifaces_mode(maas_client, mode='DHCP')
    tag_nodes(maas_client,
              osd_tag=options.osd_tag,
              storage_tag=options.storage_tag,
              client_tag=options.client_tag)


if __name__ == '__main__':
    main()
