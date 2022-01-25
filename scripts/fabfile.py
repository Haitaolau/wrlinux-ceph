import os
from datetime import datetime
from jinja2 import Environment, FileSystemLoader, select_autoescape
from importlib import import_module
import importlib.util
from invoke import task
from invoke import Responder
import subprocess
import socket
from fabric import Connection

@task
def test(c):
    c.run('echo "hello" >> /1.log')


@task
def getFile(c,name):
    """
    get file from remote (fab -H ceph1 getFile --name=/tmp/monmap)
    """
    c.get(name)

@task
def putFile(c,name,path):
    """
    upload the file to remote
    """
    c.put(name,path)

@task
def mon_copy(c):
    """
    copy the configure files to the remote
    """
    sudopass = Responder(pattern=r'password:',response='ceph\n')
    ceph_list = c.run("virsh list | awk '/ceph/{print $2}' | tr '\n' ' '",hide=True).stdout.strip('\n').split()
    for node in ceph_list:
        c.run(f"scp ./monmap {node}:/tmp/",pty=True)
        c.run(f"scp ./ceph.client.admin.keyring {node}:/etc/ceph/",pty=True)
        c.run(f"scp ./ceph.mon.keyring ceph@{node}:/tmp/",pty=True, watchers=[sudopass])
        c.run(f"scp ./ceph.keyring {node}:/var/lib/ceph/bootstrap-osd/",pty=True)



    
@task
def setup_user(c):
    """
    create the user ceph:ceph 
    """
    pass1=Responder(pattern=r'Enter file in which to save the key',response='\n')
    pass2=Responder(pattern=r'Overwrite',response='y\n')
    pass3=Responder(pattern=r'Enter passphrase',response='\n')
    pass4=Responder(pattern=r'Enter same passphrase again',response='\n')

    sudopass = Responder(pattern=r'password:',response='ceph\n')
    ceph_list = c.run("virsh list | awk '/ceph/{print $2}' | tr '\n' ' '",hide=True).stdout.strip('\n').split()
    for node in ceph_list:
        c.run(f'ssh {node} "userdel ceph"',warn=True,hide=True)
        c.run(f'ssh {node} "useradd -d /home/ceph -m ceph"')
        c.run(f'ssh {node} "passwd ceph"',pty=True, watchers=[sudopass])
        c.run(f'ssh {node} \'echo "ceph ALL = (root) NOPASSWD:ALL" |  tee /etc/sudoers.d/ceph\'')
        c.run(f'ssh {node} "chmod 0440 /etc/sudoers.d/ceph"')
        c.run(f'scp ./ssh-copy-id root@{node}:/usr/bin/')
        c.run(f'ssh ceph@{node} "ssh-keygen -t rsa"',pty=True, watchers=[pass1,pass2,pass3,pass4,sudopass])

    c.run(f'scp ceph@ceph1:~/.ssh/id_rsa.pub ./',pty=True, watchers=[sudopass])
    for node in ceph_list:
        c.run(f'scp ./id_rsa.pub ceph@{node}:~/.ssh/authorized_keys',pty=True, watchers=[sudopass])


    

@task
def setup_hostname(c):
    """
    configure the hostname for VM client
    Now, after excute the setup_hosts, we could use ssh ceph1 directly
    """
    ceph_list = c.run("virsh list | awk '/ceph/{print $2}' | tr '\n' ' '",hide=True).stdout.strip('\n').split()
    for i in ceph_list:
        c.run(f'ssh {i} "hostname {i}"')
        c.run(f'ssh {i} "echo {i} > /etc/hostname"')

    
@task 
def setup_hosts(c):
    """
    set up the configuration for vm client and host
    """
    with open('/etc/hosts','w') as f:
        f.write(f'''127.0.0.1     localhost.localdomain             localhost

# The following lines are desirable for IPv6 capable hosts
::1     localhost ip6-localhost ip6-loopback
fe00::0 ip6-localnet
ff00::0 ip6-mcastprefix
ff02::1 ip6-allnodes
ff02::2 ip6-allrouters

''')

    ceph_list = c.run("virsh list | awk '/ceph/{print $2}' | tr '\n' ' '",hide=True).stdout.strip('\n').split()
    print(ceph_list)

    with open('/etc/hosts','a') as f:
        for node in ceph_list:
            ip =c.run("virsh domifaddr %s  | awk '/192.168/{print $4}' | sed 's#/24##'" % node,hide=True).stdout.strip('\n')
            f.write(f'''{ip} {node}
''')
    
    for node in ceph_list:
        c.run(f'scp /etc/hosts root@{node}:/etc/hosts')


   


@task
def conf(c,uuid):
    """
     deploy the ceph(e.g fab conf --uuid uuid)

     Usage:
        fab conf --uuid uuid

    """
    ceph_list = c.run("virsh list | awk '/ceph/{print $2}' | tr '\n' ' '",hide=True).stdout.strip('\n').split()
    mon_members= ','.join(ceph_list)

    ip_list = []
    for node in ceph_list:
        ip = c.run("virsh domifaddr %s  | awk '/192.168/{print $4}' | sed 's#/24##'" % node,hide=True).stdout.strip('\n')
        ip_list.append(ip)

    mon_hosts = ','.join(ip_list)
    #uuid = c.run('uuidgen',hide=True).stdout.strip('\n')
    #c.run('export cephuid={}'.format(uuid)) 
    with open('ceph.conf','w') as f:
        f.write(f'''[global]
    fsid = {uuid}
    mon initial members = {mon_members}
    mon host = {mon_hosts}
    public network =192.168.122.0/24
    auth cluster required = cephx
    auth service required = cephx
    auth client required = cephx
    osd journal size = 1024
    osd pool default size = {len(ceph_list)}
    osd pool default min size = 1
    osd pool default pg num = 333
    osd pool default pgp num = 333
    osd crush chooseleaf type = 1
''')

    for node in ceph_list:
        c.run(f'scp ceph.conf root@{node}:/etc/ceph/ceph.conf')
        #c.run(f'scp ./ssh-copy-id root@{node}:/usr/bin/')

@task
def mon_destroy(c, node):
    """
    destroy the monitor for node(e.g. fab -H root@ceph1 mon_destroy --node ceph1)
    """
    nodeName=node

    #1. destory the monitor services
    c.run("systemctl daemon-reload")
    c.run(f"systemctl stop ceph-mon@{nodeName}")

    c.run("systemctl daemon-reload")

    result = c.run('echo $SHELL', hide=True)
    user_shell = result.stdout.strip('\n')
    c.run(f"systemctl status ceph-mon@{nodeName}",warn=True,shell=user_shell)
    c.run("rm -rf  /etc/ceph/ceph*")
    c.run("rm -rf  /var/lib/ceph/mon/")
    c.run("rm -rf  /tmp/monmap /tmp/ceph*")
    c.run("rm -rf /var/lib/ceph/bootstrap-osd/*")

@task
def mon_admin(c,node):
    """
    create monitor for node(e.g fab -H root@ceph1 mon_admin --node ceph1)
    """
    nodeName=node
    
    c.run(f"mkdir -p /var/lib/ceph/bootstrap-osd/")
    #2 create the keyring 
    c.run("ceph-authtool --create-keyring /tmp/ceph.mon.keyring --gen-key -n mon. --cap mon 'allow *'")
    c.run("ceph-authtool --create-keyring /etc/ceph/ceph.client.admin.keyring --gen-key -n client.admin --cap mon 'allow *' --cap osd 'allow *' --cap mds 'allow'")
    c.run("ceph-authtool --create-keyring /var/lib/ceph/bootstrap-osd/ceph.keyring --gen-key -n client.bootstrap-osd --cap mon 'profile bootstrap-osd' --cap mgr 'allow r'")
    c.run("ceph-authtool /tmp/ceph.mon.keyring --import-keyring /etc/ceph/ceph.client.admin.keyring")
    c.run("ceph-authtool /tmp/ceph.mon.keyring --import-keyring /var/lib/ceph/bootstrap-osd/ceph.keyring")
    #3 create monitor map

    # get the fsid from the /etc/ceph/ceph.conf 
    mons = c.run("awk '/mon initial members/{print $5}' /etc/ceph/ceph.conf",hide=True).stdout.strip('\n').split(',')
    
    add_node=[]
    for i in mons:
        ip =socket.gethostbyname(i)
        add_node.append(f"--add {i} {ip}")
    #print(add_node)

    # get fsid 

    fsid = c.run("awk '/fsid =/{print $3}' /etc/ceph/ceph.conf",hide=True).stdout.strip('\n')
    #print(f"fsid is {fsid}")

    #print(f"monmaptool --create {' '.join(add_node)} --fsid {fsid} /tmp/monmap")
    c.run(f"monmaptool --create {' '.join(add_node)} --fsid {fsid} /tmp/monmap")
    c.run('chown ceph:ceph /tmp/ceph.mon.keyring')


@task
def mon_start(c,node):
    """
    start the monitor
    """
    nodeName=node
    c.run(f"mkdir -p /var/lib/ceph/mon/ceph-{nodeName}")
    c.run(f"mkdir -p /var/lib/ceph/bootstrap-osd/")
    c.run(f"chown ceph:ceph /tmp/ceph.mon.keyring")
    c.run(f"chown -R ceph:ceph /var/lib/ceph/mon/ceph-{nodeName}")

    c.run(f"sudo -u ceph ceph-mon --mkfs -i {nodeName} --monmap /tmp/monmap --keyring /tmp/ceph.mon.keyring")

    #c.run(f"sed -i 's/--setuser ceph --setgroup ceph/--setuser root --setgroup root/g' /lib/systemd/system/ceph-mon@.service")

    c.run("chmod a+r /var/run/ceph/")
    c.run("chmod a+w /var/run/ceph/")
    c.run("systemctl daemon-reload")

    c.run(f"systemctl enable ceph-mon@{nodeName}")
    c.run(f"systemctl start ceph-mon@{nodeName}")
    
    result = c.run('echo $SHELL', hide=True)
    user_shell = result.stdout.strip('\n')
    c.run(f"systemctl status ceph-mon@{nodeName}",warn=True,shell=user_shell)


@task
def manager(c,node):
    """
    initiate the mamager(ceph-mgr)(e.g. fab -H ceph1 manager --node node
    """

    c.run("ceph mon enable-msgr2")
    c.run(f"mkdir -p /var/lib/ceph/mgr/ceph-{node}/")
    c.run(f"ceph auth get-or-create mgr.{node} mon 'allow profile mgr' osd 'allow *' mds 'allow *' > /var/lib/ceph/mgr/ceph-{node}/keyring")
    c.run(f'chown -R ceph:ceph /var/lib/ceph/mgr/ceph-{node}/')

    c.run(f"sed -i 's/--setuser root --setgroup root/--setuser ceph --setgroup ceph/g' /lib/systemd/system/ceph-mgr@.service")
    c.run("systemctl daemon-reload")
    c.run(f"systemctl restart ceph-mgr@{node}")
    c.run(f"systemctl enable ceph-mgr@{node}")
    c.run(f"systemctl status ceph-mgr@{node}")

@task
def osd_create(c,id):
    """
    create the osd 
    """

    print(f"[OSD] create id({id})")
    result = c.run('echo $SHELL', hide=True)
    user_shell = result.stdout.strip('\n')

    c.run(f'echo "[osd.{id}]" >> /etc/ceph/ceph.conf',warn=True,shell=user_shell)
    c.run(f'echo "    host = ceph{id}"')
    c.run('echo "osd_objectstore = filestore" >> /etc/ceph/ceph.conf')

    c.run(f'mkdir -p /var/lib/ceph/osd/ceph-{id}/')
    c.run('umount -f /dev/vdb',warn=True,shell=user_shell)
    c.run('mkfs -t xfs -f /dev/vdb')
    c.run(f'mount /dev/vdb /var/lib/ceph/osd/ceph-{id}/')

    uuid=c.run('uuidgen',hide=True).stdout.strip('\n')
    c.run(f'ceph osd create {uuid} {id}')
    OSD_SECRET = c.run('ceph-authtool --gen-print-key', hide=True).stdout.strip('\n')
    c.run(f'ceph-authtool --create-keyring /var/lib/ceph/osd/ceph-{id}/keyring --name osd.{id} --add-key {OSD_SECRET}')
    c.run(f'ceph-osd -i {id} --mkfs --mkkey --osd-uuid {uuid} --no-mon-config')
    c.run(f"ceph auth add osd.{id} osd 'allow *' mon 'allow rwx' -i /var/lib/ceph/osd/ceph-{id}/keyring")
    c.run(f"chown -R ceph:ceph /var/lib/ceph/osd/ceph-{id}")
    

@task
def osd_start(c,id):
    """
    start the osd deamon
    """
    
    print(f"[OSD] start id({id})")
    c.run("sed -i 's/--setuser root --setgroup root/--setuser ceph --setgroup ceph/g' /lib/systemd/system/ceph-osd@.service")
    c.run("systemctl daemon-reload")
    c.run(f"systemctl start ceph-osd@{id}")
    c.run(f"systemctl enable ceph-osd@{id}")
    c.run(f"systemctl status ceph-osd@{id}")


@task
def osd_destroy(c,id):
    """
    destroy the osd
    """
    result = c.run('echo $SHELL', hide=True)
    user_shell = result.stdout.strip('\n')

    print(f"[OSD] destroy id({id})")
    c.run("systemctl daemon-reload")
    c.run(f'systemctl stop ceph-osd@{id}')
    c.run(f'ceph osd down {id}')
    c.run(f'ceph osd crush remove osd.{id}')
    c.run(f'ceph auth del osd.{id}')
    c.run(f'ceph osd rm {id}')
    c.run('ceph -s')
    c.run('killall -9 ceph-osd')
    c.run('umount -f /dev/vdb',warn=True,shell=user_shell)
    c.run(f'rm -rf /var/lib/ceph/osd/ceph-{id}')
    c.run(f"sed  -i -e '/\[osd\.*/d' -e '/host = ceph/d' -e '/osd_objectstore = filestore/d' /etc/ceph/ceph.conf")
