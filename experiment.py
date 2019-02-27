import sys
import os
import subprocess
import time
import json
import atexit
import random
from datetime import datetime

# Requires password-less sudo and ssh

# ts requires moreutils to be installed
# 

BASE_DIR = os.getcwd()
SDIR = "{}/shenango/".format(BASE_DIR)

CLIENT_BIN = "{}/apps/synthetic/target/release/synthetic".format(SDIR)
RSTAT = "{}/scripts/rstat.go".format(SDIR)

THISHOST = subprocess.check_output("hostname -s", shell=True).strip()

CORES_RESTRICT = True # Restrict cores on zig/zag

binaries = {
    'iokerneld': {
        'ht': "{}/iokerneld".format(SDIR),
        'noht': "{}/iokerneld-noht".format(SDIR),
    },
    'corearbiter': {
        'ht': "{}/memcached-arachne/arachne-all/CoreArbiter/bin/coreArbiterServer".format(BASE_DIR),
    },
    'memcached': {
        'linux': "{}/memcached-linux/memcached".format(BASE_DIR),
        'shenango': "{}/memcached/memcached".format(BASE_DIR),
        'arachne': "{}/memcached-arachne/memcached".format(BASE_DIR),
        'zygos': "{}/memcached-ix/memcached".format(BASE_DIR)
    },
    'gdnsd': {
        'linux': "{}/gdnsd-stripped/build/sbin/gdnsd".format(BASE_DIR),
        'shenango': "{}/shenango-gdnsd/build/sbin/gdnsd".format(BASE_DIR)
    },
    'swaptions': {
        'linux': "{}/parsec/pkgs/apps/swaptions/inst/amd64-linux.gcc-pthreads/bin/swaptions".format(BASE_DIR),
        'shenango': "{}/parsec/pkgs/apps/swaptions/inst/amd64-linux.gcc-shenango/bin/swaptions".format(BASE_DIR),
        'arachne': "{}/parsec/pkgs/apps/swaptions/inst/amd64-linux.gcc-pthreads/bin/swaptions".format(BASE_DIR),
        'linux-floating': "{}/parsec/pkgs/apps/swaptions/inst/amd64-linux.gcc-pthreads/bin/swaptions".format(BASE_DIR),
    },
    # for synthetic server launches
    'synthetic': {
        'linux': "{}/apps/synthetic/target/release/synthetic".format(SDIR),
        'shenango': "{}/apps/synthetic/target/release/synthetic --config".format(SDIR),
        'arachne': "{}/bench/servers/spin-arachne".format(BASE_DIR),
        'zygos': "{}/bench/servers/spin-ix".format(BASE_DIR),
        'linux-floating': "{}/bench/servers/spin-linux".format(BASE_DIR),
    },
}

if CORES_RESTRICT:
    USABLE_CPUS = range(0, 16, 2) + range(24, 40, 2)
else:
    USABLE_CPUS = range(0, 48, 2)

USABLE_CPUS_STR = ",".join([str(x) for x in USABLE_CPUS])

def IP(node):
    assert node > 0 and node < 255
    return "{}.{}".format(NETPFX, node)

NETPFX = "192.168.18"
NETMASK = "255.255.255.0"
GATEWAY = IP(1)

LNX_IPS = {
    'zig': IP(9),
    'zag': IP(8),
}

OOB_IPS = {
    'pd%d' % d: '18.26.5.%d' % d for d in range(1, 12)
}
OOB_IPS.update({
    'zig':  '18.26.4.39',
    'zag': '18.26.4.41',
})

SERVER_MACS = {
    'zig': '00:1b:21:bc:66:44',
    'zag': '00:1b:21:bc:66:3a',
}

OBSERVER = "zig"
OBSERVER_IP = IP(9)
OBSERVER_MAC = SERVER_MACS['zig']
CLIENT_SET = ["pd3", "pd4"]
CLIENT_MACHINE_NCORES = 6
NEXT_CLIENT_ASSIGN = 0
NIC_PCI = "0000:04:00.0"
NIC_IFNAME = "enp4s0f0"

def is_server():
    return THISHOST in SERVER_MACS.keys()

################# Experiment Building Blocks #########################


def new_experiment(system, **kwargs):
    return {
        'name': "run.{}-{}".format(datetime.now().strftime('%Y%m%d%H%M%S'), system),
        'system': system,
        'clients': {},
        'server_hostname': THISHOST,
        'client_files': [__file__],
        'apps': [],
        'nextip': 100,
        'nextport': 5000 + random.randint(0,255),
    }


def gen_random_mac():
    return ":".join(["02"] + ["%02x" % random.randint(0, 255) for i in range(5)])


def alloc_ip(experiment, is_shenango_client=False):
    if experiment["system"] == "shenango" or is_shenango_client:
        ip = IP(experiment['nextip'])
        experiment['nextip'] += 1
        return ip

    return LNX_IPS[THISHOST]


def alloc_port(experiment):
    port = experiment['nextport']
    experiment['nextport'] += 1
    return port


def new_memcached_server(threads, experiment, name="memcached", transport="tcp"):
    x = {
        'name': name,
        'ip': alloc_ip(experiment),
        'port': alloc_port(experiment),
        'threads': threads,
        'guaranteed': threads,
        'spin': 0,
        'app': 'memcached',
        'nice': -20,
        'meml': 32000,
        'hashpower': 28,
        'mac': gen_random_mac(),
        'protocol': 'memcached',
        'transport': transport,
    }

    args = "-U {port} -p {port} -c 32768 -m {meml} -b 32768"
    args += " -o hashpower={hashpower}"

    args += {
        'arachne': ",no_hashexpand,no_lru_crawler,no_lru_maintainer,no_slab_reassign",
        'linux': ",no_hashexpand,lru_crawler,lru_maintainer,idle_timeout=0",
        'shenango': ",no_hashexpand,lru_crawler,lru_maintainer,idle_timeout=0",
        'zygos': ",lru_crawler", # TODO: change this?
    }.get(experiment['system'])

    if experiment['system'] == "arachne":
        x['args'] = "--minNumCores 2 --maxNumCores {threads} -t 1 " + args
    else:
        x['args'] = "-t {threads} " + args

    # Requires SO_REUSEPORT hack for memcached
    if experiment['system'] in ["arachne", "linux"] and transport == "udp":
        x['args'] += " -l " + ",".join(["{ip}:{port}" for i in range(4 * threads)])

    experiment['apps'].append(x)
    return x


def new_gdnsd_server(threads, experiment, name="dns"):
    x = {
        'name': name,
        'ip': alloc_ip(experiment),
        'before': ["configure_dns_environment"],
        'threads': threads,
        'guaranteed': threads,
        'spin': 0,
        'app': 'gdnsd',
        'nice': -20,
        'protocol': 'dns',
        'args': "-f start -c ./",
        'transport': 'udp',
        'mac': gen_random_mac(),
    }
    if experiment["system"] == "shenango":
        x['port'] = 53
    else:
        x['port'] = alloc_port(experiment)
    experiment['apps'].append(x)
    return x

def new_synthetic_server(threads, experiment, **kwargs):
    x = {
        'name': kwargs.get('name', 'synth'),
        'ip': alloc_ip(experiment),
        'port': alloc_port(experiment),
        'threads': threads,
        'guaranteed': threads,
        'spin': 0,
        'app': 'synthetic',
        'nice': -20,
        'mac': gen_random_mac(),
        'protocol': 'synthetic',
        'transport': kwargs.get('transport', 'tcp'),
        'fakework': kwargs.get('fakework', 'stridedmem:1024:7'),
        'args': "--mode={stype}-server {ip}:{port} --threads {threads} --transport {transport}"
    }

    x['args'] += " --fakework {fakework}"
    if experiment["system"] == "shenango":
        x['stype'] = 'spawner'
    elif experiment["system"] == "linux":
        x['stype'] = 'linux'
    elif experiment['system'] == "arachne":
        assert x['transport'] == "tcp"
        x['args'] = "--minNumCores 2 --maxNumCores {threads}"
        if x['transport'] == "udp": x['args'] += " --udp"
        x['args'] += " {fakework} {port}"
    elif experiment['system'] == "zygos":
        assert x['transport'] == "tcp"
        x['args'] = "{fakework}"
    elif experiment['system'] == "linux-floating":
        x['args'] = "{fakework} {threads} {port}"
    experiment['apps'].append(x)
    return x


def new_swaptions_inst(threads, experiment, name="swaptions"):
    x = {
        'name': name,
        'ip': alloc_ip(experiment),
        'port': None,
        'mac': gen_random_mac(),
        'threads': threads,
        'guaranteed': 0,
        'spin': 0,
        'app': 'swaptions',
        'nice': 20,
        'args': "-ns {threads} -sm 40000 -nt {threads} 2>&1 | ts %s",
    }
    experiment['apps'].append(x)
    return x


def new_measurement_instances(count, server_handle, mpps, experiment, mean=842, nconns=300, **kwargs):
    global NEXT_CLIENT_ASSIGN

    all_instances = []
    for i in range(count):
        client = CLIENT_SET[(NEXT_CLIENT_ASSIGN + i) % len(CLIENT_SET)]
        if not client in experiment['clients']:
            experiment['clients'][client] = []
        x = {
            'ip': alloc_ip(experiment, is_shenango_client=True),
            'port': None,
            'mac': gen_random_mac(),
            'host': client,
            'name': "{}-{}.{}".format(i, client, server_handle['name']),
            'binary': "./synthetic --config",
            'app': 'synthetic',
            'serverip': server_handle['ip'],
            'serverport': server_handle['port'],
            'output': kwargs.get('output', "buckets"),
            'mpps': float(mpps) / count,
            'protocol': server_handle['protocol'],
            'transport': server_handle['transport'],
            'distribution': kwargs.get('distribution', "zero"),
            'mean': mean,
            'client_threads': nconns // count,
            'start_mpps': float(kwargs.get('start_mpps', 0)) / count,
            'args': "{serverip}:{serverport} {warmup} --output={output} --protocol {protocol} --mode runtime-client --threads {client_threads} --runtime {runtime} --barrier-peers {npeers} --barrier-leader {leader}  --mean={mean} --distribution={distribution} --mpps={mpps} --samples={samples} --transport {transport} --start_mpps {start_mpps}"
        }
        warmup = kwargs.get('warmup')
        if warmup is None:
            if experiment['system'] not in ["arachne", "zygos"]:
                warmup = True

        x["warmup"] = "--warmup" if warmup else ""
        if kwargs.get('rampup', False):
            x['args'] += " --rampup={rampup}"
            x['rampup'] = kwargs.get('rampup') / count
        experiment['clients'][client].append(x)
        all_instances.append(x)
    NEXT_CLIENT_ASSIGN += count
    return all_instances

def sleep_5(cfg, experiment):
    time.sleep(5)

def finalize_measurement_cohort(experiment, samples, runtime):
    all_clients = [c for j in experiment['clients']
                   for c in experiment['clients'][j]]
    all_clients.sort(key=lambda c: c['host'])
    max_client_permachine = max(
        len(experiment['clients'][c]) for c in experiment['clients'])
    assert max_client_permachine <= CLIENT_MACHINE_NCORES
    threads_per_client = CLIENT_MACHINE_NCORES // max_client_permachine
    assert threads_per_client % 2 == 0
    # Apps must have unique names
    assert len(set(app['name'] for app in experiment['apps'])) == len(experiment['apps'])
    for i, cfg in enumerate(all_clients):
        cfg['threads'] = threads_per_client
        cfg['guaranteed'] = threads_per_client
        cfg['spin'] = threads_per_client
        cfg['runtime'] = runtime
        cfg['npeers'] = len(all_clients)
        cfg['samples'] = samples
        cfg['leader'] = OOB_IPS[all_clients[0]
                                ['host']] if i > 0 else cfg['host']
        if i > 0:
            cfg['before'] = ['sleep_5']
    experiment['client_files'].append(CLIENT_BIN)

########################## EXPERIMENTS ###############################


def loadshift(system, **kwargs):
    assert system in ["shenango", "arachne", "linux-floating"]

    x = new_experiment(system)
    x['name'] += "-loadshift"

    loadshift_points = []
    loadshift_points.append((100000, 1000000)) #warmup
    for krps in range(400, 1200, 200):
        loadshift_points.append((100000, 1000000))
        loadshift_points.append((krps * 1000, 1000000))

    if system == "shenango":
        for mrps in range(2, 6):
            loadshift_points.append((100000, 1000000))
            loadshift_points.append((mrps * 1e6, 1000000))

    NCLIENTS = len(CLIENT_SET)
    loadshift_points = map(lambda p: (int(p[0] / NCLIENTS), p[1]), loadshift_points)

    thr = {
        'arachne': 15,
        'shenango': 14,
        'linux-floating': 16,
    }.get(system)

    mean = get_mean(1.0, system, False)

    synth_handle = new_synthetic_server(thr, x, **kwargs)

    new_swaptions_inst(len(USABLE_CPUS), x)

    clients = new_measurement_instances(
        NCLIENTS, synth_handle, 0, x, mean=mean, distribution="exponential", nconns=1200)

    spec = ",".join("{}:{}".format(*p) for p in loadshift_points)
    for c in clients:
        c['args'] += " --loadshift=" + spec
    finalize_measurement_cohort(x, 0, 0)
    return x

# for 'stridedmem:1024:7'
def get_mean(target_us, system, noht):
    assert system in ["shenango", "linux", "arachne", "zygos", "linux-floating"]

    impl = {
        'shenango': 'rust',
        'linux': 'rust',
        'arachne': 'cpp',
        'zygos': 'cpp',
        'linux-floating': 'cpp'
    }.get(system)

    return int(float(target_us) * {
        ('rust', True): 83.89,
        ('rust', False): 59.37,
        ('cpp', True): 78.0,
        ('cpp', False): 65.0,
    }.get((impl, noht)))


def assemble_local_synth(mrps, producers, consumers, time=10, samples=20, **kwargs):
    y = new_experiment("shenango")
    y['noht'] = True
    x = {
        'ip': alloc_ip(y),
        'port': alloc_port(y),
        'mac': gen_random_mac(),
        'threads': producers + consumers,
        'guaranteed': 1,
        'spin': 0,
        'samples': samples,
        'runtime': time,
        'name': "localsynth",
        'app': 'synthetic',
        'output': "normal",
        'mpps': mrps,
        'protocol': 'synthetic',
        'distribution': kwargs.get('distribution', 'exponential'),
        'mean': kwargs.get('mean', get_mean(10, "shenango", True)),
        'client_threads': producers,
        'start_mpps': kwargs.get('start_mpps', 0),
        'args': "{ip}:{port} --rampup=0 --output={output} --protocol {protocol} --mode local-client --threads {client_threads} --runtime {runtime}  --mean={mean} --distribution={distribution} --mpps={mpps} --samples={samples} --start_mpps {start_mpps}"
    }
    y['name'] += "-localsynth-" + x['distribution']
    y['apps'].append(x)
    return y

def multiapp_io(system, samples=None, bg='swaptions', spin=False):
    assert system in ["shenango", "linux"]
    x = new_experiment(system)
    x['name'] += "-multiapp_io"

    if system == "shenango":
        max_memcached_mpps = 1.125
        samples = samples or 45
        dns_threads = 4
        memcached_threads = 3
        bg_threads = 22
    else:
        max_memcached_mpps = 0.3
        samples = samples or 12
        dns_threads = 24
        memcached_threads = 5
        bg_threads = 24

    memcached_handle = new_memcached_server(memcached_threads, x)
    dns_handle = new_gdnsd_server(dns_threads, x)

    if spin:
        assert system == "shenango"
        dns_handle['spin'] = dns_threads
        memcached_handle['spin'] = memcached_threads

    if bg == "swaptions":
        new_swaptions_inst(bg_threads, x)

    new_measurement_instances(
        len(CLIENT_SET) / 2, memcached_handle, max_memcached_mpps, x)
    new_measurement_instances(
        len(CLIENT_SET) / 2, dns_handle, 3 * max_memcached_mpps, x)
    finalize_measurement_cohort(x, samples, 30)

    return x


def bench_memcached(system, thr, spin=False, bg=None, samples=55, time=10, mpps=6.0, noht=False, transport="tcp", nconns=1200, start_mpps=0.0):
    assert system in ["shenango", "linux", "arachne", "zygos"]

    x = new_experiment(system)
    x['name'] += "-memcached" + "-" + transport
    x['name'] += "-spin" if spin else ""
    if bg: x['name'] += '-' + bg

    if noht:
        assert system == "shenango"
        x['noht'] = True

    memcached_handle = new_memcached_server(thr, x, transport=transport)
    if spin:
        memcached_handle['spin'] = thr

    if bg == "swaptions":
        new_swaptions_inst(len(USABLE_CPUS), x)

    new_measurement_instances(len(CLIENT_SET), memcached_handle, mpps, x, nconns=nconns, start_mpps=start_mpps)
    finalize_measurement_cohort(x, samples, time)


    return x


def bench_dns(system, spin=False, bg=None, samples=54, time=10, mpps=5.4, noht=False, thr=None, **kwargs):
    assert system in ["shenango", "linux"]

    x = new_experiment(system)
    x['name'] += "-dns"
    x['name'] += ("-" + bg) if bg else ""
    x['name'] += "-spin" if spin else ""

    if not thr and system == "shenango":
        thr = 5 if noht else 6
    elif not thr:
        thr = 24

    if noht:
        assert system == "shenango"
        x['noht'] = True

    dns_handle = new_gdnsd_server(thr, x)
    if spin:
        dns_handle['spin'] = thr

    if bg == "swaptions":
        new_swaptions_inst(len(USABLE_CPUS), x)

    new_measurement_instances(len(CLIENT_SET), dns_handle, mpps, x, nconns=1200, warmup=False, **kwargs)
    finalize_measurement_cohort(x, samples, time)

    return x

# try different thread configurations with memcached
def try_thr_memcached(system, thread_range, mpps_start, mpps_end, samples, transport, bg=False, time=20):
    assert system in ["shenango", "linux", "arachne"]
    for i in thread_range:
        x = new_experiment(system)
        x['name'] += "-memcached-{}-{}threads".format(transport, i)
        memcached_handle = new_memcached_server(i, x, transport=transport)
        if bg: new_swaptions_inst(24, x)
        new_measurement_instances(len(CLIENT_SET), memcached_handle, mpps_end, x, start_mpps=mpps_start,  nconns=200*len(CLIENT_SET))
        finalize_measurement_cohort(x, samples, time)
        execute_experiment(x)

def exitfn():
    procs = ["iokerneld", "cstate", "memcached",
             "swaptions", "mpstat", "synthetic", "gdnsd",
             "coreArbit", "ix", "spin-arachne", "spin-linux"]
    for j in procs:
        os.system("sudo pkill " + j)
    for j in procs:
        os.system("sudo pkill -9 " + j)

    if is_server():
        runcmd("sudo rmmod dune 2>/dev/null || true")
        runcmd("sudo rmmod pcidma 2>/dev/null || true")


def switch_to_linux():
    assert is_server()
    print "switch to linux"
    runcmd("sudo ifdown {} || true".format(NIC_IFNAME))
    runcmd("sudo {}/scripts/setup_machine.sh || true".format(SDIR))
    runcmd("sudo {}/dpdk/usertools/dpdk-devbind.py -b none {}".format(SDIR, NIC_PCI))
    runcmd("sudo modprobe ixgbe")
    runcmd("sudo {}/dpdk/usertools/dpdk-devbind.py -b ixgbe {}".format(SDIR, NIC_PCI))
    runcmd("sudo ethtool -N {} rx-flow-hash udp4 sdfn".format(NIC_IFNAME))
    runcmd("sudo {}/scripts/set_irq_affinity {} {}".format(SDIR, USABLE_CPUS_STR, NIC_IFNAME))
    runcmd("sudo ip addr flush {}".format(NIC_IFNAME))
    runcmd("sudo ip addr add {}/24 dev {}".format(LNX_IPS[THISHOST], NIC_IFNAME))
    runcmd("sudo sysctl net.ipv4.tcp_syncookies=1")
    return


def switch_to_shenango():
    runcmd("sudo {}/scripts/setup_machine.sh || true".format(SDIR))
    if not is_server():
        return
    runcmd("sudo ifdown {}".format(NIC_IFNAME))
    runcmd("sudo modprobe uio")
    runcmd("(lsmod | grep -q igb_uio) || sudo insmod {}/dpdk/build/kmod/igb_uio.ko".format(SDIR))
    runcmd("sudo {}/dpdk/usertools/dpdk-devbind.py -b igb_uio {}".format(SDIR, NIC_PCI))
    return

def switch_to_zygos():
    assert is_server()
    runcmd("sudo find /dev/hugepages -type f -delete")
    runcmd("sudo {}/scripts/setup_machine.sh || true".format(SDIR))
    runcmd("sudo modprobe -r ixgbe")
    runcmd("sudo rmmod dune 2>&1 || true")
    runcmd("sudo rmmod pcidma 2>&1 || true")
    runcmd("sudo insmod {}/zygos/deps/dune/kern/dune.ko".format(BASE_DIR))
    runcmd("sudo insmod {}/zygos/deps/pcidma/pcidma.ko".format(BASE_DIR))
    runcmd("sudo modprobe uio")
    runcmd("sudo rmmod igb_uio 2>&1 || true")
    runcmd("sudo insmod {}/zygos/deps/dpdk/build/kmod/igb_uio.ko".format(BASE_DIR))
    runcmd("sudo {}/zygos/deps/dpdk/tools/dpdk_nic_bind.py -b igb_uio {}".format(BASE_DIR, NIC_PCI))
    runcmd("sudo rm -fr /var/run/.rte_config")


def runcmd(cmdstr, **kwargs):
    return subprocess.check_output(cmdstr, shell=True, **kwargs)


def runpara(cmd, inputs, die_on_failure=False, **kwargs):
    fail = "--halt now,fail=1" if die_on_failure else ""
    return runcmd("parallel {} \"{}\" ::: {}".format(fail, cmd, " ".join(inputs)))


def runremote(cmd, hosts, **kwargs):
    return runpara("ssh -t -t {{}} '{cmd}'".format(cmd=cmd), hosts, kwargs)

############################# APPLICATIONS ###########################

# Launching configuration spec


def start_iokerneld(experiment):
    switch_to_shenango()
    binary = binaries['iokerneld']['ht']
    if 'noht' in experiment and THISHOST == experiment['server_hostname']:
        binary = binaries['iokerneld']['noht']
    runcmd("sudo {}/scripts/setup_machine.sh || true".format(SDIR))
    proc = subprocess.Popen("sudo {} 2>&1 | ts %s > iokernel.{}.log".format(
        binary, THISHOST), shell=True, cwd=experiment['name'])
    time.sleep(10)
    proc.poll()

    assert proc.returncode is None
    return proc

def start_corearbiter(experiment):
    binary = binaries['corearbiter']['ht']
    assert is_server()
    assert not 'noht' in experiment
    runcmd("sudo {}/scripts/setup_machine.sh || true".format(SDIR))
    proc = subprocess.Popen("sudo numactl -N 0 -m 0 {} > corearbiter.{}.log 2>&1".format(
      binary, THISHOST), shell=True, cwd=experiment['name'])
    time.sleep(5)
    proc.poll()
    assert proc.returncode is None
    return proc

def start_cstate():
    proc = subprocess.Popen(
        "sudo {}/scripts/cstate 0".format(SDIR), shell=True)
    return proc


def gen_conf(filename, experiment, mac=None, **kwargs):
    conf = [
        "host_addr {ip}",
        "host_netmask {netmask}",
        "host_gateway {gw}",
        "runtime_kthreads {threads}",
        "runtime_guaranteed_kthreads {guaranteed}",
        "runtime_spinning_kthreads {spin}"
    ]
    if mac:
        conf.append("host_mac {mac}")

    #HACK
    if kwargs['guaranteed'] > 0:
        conf.append("disable_watchdog true")

    if experiment['system'] == "shenango":
        for cfg in experiment['apps']:
            if cfg['ip'] == kwargs['ip']:
                continue
            conf.append("static_arp {ip} {mac}".format(**cfg))
    else:
        for host in SERVER_MACS:
            conf.append("static_arp {ip} {mac}".format(ip=LNX_IPS[host], mac=SERVER_MACS[host]))
    for client in experiment['clients']:
        for cfg in experiment['clients'][client]:
            if cfg['ip'] == kwargs['ip']:
                continue
            conf.append("static_arp {ip} {mac}".format(**cfg))

    if OBSERVER:
      conf.append("static_arp {} {}".format(OBSERVER_IP, OBSERVER_MAC))

    with open(filename, "w") as f:
        f.write("\n".join(conf).format(
            netmask=NETMASK, gw=GATEWAY, mac=mac, **kwargs) + "\n")

def gen_ix_conf(filename, experiment, **kwargs):
    conf = [
        "host_addr=\"{ip}/24\"",
        "gateway_addr=\"{gw}\"",
        "port={port}",
        "devices=\"{device}\"",
        "cpu={cpu_str}",
        "batch={batch}",
        "loader_path=\"/lib64/ld-linux-x86-64.so.2\"",
    ]

    # ZIG/ZAG SPECIFIC! #
    assert THISHOST in ["zig", "zag"]

    if 'noht' in experiment:
        cpu_list = list(range(0,24,2))
    else:
        cpu_list = [core for pair in zip(range(0,24,2), range(24,48,2)) for core in pair]

    cpus = sorted(cpu_list[:kwargs['threads']])

    with open(filename, "w") as f:
        f.write("\n".join(conf).format(
            gw=GATEWAY, device=NIC_PCI, cpu_str=str(cpus), batch=64, **kwargs) + "\n")

def configure_dns_environment(cfg, experiment):
    with open(experiment['name'] + "/config", "w") as f:
        if experiment['system'] != "shenango":
            f.write(
                "options => {{listen => {{0.0.0.0:{port} => {{udp_threads = {threads}}}}}}}".format(**cfg))
    zfdir = binaries['gdnsd']['linux'].rsplit(
        "/", 1)[0] + "/../etc/gdnsd/zones/"
    runcmd("ln -s {} {}/".format(zfdir, experiment['name']))


def launch_shenango_program(cfg, experiment):
    assert 'args' in cfg

    if not 'binary' in cfg:
        cfg['binary'] = binaries[cfg['app']]['shenango']

    cwd = os.getcwd()
    os.chdir(experiment['name'])
    assert os.access(cfg['binary'].split()[0], os.F_OK), cfg[
        'binary'].split()[0]
    os.chdir(cwd)

    gen_conf(
        "{}/{}.config".format(experiment['name'], cfg['name']), experiment, **cfg)

    args = cfg['args'].format(**cfg)

    fullcmd = "numactl -N 0 -m 0 {bin} {name}.config {args} > {name}.out 2> {name}.err"
    fullcmd = fullcmd.format(bin=cfg['binary'], name=cfg['name'], args=args)
    print "Running", fullcmd

    ### HACK
    # if THISHOST.startswith("pd") or THISHOST == "zag":
    #     fullcmd = "export RUST_BACKTRACE=1; " + fullcmd

    proc = subprocess.Popen(fullcmd, shell=True, cwd=experiment['name'])
    time.sleep(3)
    proc.poll()
    assert not proc.returncode
    return proc

def launch_zygos_program(cfg, experiment):
    assert 'args' in cfg

    if not 'binary' in cfg:
        cfg['binary'] = binaries[cfg['app']]['zygos']

    cwd = os.getcwd()
    os.chdir(experiment['name'])
    assert os.access(cfg['binary'].split()[0], os.F_OK), cfg[
        'binary'].split()[0]
    os.chdir(cwd)

    prio = ""
    if cfg['nice'] >= 0:
        prio = "nice -n {}".format(cfg['nice'])

    cnf_name = "{}/{}.config".format(experiment['name'], cfg['name'])
    gen_ix_conf(cnf_name, experiment, **cfg)

    print cfg
    args = cfg['args'].format(**cfg)

    ix = "{}/zygos/dp/ix".format(BASE_DIR)
    fullcmd = "sudo numactl -N 0 -m 0 {prio} {ix} -c {cnf} -- {bin} {args} > {name}.out 2>&1"
    fullcmd = fullcmd.format(prio=prio, ix=ix, bin=cfg['binary'], name=cfg['name'], cnf=os.path.abspath(cnf_name), args=args)
    print "Running", fullcmd

    proc = subprocess.Popen(fullcmd, shell=True, cwd=experiment['name'])
    time.sleep(20)
    proc.poll()
    assert proc.returncode is None
    return proc


def launch_linux_program(cfg, experiment):
    assert 'args' in cfg
    assert 'nice' in cfg
    assert cfg['ip'] == LNX_IPS[THISHOST]

    binary = cfg.get('binary', binaries[cfg['app']][experiment['system']])
    assert os.access(binary, os.F_OK), binary
    name = cfg['name']

    prio = ""
    if cfg['nice'] >= 0:
        prio = "chrt --idle 0"
        #prio = "nice -n {}".format(cfg['nice'])

    args = cfg['args'].format(**cfg)

    # cpu_list = [str(i) for a in range(0, 24, 2) for i in [a, a + 24]]
    # assert cfg['threads'] <= len(cpu_list)
    cpu_bind = "-C " + USABLE_CPUS_STR #-C " + ",".join(cpu_list[:cfg['threads']])

    fullcmd = "numactl -N 0 -m 0 {bind} {prio} {bin} {args} > {name}.out 2>&1"
    fullcmd = fullcmd.format(bind=cpu_bind, bin=binary,
                             name=name, args=args, prio=prio)
    print "Running", fullcmd
    proc = subprocess.Popen(fullcmd, shell=True, cwd=experiment['name'])

    if cfg['nice'] < 0:
        time.sleep(2)
        pid = proc.pid
        with open("/proc/{pid}/task/{pid}/children".format(pid=pid)) as f:
            for line in f:
                runcmd(
                    "sudo renice -n {} -p $(ls /proc/{}/task)".format(cfg['nice'], line.strip()))

    proc.poll()
    assert proc.returncode is None
    return proc


def launch_arachne_program(cfg, experiment):
    assert 'args' in cfg
    assert cfg['ip'] == LNX_IPS[THISHOST]

    binary = cfg.get('binary', binaries[cfg['app']]['arachne'])
    assert os.access(binary, os.F_OK), str(binary)
    name = cfg['name']

    prio = ""
    if cfg['nice'] >= 0:
        prio = "chrt --idle 0"
        #prio = "nice -n {}".format(cfg['nice'])

    args = cfg['args'].format(**cfg)
    fullcmd = "numactl -N 0 -m 0 {prio} {bin} {args} > {name}.out 2>&1"
    fullcmd = fullcmd.format(bin=binary, prio=prio,
                             name=name, args=args)
    print "Running", fullcmd
    proc = subprocess.Popen(fullcmd, shell=True, cwd=experiment['name'])

    proc.poll()
    assert proc.returncode is None
    return proc


def launch_apps(experiment):
    launcher = {
        'shenango': launch_shenango_program,
        'linux': launch_linux_program,
        'arachne': launch_arachne_program,
        'zygos': launch_zygos_program,
        'linux-floating': launch_linux_program,
    }.get(experiment['system'])

    procs = []
    for cfg in experiment['apps']:
        if 'before' in cfg:
            for cmd in cfg['before']:
                eval(cmd)(cfg, experiment)
        procs.append(launcher(cfg, experiment))
        if 'after' in cfg:
            for cmd in cfg['after']:
                eval(cmd)(cfg, experiment)
    return procs


def go_client(experiment_directory):
    assert os.access(experiment_directory, os.F_OK)
    with open(experiment_directory + "/config.json") as f:
        experiment = json.loads(f.read())
    iokerneld = start_iokerneld(experiment)
    cs = start_cstate()
    procs = []
    for cfg in experiment['clients'][THISHOST]:
        procs.append(launch_shenango_program(cfg, experiment))
    for p in procs:
        p.wait()
    return

def go_observer(experiment_directory):
    assert os.access(experiment_directory, os.F_OK)
    with open(experiment_directory + "/config.json") as f:
        experiment = json.loads(f.read())

    if experiment['system'] != "shenango":
        return

    procs = []
    for app in experiment['apps'] + [app for client in experiment['clients'] for app in experiment['clients'][client]]:
        fullcmd = "sudo arp -d {ip} || true; "
        fullcmd += "go run rstat.go {ip} 1 "
        fullcmd += "| ts %s > rstat.{name}.log"
        procs.append(subprocess.Popen(fullcmd.format(**app), shell=True,cwd=experiment['name']))

    for p in procs:
        p.wait()


def go_server(experiment):
    procs = []

    # Create directory
    try:
        os.mkdir(experiment['name'])
    except:
        pass
    # Copy ourselves for posterity
    runcmd("cp {} {}/".format(__file__, experiment['name']))

    conf_fn = experiment['name'] + "/config.json"
    with open(conf_fn, "w") as f:
        f.write(json.dumps(experiment))

    # Record status of local git repo
    runcmd("(cd {}; git status; git diff) > {}/gitstatus.$(hostname -s).log".format(SDIR,
                                                                                    experiment['name']))

    # Start mpstat
    procs.append(subprocess.Popen("mpstat 1 -N 0,1 2>&1| ts %s > mpstat.{}.log".format(
                                  THISHOST), shell=True, cwd=experiment['name']))

    # Start cstate
    procs.append(start_cstate())

    # Run iokernel or dune
    if experiment['system'] == "shenango":
        procs.append(start_iokerneld(experiment))
    elif experiment['system'] == "zygos":
        switch_to_zygos()
    else:
        switch_to_linux()

    if experiment['system'] == "arachne":
        procs.append(start_corearbiter(experiment))

    # Start each server app
    procs += launch_apps(experiment)

    return procs


def assemble_synthetic(system, thr, dist="exponential", spin=False, noht=False, bg=None,
                       time=10, samples=40, mpps=1.6, target_us=10, transport="tcp", min_mpps=0.0, nconns=1200):
    assert system in ["shenango", "linux", "arachne", "zygos", "linux-floating"]
    assert transport in ["udp", "tcp"]
    x = new_experiment(system)
    x['name'] += "-synthetic-" + dist
    if bg:
        x['name'] += "-" + bg
    x['name'] + "-" + transport
    x['transport'] = transport

    mean = get_mean(target_us, system, noht)

    if noht:
        x['noht'] = True

    synth_handle = new_synthetic_server(thr, x, transport=transport)

    if spin:
        x['name'] += '-spin'
        synth_handle['spin'] = synth_handle['threads']
    if bg == "swaptions":
        new_swaptions_inst(len(USABLE_CPUS), x)

    new_measurement_instances(
        len(CLIENT_SET), synth_handle, mpps, x, mean=mean, distribution=dist, nconns=nconns, start_mpps=min_mpps)
    finalize_measurement_cohort(x, samples, time)

    return x


def assemble_pps_exper(thr):
    x = new_experiment("shenango")
    x['name'] += '-pps'
    x['noht'] = True

    synth_handle = new_synthetic_server(thr, "synth", x)

    new_measurement_instances(len(CLIENT_SET), synth_handle, 8, x, mean=0)
    finalize_measurement_cohort(x, 16, 10)
    return x


def verify_dates(host_list):
    for i in range(3): # try a few extra times
        while True:
            dates = set(runremote("date +%s", host_list).splitlines())
            if dates:
                break
            else:
                print "retrying verify dates"
        if len(dates) == 1:
            return
        # Not more than one second off
        if len(dates) == 2:
            d1 = int(dates.pop())
            d2 = int(dates.pop())
            if (d1 - d2)**2 == 1:
                return
        time.sleep(1)
    assert False


def setup_clients(experiment):
    servers = experiment['clients'].keys()
    verify_dates(servers + [OBSERVER])
    runremote("mkdir -p {}".format(
        experiment['name']), servers + [OBSERVER])
    conf_fn = experiment['name'] + "/config.json"
    for i in experiment['client_files'] + [conf_fn, RSTAT]:
        runpara("scp {binary} {{}}:{dest}/".format(binary=i,
                                                   dest=experiment['name']), servers + [OBSERVER])

def collect_clients(experiment):
    runpara("scp {{}}:{exp}/*.log {exp}/ || true".format(exp=experiment['name']), experiment['clients'].keys() + [OBSERVER])
    runpara("scp {{}}:{exp}/*.out {exp}/ || true".format(exp=experiment['name']), experiment['clients'].keys())
    runpara("scp {{}}:{exp}/*.err {exp}/ || true".format(exp=experiment['name']), experiment['clients'].keys())
    runremote(
        "rm -rf {}".format(experiment['name']), experiment['clients'].keys() + [OBSERVER])
    return

def execute_experiment_noclients(experiment):
    assert len(experiment['clients']) == 0
    procs = go_server(experiment)
    done = False
    while not done:
        for p in procs:
            if p.poll() != None:
                done = True
                break
        time.sleep(3)
    for p in procs:
        try:
            p.terminate()
        except:
            pass
        p.wait()
        del p
    exitfn()

def execute_experiment(experiment):
    procs = go_server(experiment)
    setup_clients(experiment)
    time.sleep(10)
    observer = None
    try:
        observer_cmd = "exec ssh -t -t {observer} 'python {dir}/{script} observer {dir} > {dir}/py.{observer}.log 2>&1'".format(
            observer=OBSERVER, dir=experiment['name'], script=os.path.basename(__file__))
        if OBSERVER: observer = subprocess.Popen(observer_cmd, shell=True)
        runremote("ulimit -S -c unlimited; python {dir}/{script} client {dir} > {dir}/py.{{}}.log 2>&1".format(dir=experiment[
                  'name'], script=os.path.basename(__file__)), experiment['clients'].keys(), die_on_failure=True)
    finally:
        collect_clients(experiment)
        if observer:
            observer.terminate()
            observer.wait()
    for p in procs:
        p.terminate()
        p.wait()
        del p
    exitfn()
    return experiment


# runs one experiment per sample-point.
# mainly needed for zygos which doesn't seem to support closing TCP connections.
def rep_external(fn, mpps, samples, *args, **kwargs):
    for i in range(1, samples + 1):
        mpps_local = float(mpps * i) / float(samples)
        xp = fn(*args, mpps=mpps_local, samples=1, **kwargs)
        xp['name'] += '-{}mpps'.format(mpps_local)
        execute_experiment(xp)

def go_replay(exp_folder):
    assert is_server()
    try:
        with open(exp_folder) as f:
            exp = json.loads(f.read())
    except:
        with open("{}/config.json".format(exp_folder)) as f:
            exp = json.loads(f.read())
    exp['client_files'] = filter(lambda l: "experiment.py" not in l, exp['client_files'])
    exp['client_files'].append(__file__)
    exp['name'] += "-replay"
    execute_experiment(exp)


def run_balancer_experiment(interval):
    subprocess.check_call("git diff --exit-code iokernel/main.c > /dev/null", shell=True, cwd=SDIR)
    try:
        subprocess.check_call("sed 's/define CORES_ADJUST_INTERVAL_US.*/define CORES_ADJUST_INTERVAL_US {}/g' -i iokernel/main.c".format(interval), shell=True, cwd=SDIR)
        subprocess.check_call("make", shell=True, cwd=SDIR)
        x = assemble_synthetic("shenango", 14, dist="exponential", mpps=1.4, bg="swaptions", samples=20)
        x['name'] += "-{}us_balancer".format(interval)
        execute_experiment(x)
    finally:
        subprocess.check_call("git checkout iokernel/main.c", shell=True, cwd=SDIR)
        subprocess.check_call("make", shell=True, cwd=SDIR)


def run_cycle_counting_experiment():
    subprocess.check_call("git diff --exit-code runtime/defs.h > /dev/null", shell=True, cwd=SDIR)
    try:
        subprocess.check_call("echo \"#define TCP_RX_STATS 1\" >> runtime/defs.h", shell=True, cwd=SDIR)
        subprocess.check_call("make", shell=True, cwd=SDIR)
        subprocess.check_call("cargo clean && cargo build --release", shell=True, cwd=SDIR + "/apps/synthetic/")
        for nconns in [24, 1200]:
            x = assemble_synthetic("shenango", 14, dist="exponential", mpps=1.4, bg="swaptions", samples=20, nconns=nconns)
            x['name'] += "-{}conns-cycle_counted".format(nconns)
            execute_experiment(x)
    finally:
        subprocess.check_call("git checkout runtime/defs.h", shell=True, cwd=SDIR)
        subprocess.check_call("make", shell=True, cwd=SDIR)
        subprocess.check_call("cargo clean && cargo build --release", shell=True, cwd=SDIR + "/apps/synthetic/")

def paper_experiments():
    # load shift experiment
    if False:
        execute_experiment(loadshift("shenango"))
        execute_experiment(loadshift("arachne"))

    # local synthetic experiment
    if False:
        execute_experiment_noclients(
            assemble_local_synth(0.8, 1, 10, time=10, samples=40))

    # balancer interval experiment
    if False:
        for interval in [25, 50, 100]:
            run_balancer_experiment(interval)

    # memcached experiments
    if False:
        # Shenango, 1 MPPS at a time
        for start_mpps in range(6):
            execute_experiment(bench_memcached(
                "shenango", 12, start_mpps=start_mpps, mpps=start_mpps+1, bg="swaptions", samples=10))

        # Linux, higher sample rate below 1.6
        execute_experiment(bench_memcached(
            "linux", 16, mpps=1.6, samples=32, bg="swaptions"))
        execute_experiment(bench_memcached(
            "linux", 16, mpps=3.0, samples=14, bg="swaptions", start_mpps=1.6))

        # Arachne, higher sample rate below 1.6
        execute_experiment(bench_memcached(
            "arachne", 15, mpps=1.6, samples=32, bg="swaptions"))
        execute_experiment(bench_memcached(
            "arachne", 15, mpps=3.0, samples=14, bg="swaptions", start_mpps=1.6))

    # DNS experiments
    if False:
        execute_experiment(bench_dns(
            "shenango", mpps=6.0, thr=6, samples=60, bg="swaptions"))

        execute_experiment(bench_dns(
            "linux", mpps=2.0, thr=16, samples=20, bg="swaptions"))

    # synthetic graph
    if False:
        for sys, mpps in [("shenango", 1.4), ("linux-floating", 1.0), ("arachne", 1.0)]:
            for dist in ["exponential", "bimodal1", "constant"]:
                execute_experiment(assemble_synthetic(sys, 14, dist=dist, mpps=mpps, bg="swaptions"))

    # few connections experiments
    if False:
        x = assemble_synthetic("shenango", 14, dist="exponential", mpps=1.4, bg="swaptions", nconns=24)
        x['name'] += "-24conns"
        execute_experiment(x)

        run_cycle_counting_experiment()

    # zygos graphs
    if False:
        rep_external(bench_memcached, 6.5, 65, "zygos", 16)

        for dist in ["exponential", "bimodal1", "constant"]:
            rep_external(assemble_synthetic, 1.4, 40, "zygos", 16, dist=dist)

        rep_external(assemble_synthetic, 1.4, 40, "zygos", 16, dist="exponential", nconns=24)


if __name__ == '__main__':
    atexit.register(exitfn)
    if len(sys.argv) < 2 or sys.argv[1] == "server":
        assert is_server()

        paper_experiments()

    elif sys.argv[1] == "client":
        assert len(sys.argv) == 3
        go_client(sys.argv[2])
    elif sys.argv[1] == "observer":
        assert len(sys.argv) == 3
        go_observer(sys.argv[2])
    elif sys.argv[1] == "replay":
        assert len(sys.argv) == 3
        go_replay(sys.argv[2])
    else:
        assert False, 'bad arg'
