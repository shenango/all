
# usage: python summary.py <experiment directory>

import json
import os
import sys
from collections import defaultdict
import re

DISPLAYED_RSTAT_FIELDS = ["parks", "p_rx_ooo", "p_reorder_time"]

def percentile(latd, target):
    # latd: ({microseconds: count}, number_dropped)
    # target: percentile target, ie 0.99
    latd, dropped = latd
    count = sum([latd[k] for k in latd]) + dropped
    target_idx = int(float(count) * target)
    curIdx = 0
    for k in sorted(latd.keys()):
        curIdx += latd[k]
        if curIdx >= target_idx:
            return k
    return float("inf")

def read_lat_line(line):
    #line = line.split(" ", 1)[1]
    if line.startswith("Latencies: "):
        line = line[len("Latencies: "):]
    d = {}
    for l in line.strip().split():
        micros, count = l.split(":")
        d[int(micros)] = int(count)
    return d

def read_trace_line(line):
    if line.startswith("Trace: "):
        line = line[len("Trace: "):]
    points = []
    lats = defaultdict(int)
    for l in line.strip().split():
        start, delay, latency = l.split(":")
        if latency != "-1":
            lats[int(latency) // 1000] += 1
        if delay != "-1":
            points.append((int(start), int(latency)))
    return lats, points


# list_of_tuples: [({microseconds: count}, number_dropped)...]
def merge_lat(list_of_tuples):
    dropped = 0
    c = defaultdict(int)
    for s in list_of_tuples:
        for k in s[0]:
            c[k] += s[0][k]
        dropped += s[1]
    return c, dropped


def parse_loadgen_output(filename):
    with open(filename) as f:
        dat = f.read()

    samples = []

    line_starts = ["Latencies: ", "Trace: ", "zero, ","exponential, ",
                   "bimodal1, ", "constant, "]

    def get_line_start(line):
        for l in line_starts:
            if line.startswith(l): return l
        return None

    """Distribution, Target, Actual, Dropped, Never Sent, Median, 90th, 99th, 99.9th, 99.99th, Start"""
    header_line = None
    for line in dat.splitlines():
	#line = line.split(" ", 1)[1]
        line_start = get_line_start(line)
        if not line_start: continue
        if line_start == "Latencies: ":
            samples.append({
                'distribution': header_line[0],
                'offered': int(header_line[1]),
                'achieved': int(header_line[2]),
                'missed': int(header_line[4]),
                'latencies': (read_lat_line(line), int(header_line[3])),
                'time': int(header_line[10]),
            })
        elif line_start == "Trace: ":
            lats, tracepoints = read_trace_line(line)
            samples.append({
                'distribution': header_line[0],
                'offered': int(header_line[1]),
                'achieved': int(header_line[2]),
                'missed': int(header_line[4]),
                'latencies': (lats, int(header_line[3])),
                'tracepoints': tracepoints,
                'time': int(header_line[10]),
            })
        else:
            header_line = line.strip().split(", ")
            assert len(header_line) > 10 or len(header_line) == 6, line
            if len(header_line) == 6:
                 samples.append({
                 'distribution': header_line[0],
                 'offered': int(header_line[1]),
                 'achieved': 0,
                 'missed': int(header_line[4]),
                 'latencies': ({}, int(header_line[3])),
                 'time': int(header_line[5]),
            })
    return samples


def merge_sample_sets(a, b):
    samples = []
    for ea, eb in zip(a, b):
        assert set(ea.keys()) == set(eb.keys())
        assert ea['distribution'] == eb['distribution']
        # assert ea['app'] == eb['app']
        assert abs(ea['time'] - eb['time']) < 2
        newexp = {
            'distribution': ea['distribution'],
            'offered': ea['offered'] + eb['offered'],
            'achieved': ea['achieved'] + eb['achieved'],
            'missed': ea['missed'] + eb['missed'],
            'latencies': merge_lat([ea['latencies'], eb['latencies']]),
            # 'app': ea['app'],
            'time': min(ea['time'], eb['time']),
        }
        if 'tracepoints' in ea:
            newexp['tracepoints'] = ea['tracepoints'] + eb['tracepoints']
        samples.append(newexp)
        assert set(ea.keys()) == set(newexp.keys())
    return samples

def except_none(func):
	def e(*args, **kwargs):
		try:
			return func(*args, **kwargs)
		except:
			return None
	return e

@except_none
def load_app_output(app, directory, first_sample_time):

    parse_bg_key = {
        'swaptions': ("Swaption per second: ", None),
        'x264': ("/512 frames, ", " fps"),
        'stress': ("fakework rate: ", None)
    }
    #fixme
    if app['app'] not in parse_bg_key.keys():
        return None

    filename = "{}/{}.out".format(directory, app['name'])
    assert os.access(filename, os.F_OK)
    with open(filename) as f:
        bgdata = f.read()

    token_l, token_r = parse_bg_key.get(app['app'])

    lines = filter(lambda l: token_l in l, bgdata.splitlines())
    lines = map(lambda l: l.split(" ", 1), lines)

    datapoints = []
    for timestamp, line in lines:
        rate = line
        if token_l:
            rate = rate.split(token_l)[1]
        if token_r:
            rate = rate.split(token_r)[0]
        datapoints.append((int(timestamp), float(rate)))

    # baseline from first ten entries:
    x = datapoints[1:11]

    baseline = None
    if all([l[0] < first_sample_time for l in x]):
        baseline = sum([l[1] for l in x]) / len(x)

    return {
        'recorded_baseline': baseline,
        'recorded_samples': datapoints
    }

@except_none
def parse_iokernel_log(dirn, experiment):
    fname = "{dirn}/iokernel.{server_hostname}.log".format(
        dirn=dirn, **experiment)
    with open(fname) as f:
        data = f.read()
        int(data.split()[0])

    stats = defaultdict(list)
    data = data.split(" Stats:")[1:]
    for d in data:
        RX_P = None
        for line in d.strip().splitlines():
            if "eth stats for port" in line: continue
            dats = line.split()
            tm = int(dats[0])
            for stat_name, stat_val in zip(dats[1::2], dats[2::2]):
                stats[stat_name.replace(":", "")].append((tm, int(stat_val)))
                if stat_name == "RX_PULLED:": RX_P = float(stat_val)
                if stat_name == "BATCH_TOTAL:": stats['IOK_SATURATION'].append((tm, RX_P / float(stat_val)))
    return stats

@except_none
def parse_utilization(dirn, experiment):
    fname = "{dirn}/mpstat.{server_hostname}.log".format(
        dirn=dirn, **experiment)
    try:
        with open(fname) as f:
            data = f.read().splitlines()
        int(data[0].split()[0])
    except:
        return None

    cpuln = next(l for l in data if "_x86_64_" in l)
    ncpu = int(re.match(".*\((\d+) CPU.*", cpuln).group(1))
    headerln = next(l for l in data if "iowait" in l).split()
    # assume max 2 nodes
    assert "CPU" in headerln or "NODE" in headerln

    cols = {h: pos for pos, h in enumerate(headerln)}

    data = map(lambda l: l.split(), data)
    data = filter(lambda l: "%iowait" not in l and len(l) > 1, data[4:])

    if "NODE" in headerln:
        data = filter(lambda l: int(l[cols['NODE']]) == 0, data)
    else:
        assert all(lambda l: l[cols['CPU']] == 'all', data)

# % usr

# 100.0 - %idle
    data = map(lambda l: (int(l[0]), 100. - float(l[-1])), data)

    if not "NODE" in headerln:
        data = map(lambda a, b: a, 2 * b, data)

    return data

def parse_rstat(app, directory):
    fname = "{}/rstat.{}.log".format(directory, app['name'])
    try:
        with open(fname) as f:
            data = f.read().splitlines()
        int(data[0].split()[0])
    except:
        return None

    stat_vec = defaultdict(list)

    float_match = "([+-]*\d+.\d+|NaN|[+-]Inf)"
    netln_match = "(\d+) net: RX {f} pkts, {f} bytes \| TX {f} pkts, {f} bytes \| {f} drops \| {f}% rx out of order \({f}% reorder time\)".format(f=float_match)
    schedln_match = "(\d+) sched: {f} rescheds \({f}% sched time, {f}% local\), {f} softirqs \({f}% stolen\), {f} %CPU, {f} parks \({f}% migrated\), {f} preempts \({f} stolen\)".format(f=float_match)

    for line in data:
        match = re.match(netln_match, line)
        if match:
            ts = int(match.group(1))
            stat_vec['rxpkt'].append((ts, float(match.group(2))))
            stat_vec['rxbytes'].append((ts, float(match.group(3))))
            stat_vec['txpkt'].append((ts, float(match.group(4))))
            stat_vec['txbytes'].append((ts, float(match.group(5))))
            stat_vec['drops'].append((ts, float(match.group(6))))
            stat_vec['p_rx_ooo'].append((ts, float(match.group(7))))
            stat_vec['p_reorder_time'].append((ts, float(match.group(8))))
            continue
        match = re.match(schedln_match, line)
        if match:
            ts = int(match.group(1))
            stat_vec['rescheds'].append((ts, float(match.group(2))))
            stat_vec['schedtimepct'].append((ts, float(match.group(3))))
            stat_vec['localschedpct'].append((ts, float(match.group(4))))
            stat_vec['softirqs'].append((ts, float(match.group(5))))
            stat_vec['stolenirqpct'].append((ts, float(match.group(6))))
            stat_vec['cpupct'].append((ts, float(match.group(7))))
            stat_vec['parks'].append((ts, float(match.group(8))))
            stat_vec['migratedpct'].append((ts, float(match.group(9))))
            stat_vec['preempts'].append((ts, float(match.group(10))))
            stat_vec['stolenpct'].append((ts, float(match.group(11))))
            continue
        assert False, line
    return stat_vec

def extract_window(datapoints, wct_start, duration_sec):

    window_start = wct_start + int(duration_sec * 0.1)
    window_end = wct_start + int(duration_sec * 0.9)

    datapoints = filter(lambda l: l[0] >= window_start and l[
        0] <= window_end, datapoints)

    # Weight any gaps in reporting
    try:
        total = 0
        nsecs = 0
        for idx, (tm, rate) in enumerate(datapoints[1:]):
            nsec = tm - datapoints[idx][0]
            total += rate * nsec
            nsecs += nsec
        avgmids = total / nsecs
    except:
        avgmids = None

    return avgmids


def load_loadgen_results(experiment, dirname):
    insts = [i for host in experiment['clients'] for i in experiment['clients'][host]]
    if not insts:
         insts = [i for i in experiment['apps'] if i.get('protocol') == 'synthetic'] # local synth;
         print insts, [i for i in insts]
         experiment['clients'][experiment['server_hostname']] = insts #[i for i in insts if i.get('protocol') == 'synthetic'] #experiment['apps'] #semicorrect
    for inst in insts: #host in experiment['clients']:
 #       for inst in experiment['clients'][host]:
            filename = "{}/{}.out".format(dirname, inst['name'])
            assert os.access(filename, os.F_OK)
            data = parse_loadgen_output(filename)
           # assert len(data) == inst['samples'], filename
            if inst['name'] != "localsynth":
	            server_handle = inst['name'].split(".")[1] 
        	    app = next(app for app in experiment['apps'] if app['name'] == server_handle)
            else:
                    app = inst #local
            if not 'loadgen' in app:
                app['loadgen'] = data
            else:
                app['loadgen'] = merge_sample_sets(app['loadgen'], data)


    for app in experiment['apps']:
        if not 'loadgen' in app: continue
        for sample in app['loadgen']:
            latd = sample['latencies']
            sample['p50'] = percentile(latd, 0.5)
            sample['p90'] = percentile(latd, 0.9)
            sample['p99'] = percentile(latd, 0.99)
            sample['p999'] = percentile(latd, 0.999)
            sample['p9999'] = percentile(latd, 0.9999)
            del sample['latencies']
            sample['app'] = app

def parse_dir(dirname):
    files = os.listdir(dirname)
    assert "config.json" in files
    with open(dirname + "/config.json") as f:
         experiment = json.loads(f.read())

    load_loadgen_results(experiment, dirname)

    start_time = min(sample['time'] for app in experiment['apps'] for sample in app.get('loadgen', []))

    for app in experiment['apps']:
        app['output'] = load_app_output(app, dirname, start_time)
        app['rstat'] = parse_rstat(app, dirname)

    experiment['mpstat'] = parse_utilization(dirname, experiment)
    experiment['ioklog'] = parse_iokernel_log(dirname, experiment)

    return experiment

def arrange_2d_results(experiment):
    # per start time: the 1 background app of choice, aggregate throughtput,  
    # 1 line per start time per server application

    by_time_point = zip(*(app['loadgen'] for app in experiment['apps'] if 'loadgen' in app))
    bgs = [app for app in experiment['apps'] if app['output']]
    # TODO support multiple bg apps
    assert len(bgs) <= 1
    bg = bgs[0] if bgs else None

    runtime = experiment['clients'].itervalues().next()[0]['runtime']

    header1 = ["system", "app", "background", "transport", "spin", "nconns", "threads"]
    header2 = ["offered", "achieved", "p50", "p90", "p99", "p999", "p9999", "distribution"]
    header3 = ["tput", "baseline", "totaloffered", "totalachieved",
              "totalcpu"] #, "localcpu", "ioksaturation"]

    header = header1 + header2 + header3 + DISPLAYED_RSTAT_FIELDS

    lines = [header]
    ncons = 0
    for list_pm in experiment['clients'].itervalues():
        for i in list_pm: ncons += i['client_threads']
#    nconns = sum(

    for time_point in by_time_point:
        times = set(t['time'] for t in time_point)
        #assert len(times) == 1 # all start times are the same
        time = times.pop()
	if len(times) == 1: assert abs(times.pop() - time) <= 1
	else: assert len(times) == 0
        bgbaseline = bg['output']['recorded_baseline'] if bg else 0
        bgtput = extract_window(bg['output']['recorded_samples'], time, runtime) if bg else 0
	if bgtput is None: bgtput = 0
        cpu = extract_window(experiment['mpstat'], time, runtime) if experiment['mpstat'] else None
        total_offered = sum(t['offered'] for t in time_point)
        total_achieved = sum(t['achieved'] for t in time_point)
        iok_saturation = extract_window(experiment['ioklog']['IOK_SATURATION'], time, runtime) if experiment['ioklog'] else None
        for point in time_point:
            out = [experiment['system'], point['app']['app'], bg['app'] if bg else None, point['app'].get('transport', None), point['app']['spin'] > 1, ncons, point['app']['threads']]
            out += [point[k] for k in header2]
            out += [bgtput, bgbaseline, total_offered, total_achieved, cpu]
            """if point['app']['rstat']:
                out.append(extract_window(point['app']['rstat']['cpupct'], time, runtime))
            else:
                out.append(None)
            out.append(iok_saturation)"""
            for field in DISPLAYED_RSTAT_FIELDS:
		if point['app']['rstat']:
			out.append(extract_window(point['app']['rstat'][field], time, runtime))
		else:
			out.append(None)
            lines.append(out)
        for bgl in bgs:
            continue; out = [experiment['system'], bgl['app'], bg['app'] if bg else None, 
                    None, bgl['spin'] > 1]
            out += [0]*7 + [None]
            out.append(extract_window(bgl['output']['recorded_samples'], time, runtime))
            out.append(bgl['output']['recorded_baseline'])
            out += [total_offered, total_achieved, cpu]
            """if bgl['rstat']:
                out.append(extract_window(bgl['rstat']['cpupct'], time, runtime))
            else:
                out.append(None)
            out.append(iok_saturation)"""
            for field in DISPLAYED_RSTAT_FIELDS:
                if point['app']['rstat']:
                        out.append(extract_window(point['app']['rstat'][field], time, runtime))
                else:
                        out.append(None)
            lines.append(out)

    return lines



def rotate(output_lines):
    resdict = {}
    headers = output_lines[0]
    for i, h in enumerate(headers):
        resdict[h] = [l[i] for l in output_lines[1:]]
    return resdict


def print_res(res):
    for line in res:
        print ",".join([str(x) for x in line])

def do_it_all(dirname):

    exp = parse_dir(dirname)
    stats = arrange_2d_results(exp)

    bycol = rotate(stats)

    STAT_F = "{}/stats/".format(dirname)
    os.system("mkdir -p " + STAT_F)

    with open(STAT_F + "stat.csv", "w") as f:
        for line in stats:
            x = ",".join([str(x) for x in line])
            print x
            f.write(x + '\n')

    return bycol

def main():
    all_res = []
    for d in sys.argv[1:]:
        do_it_all(d)

if __name__ == '__main__':
    main()
