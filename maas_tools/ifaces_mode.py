#!/usr/bin/env python
# encoding: utf-8
# Tell MAAS how to configure nodes' network interfaces

import os
import requests
import sys

from optparse import OptionParser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from maas_base_client import MaasBaseClient

DHCP = 'dhcp'
LINK_UP = 'link_up'


class MaasClient(MaasBaseClient):

    def unlink_iface(self, iface_uri, link_id=None):
        url = '{0}{1}/?op=unlink_subnet'.format(self._base_url, iface_uri)
        rq = requests.post(url, data={'id': link_id}, headers=self._auth())
        rq.raise_for_status()

    def link_iface(self, iface_uri, subnet_id=None, link_id=None,
                   mode=LINK_UP):
        if mode.lower() == LINK_UP:
            self.unlink_iface(iface_uri, link_id=link_id)
        else:
            url = '{0}{1}?op=link_subnet'.format(self._base_url, iface_uri)
            data = {
                'mode': mode,
                'subnet': subnet_id,
            }
            rq = requests.post(url, data=data, headers=self._auth())
            rq.raise_for_status()

    def _set_links_mode(self, iface, mode=DHCP):
        links = (link for link in iface['links']
                 if link['mode'].lower() != mode.lower())
        for link in links:
            self.link_iface(iface['resource_uri'],
                            subnet_id=link['subnet']['id'],
                            link_id=link['id'],
                            mode=mode)

    def _set_nonpxe_ifaces_mode(self, node, mode=DHCP):
        pxe_mac = node['pxe_mac']['mac_address']
        ifaces = (iface for iface in node['interface_set']
                  if iface['mac_address'] != pxe_mac)
        for iface in ifaces:
            try:
                self._set_links_mode(iface, mode)
            except:
                print("{host}: failed to set {ifname} to {mode}".format(
                    host=node['hostname'],
                    mode=mode,
                    ifname=iface['name']))

    def set_nonpxe_ifaces_mode(self, nodes=None, mode=DHCP):
        if not nodes:
            nodes = self.nodes()
        for node in nodes:
            self._set_nonpxe_ifaces_mode(node, mode=mode)


def main():
    parser = OptionParser()
    parser.add_option('-m', '--maas-host', dest='maas_host')
    parser.add_option('-u', '--maas-user', dest='maas_user')
    parser.add_option('-M', '--link-mode', dest='link_mode', default=DHCP)
    options, args = parser.parse_args()
    maas_client = MaasClient(host=options.maas_host, user=options.maas_user)
    maas_client.set_nonpxe_ifaces_mode(mode=options.link_mode)


if __name__ == '__main__':
    main()
