import errno
import json
import libvirt
import os
import shlex
import socket
from io import BytesIO
from subprocess import check_output
from xml.etree import ElementTree as ET

from paramiko import AutoAddPolicy, SSHClient, SSHConfig

from leappto import AbstractMachineProvider, MachineType, Machine, Disk, \
        Package, OperatingSystem, Installation
from leappto.providers.ssh_provider import SSHMachineProvider

class LibvirtMachine(Machine):
    # TODO: Libvirt Python API doesn't seem to expose 
    # virDomainSuspend and virDomainResume so use Virsh
    # for the time being
    def suspend(self):
        return check_output(['sudo', 'virsh', 'suspend', self.id])

    def resume(self):
        return check_output(['sudo', 'virsh', 'resume', self.id])


class LibvirtMachineProvider(AbstractMachineProvider):
    def __init__(self, shallow_scan=True):
        self._connection = libvirt.open('qemu:///system')
        self._shallow_scan = shallow_scan
        # Stupid `libvirt` cannot carry out certain *read only* operations while
        # being in read-only mode so just use `open` and fix this later by enumerating
        # networks, checking the MAC of the domain and correlating this against DHCP leases
        # self._connection = libvirt.openReadOnly('qemu:///system')

    @property
    def connection(self):
        return self._connection

    def __del__(self):
        if self._connection:
            self._connection.close()
        del self._connection

    def get_machines(self):
        """
        Get `Machine` description for each active machine

        :return: List[Machine], List of machines running on the system
        """

        def __get_attribute(elem, attr):
            """
            Get attribute if we have valid element

            :param elem: xml.etree.ElementTree.Element, element
            :param attr: str, attribute name
            :return: str, attribute value
            """
            if elem is not None:
                return elem.get(attr)

        def __get_storage(disks):
            """
            Get `Disk` objects from XML

            :param disks: List[xml.etree.ElementTree.Element], disk xml elements
            :return: List[Disk], list of Disks
            """
            storage = []
            for disk in disks:
                type_ = disk.get('type')
                backing_file = __get_attribute(disk.find('source[@file]'), 'file')
                driver_type = __get_attribute(disk.find('driver[@type]'), 'type')
                device = __get_attribute(disk.find('target[@dev]'), 'dev')
                storage.append(Disk(type_, backing_file, device, driver_type))
            return storage

        def __get_vagrant_data_path_from_domain(domain_name):
            index_path = os.path.join(os.environ['HOME'], '.vagrant.d/data/machine-index/index')
            index = json.load(open(index_path, 'r'))
            for ident, machine in index['machines'].iteritems():
                path_name = os.path.basename(machine['vagrantfile_path'])
                vagrant_name = machine.get('name', 'default')
                if domain_name == path_name + '_' + vagrant_name:
                    return machine['local_data_path']
            return None

        def __get_vagrant_ssh_args_from_domain(domain_name):
            path = __get_vagrant_data_path_from_domain(domain_name)
            path = os.path.join(path, 'provisioners/ansible/inventory/vagrant_ansible_inventory')
            with open(path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line[0] in (';', '#'):
                        continue
                    return __parse_ansible_inventory_data(line)
            return None

        def __parse_ansible_inventory_data(line):
            parts = shlex.split(line)
            if parts:
                parts = parts[1:]
            args = {}
            mapping = {
                    'ansible_ssh_port': ('port', int),
                    'ansible_ssh_host': ('hostname', str),
                    'ansible_ssh_private_key_file': ('key_filename', str),
                    'ansible_ssh_user': ('username', str)}
            for part in parts:
                key, value = part.split('=', 1)
                if key in mapping:
                    args[mapping[key][0]] = mapping[key][1](value)
            return args

        def __get_vagrant_ssh_client_for_domain(domain_name):
            args = __get_vagrant_ssh_args_from_domain(domain_name)
            if args:
                client = SSHClient()
                client.load_system_host_keys()
                client.set_missing_host_key_policy(AutoAddPolicy())
                client.connect(args.pop('hostname'), **args)
                return client
            return None

        def __get_os_info(domain_name, shallow):
            client = __get_vagrant_ssh_client_for_domain(domain_name)
            if not client:
                return None
            return SSHMachineProvider._get_os_info(client, shallow)

        def __domain_info(domain):
            """
            Create `Machine` description out of `virDomain` object

            :param domain: libvirt.virDomain, Domain for which to fetch the information
            """
            desc = domain.XMLDesc()
            root = ET.fromstring(desc)

            os_type = root.find('os/type')
            typ = next(os_type.itertext())
            vt = MachineType.Default

            if 'kvm' in root.get('type'):
                vt |= MachineType.Kvm
            if 'hvm' in typ:
                vt |= MachineType.Hvm

            '''
            Too much log spew and doesn't work

            try:
                # This can fail on a number of occasions:
                # 1) Theres no guest agent installed
                # 2) The connection doesn't support the call
                hostname = domain.hostname()
            except libvirt.libvirtError:
                hostname = None
            '''

            ips, hostname, inst = __get_os_info(domain.name(), self._shallow_scan)

            storage = __get_storage(root.findall("devices/disk[@device='disk']"))

            return LibvirtMachine(domain.UUIDString(), hostname,
                                  ips, os_type.get('arch'), vt, storage,
                                  next(root.find('name').itertext()), inst, self)

        domains = self.connection.listAllDomains(0)
        return [__domain_info(dom) for dom in domains if dom.isActive()]
