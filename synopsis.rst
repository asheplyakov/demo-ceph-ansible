Preliminaries
=============

Lab description
---------------

* (virtual) hardware: libvirt/kvm VMs managed by MAAS_ (version 1.9):
  - 3 OSD nodes having 3 (virtual) hard drives per a node
  - 3 monitor nodes
  - 1 radosgw node
  - 1 client node
* software: Ubuntu 14.04, ceph 10.2.1 (jewel), `self built packages`_
* ansible version: 2.1.0 from *ppa:ansible/ansible*
* (virtual) networks:
  - ``client_net`` network, 10.253.0.0/24, client-cluster traffic goes here
  - ``cluster_net`` network, 10.250.0.0/24, intra-cluster traffic goes here
  - ``pxe_net`` network, 10.40.0.0/24, provisioning (MAAS_) and deployment (ssh) traffic
  - ``10.40.0.2`` runs the MAAS_ server

.. _self built packages: http://asheplyakov.srt.mirantis.net/Public/repos/ceph
.. _ceph-ansible: http://github.com/ceph/ceph-ansible
.. _MAAS: https://maas.ubuntu.com/docs1.9/index.html

Preparation
-----------

* Install ansible on the host::

    sudo apt-add-repository ppa:ansible/ansible
    sudo apt-get update
    sudo apt-get install -y ansible

* Clone this repository::

    git clone --recursive https://github.com/asheplyakov/demo-ceph-ansible.git

* Define 8 VMs and corresponding virtual drives, networks, etc

* Add VMs to MAAS, use the ``maas_tools/match_maas_libvirt.py`` helper
  script to tell MAAS how to power on/off VMs

* Comission the nodes

* Tag the nodes to set their roles:

  - mark monitor nodes with ``ansible_mons`` tag
  - mark OSD nodes with ``ansible_osds`` tag
  - mark radosgw nodes with ``ansible_rgws`` tag
  - mark the client nodes with ``ansible_clients`` tag

  Manual tagging is boring, use ``maas_tools/tag_osds.py`` script to tag
  all nodes having >=2 hard drives as OSDs (and tag other nodes as
  ``clients``). After that one can tag monitors (and radosgw) nodes
  manually (usually there are only a handful of such nodes).


* Tag the storage devices:

  - mark OSD data drives with ``ansible_osd_data`` tag
  - mark OSD journal drives with  ``ansible_osd_journal`` tag

* Configure the nodes' ``eth1`` and ``eth2`` interfaces to obtain
  the IP address via dhcp. ``maas_tools/tag_osds.py`` automates this too.

* Install Ubuntu 14.04 on those VMs with MAAS

* Fetch the nodes' SSH keys::

    ./maas_inventory.py --ssh-keys

  This step is crucial for ansible to be able to connect to the nodes

Deployment
==========

Cluster configuration
---------------------

Mandatory and important settings:

* OSD data and journal devices

  - The inventory script sets the OSD data and journal drives on a per host basis
    using stable identifiers (udev generated synlinks in ``/dev/disk/by-id``)
    instead of the traditional ones (like */dev/sda*).
    In general the traditional identifiers can
      - change across reboots (it used to be */dev/sda* before the reboot,
        but now it's */dev/sdb*)
      - vary between nodes even if the hardware is the same (*/dev/sda*
        is an SSD on *osd1*, but it's a HDD on *osd2*)
    Stable identifers help to avoid surprises, however they are unique
    (depend on the drive serial number, model name, etc) and should be
    specified on a per host basis.

  - one can override inventory script (or skip tagging the storage devices)
    using the per host (group) variables::

     devices:
       - /dev/disk/by-id/ata-fooXXXHDD
       - /dev/disk/by-id/ata-barYYYHDD

     raw_journal_devices:
       - /dev/disk/by-id/ata-blahSSD
       - /dev/disk/by-id/ata-blahSSD

    Note: the same drive specified twice (once per an OSD), it will be partitioned
    so both OSDs defined above can use it as a journal. Thus it's possible to use
    a single SSD with several rotating drives.


* ``group_vars/all``

  - enable ``cephx`` authentication::

      cephx: true

  - use filestore, set journal size to 3 GB::

      osd_objectstore: filestore
      journal_size: 3072

  - pools' settings:: 

      pool_default_size: 3
      pool_default_min_size: 2
      pool_default_pg_num: 128
      pool_default_pgp_num: 128

  - network settings::
    
      public_network: 10.253.0.0/24
      cluster_network: 10.252
      monitor_interface: eth1

    Every node has a single (virtual) NIC, hence no separate cluster network.

  - client settings: specify rbd features compatible with rbd client included in
    Linux kernel 3.13.x (the default kernel version shipped with Ubuntu 14.04)::

      ceph_conf_overrides:
        client:
          rbd default features: 3

  - tell ceph-ansible to *not* touch APT configuration::

      ceph_origin: 'distro'

  - add a repository with custom ceph packages, add pinning rules::

      ceph_apt_repo:
        url: "deb http://asheplyakov.srt.mirantis.net/Public/repos/ceph {{ ceph_release }}-{{ os_release }} main"
        label: "sa-{{ ceph_release }}-{{ os_release }}"
        gpg_keyid: 69514C18
        priority: 1050


  - ceph is picky about nodes' system time being out of sync. run *ntpdate*
    using the specified NTP server::

      ntp_server: 10.253.0.1
      sync_time: true

  - radosgw and ``civetweb`` settings: ``radosgw_civetweb_bind_ip`` *must*
    be specified to avoid ansible failure::

      radosgw_frontend: civetweb
      radosgw_civetweb_bind_ip: 0.0.0.0
      radosgw_civetweb_port: 8080

* ``group_vars/osds``

  - put all journals to the same drive (presumably SSD)::

      raw_multi_journal: true

  - set the actual data and journal devices on a per node basis by
    the inventory script (and can be overriden by host/group variables)
    Note: the drives should have a valid GPT with no paritions defined,
    otherwise ``ceph-ansible`` refuses to use the device

  - mandatory settings::

      fsid "{{ cluster_uuid.stdout }}"
      cephx: true

* ``group_vars/mons``

  - nothing special here, just a boilerplate::

      fsid: "{{ cluster_uuid.stdout }}"
      monitor_secret: "{{ monitor_keyring.stdout }}"
      cephx: true
      pool_default_pg_num: 128


Preflight checks
----------------

* Check if VMs are reachable via ssh::

    $ ansible -m ping -i ./maas_inventory.py all
    saceph-adm.maas | SUCCESS => {
       "changed": false, 
       "ping": "pong"
    }
    # and so on


Deploy it
---------

**WARNING**: this wipes out the data from the OSD drives. Before running this
command please make sure the inventory file (*hosts*) does **NOT** point to
your production cluster::

  ansible-playbook -i ./maas_inventory.py site.yml


Benchmark
---------

Create 32G rbd image named ``test${hostname}.img``, map it, create ext4 filesystem,
mount it and write ``fio`` randwrite benchmark::

  ansible -m shell -i ./maas_inventory.py clients -a "/opt/rbd-test.sh"

