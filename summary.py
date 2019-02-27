
# usage: python summary.py <experiment directory>

import json
import os
import sys
from collections import defaultdict
import re

USE_PARALLEL = False # Useful for reading many large files
DISPLAYED_RSTAT_FIELDS = ["parks", "p_rx_ooo", "p_reorder_time"]

import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams['lines.markersize'] /= 8

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
# returns: latencies as {microseconds: count}
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


def parse_file(filename):
    machine, app, out = os.path.basename(filename).split(".")
    machine = machine.split("-")[-1]
    assert out == "out" and machine.startswith("pd") or machine in ["zig", "zag"]
    with open(filename) as f:
        dat = f.read()
    experiments = []

    line_starts = ["Latencies: ", "Trace: ", "zero, ","exponential, ",
                   "bimodal1, ", "constant, "]

    def get_line_start(line):
        for l in line_starts:
            if line.startswith(l): return l
        return None

    """Distribution, Target, Actual, Dropped, Never Sent, Median, 90th, 99th, 99.9th, 99.99th, Start"""
    header_line = None
    for line in dat.splitlines():
        line_start = get_line_start(line)
        if not line_start: continue
        if line_start == "Latencies: ":
            experiments.append({
                'distribution': header_line[0],
                'target': int(header_line[1]),
                'achieved': int(header_line[2]),
                'missed': int(header_line[4]),
                'latencies': (read_lat_line(line), int(header_line[3])),
                # 'dat': [(header_line, line)],
                'time': int(header_line[10]) if len(header_line) > 10 else None,
                'app': app,
            })
        elif line_start == "Trace: ":
            lats, tracepoints = read_trace_line(line)
            experiments.append({
                'distribution': header_line[0],
                'target': int(header_line[1]),
                'achieved': int(header_line[2]),
                'missed': int(header_line[4]),
                'latencies': (lats, int(header_line[3])),
                'tracepoints': tracepoints,
                # 'dat': [(header_line, line)],
                'time': int(header_line[10]) if len(header_line) > 10 else None,
                'app': app,
            })
        else:
            header_line = line.strip().split(", ")
            if len(header_line) == 6:
                experiments.append({
                'distribution': header_line[0],
                'target': 0,
                'achieved': 0,
                'missed': int(header_line[4]),
                'latencies': ({}, int(header_line[3])),
                'time': int(header_line[5]),
                'app': app,
            })
    return experiments


def merge_experiments(a, b):
    experiments = []
    for ea, eb in zip(a, b):
        assert set(ea.keys()) == set(eb.keys())
        assert ea['distribution'] == eb['distribution']
        assert ea['app'] == eb['app']
        assert abs(ea['time'] - eb['time']) < 2
        newexp = {
            'distribution': ea['distribution'],
            'target': ea['target'] + eb['target'],
            'achieved': ea['achieved'] + eb['achieved'],
            'missed': ea['missed'] + eb['missed'],
            'latencies': merge_lat([ea['latencies'], eb['latencies']]),
            # 'dat': ea['dat'] + eb['dat'],
            'app': ea['app'],
            'time': min(ea['time'], eb['time']),
        }
        if 'tracepoints' in ea:
            newexp['tracepoints'] = ea['tracepoints'] + eb['tracepoints']
        experiments.append(newexp)
        assert set(ea.keys()) == set(newexp.keys())
    return experiments

def thelats(latd):
    return [
        percentile(latd, 0.5),
        percentile(latd, 0.9),
        percentile(latd, 0.99),
        percentile(latd, 0.999),
        percentile(latd, 0.9999)
    ]


def parse_bg(dirn, files, first_exp_time):
    patterns = ["background_work.log", "swaptions.*out", "x264.*out"]
    bgfiles = [f for f in files for p in patterns if re.match(p, f)]
    if bgfiles:
        assert len(bgfiles) == 1
        with open(dirn + "/" + bgfiles[0]) as f:
            bgdata = f.read()
    else:
        return "None", 0, None

    if "Swaption" in bgdata:
        token_l = "Swaption per second: "
        token_r = None
        app = "swaptions"
    elif "x264" in bgdata:
        token_l = "/512 frames, "
        token_r = " fps,"
        app = "x264"
    else:
        assert False

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
    if all([l[0] < first_exp_time for l in x]):
        baseline = sum([l[1] for l in x]) / len(x)

    return app, baseline, datapoints


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

    data = map(lambda l: (int(l[0]), 100. - float(l[-1])), data)

    if not "NODE" in headerln:
        data = map(lambda a, b: a, 2 * b, data)

    return data

def parse_rstat(dirn, experiment, app_name):
    # pass
    fname = "{dirn}/rstat.{app_name}.log".format(dirn=dirn, app_name=app_name)
    try:
        with open(fname) as f:
            data = f.read().splitlines()
        int(data[0].split()[0])
    except:
        return None

    stat_vec = defaultdict(list)

    float_match = "([+-]*\d+.\d+|NaN|Inf)"
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
            stat_vec['schedtime%'].append((ts, float(match.group(3))))
            stat_vec['localsched%'].append((ts, float(match.group(4))))
            stat_vec['softirqs'].append((ts, float(match.group(5))))
            stat_vec['stolenirq%'].append((ts, float(match.group(6))))
            stat_vec['cpu%'].append((ts, float(match.group(7))))
            stat_vec['parks'].append((ts, float(match.group(8))))
            stat_vec['migrated%'].append((ts, float(match.group(9))))
            stat_vec['preempts'].append((ts, float(match.group(10))))
            stat_vec['stolen%'].append((ts, float(match.group(11))))
            continue
        assert False, line
    return stat_vec

def extract_window(datapoints, wct_start, duration_sec):

    window_start = wct_start + int(duration_sec * 0.2)
    window_end = wct_start + int(duration_sec * 0.8)

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

def parse_dir(dirn):
    files = os.listdir(dirn)
    assert "config.json" in files
    with open(dirn + "/config.json") as f:
        experiment = json.loads(f.read())

    app_data = defaultdict(list)
    num_data_points = None

    to_parse = []

    for f in filter(lambda a: a.endswith(".out"), files):
        fs = f.split(".")
        if len(fs) != 3:
            continue  # irg
        # could probably remove this stuff
        machine, app, _ = fs
        machine = machine.split("-")[-1]
        assert machine in ["zig", "zag"] or machine.startswith("pd")
        to_parse.append(dirn + "/" + f)
        continue

    if USE_PARALLEL:
        import multiprocessing
        p = multiprocessing.Pool()
        expers = p.map(parse_file, to_parse)
        p.close()
        p.join()
    else:
        expers = map(parse_file, to_parse)

    num_data_points = len(expers[0])
    assert all(len(e) == len(expers[0]) for e in expers)
    assert num_data_points, str(files)

    for e in expers:
        app_data[e[0]['app']].append(e)

    app_data = map(lambda a: reduce(merge_experiments, app_data[a]), app_data)

    first_time = [app[0] for app in app_data][0]['time']
    bgapp, bgbase, bgdatapoints = parse_bg(dirn, files, first_time)
    util_datapoints = parse_utilization(dirn, experiment)

    rstats = {}

    for points in app_data:
        app_name = points[0]['app']
        rstat_vec = parse_rstat(dirn, experiment, app_name)
        if rstat_vec:
            rstats[app_name] = rstat_vec

    parse_tuple = (experiment, app_data, num_data_points,
                   first_time, bgapp, bgbase, bgdatapoints, util_datapoints, rstats)

    return parse_tuple


def stat_results(ptuple):

    experiment, app_data, num_data_points, first_time, bgapp, bgbase, bgdatapoints, util_datapoints, rstats = ptuple

    tmp = experiment['clients'].keys()[0]  # first client
    tmp = experiment['clients'][tmp][0]  # list of cmds
    if type(tmp) == unicode:  # 2 formats for now
        assert False  # remove this case soon
        runtime = int(tmp.split("--runtime ")[1].split()[0])
    elif type(tmp) == dict:
        runtime = tmp['runtime']

    distributions = set([e['distribution'] for app in app_data for e in app])
    if "zero" in distributions:
        assert len(distributions) == 1

    output_lines = []

    header = ["system", "app", "background", "offered", "achieved", "p50", "p90", "p99",
              "p999", "p9999", "tput", "baseline", "totaloffered", "totalachieved",
              "totalcpu", "transport", "spin"]
    if "zero" not in distributions:
        header.append("distribution")
    header += DISPLAYED_RSTAT_FIELDS
    output_lines.append(header)

    for i in range(num_data_points):
        expers = [app[i] for app in app_data]
        times = list(set([e['time'] for e in expers]))
        assert len(times) < 3
        if len(times) == 2:
            assert abs(times[0] - times[1]) < 2

        bgtput = 0
        time = times.pop()
        if bgdatapoints:
            bgtput = extract_window(bgdatapoints, time, runtime)

        util = None
        if util_datapoints:
            util = extract_window(util_datapoints, time, runtime)

        total_offered = sum([e['target'] for e in expers])
        total_achieved = sum([e['achieved'] for e in expers])

        spin = str("spin" in experiment['name'])
        for e in expers:
            out = [experiment['system'], e['app'], bgapp]
            out += [e['target'], e['achieved']]
            out += thelats(e['latencies'])
            out += [bgtput, bgbase, total_offered, total_achieved, util, experiment['transport'], spin]
            if "zero" not in distributions:
                out += [e['distribution']]
            for field in DISPLAYED_RSTAT_FIELDS:
                if rstats and e['app'] in rstats:
                    out.append(extract_window(rstats[e['app']][field], time, runtime))
                else:
                    out.append(None)
            output_lines.append(out)

        if False:  # useful for multiapp R script to have this line
            out = [experiment['system'], bgapp, bgapp]
            out += [0] * 7
            out += [bgtput, bgbase, total_offered, total_achieved]
            output_lines.append(out)

    return output_lines

def rotate(output_lines):
    resdict = {}
    headers = output_lines[0]
    for i, h in enumerate(headers):
        resdict[h] = [l[i] for l in output_lines[1:]]
    return resdict


def lat_time_series(points, outfile, ns_granularity=1e9):
    plt.clf()
    points.sort()
    assert points == sorted(points, key=lambda l: l[0])

    slice_points = []
    cur_idx = 0
    cur_idx_start = 0
    while cur_idx <= len(points):
        if cur_idx == len(points) or points[cur_idx][0] >= points[cur_idx_start][0] + ns_granularity:
            slice_points.append((cur_idx_start, cur_idx))
            cur_idx_start = cur_idx
            if cur_idx == len(points): break
            continue
        cur_idx += 1

    p999s = []
    tputs = []

    for start, end in slice_points:
        latd = defaultdict(int)
        dropped = 0
        for i in xrange(start, end):
            if points[i][1] < 0:
                dropped += 1
            else:
                latd[points[i][1] // 1000] += 1
        tputs.append(((end - start) * 1e9) / ns_granularity)
        p999s.append(percentile((latd, dropped), 0.999))
        del latd

    # print "done w/ slice points"

    plt.subplot(2, 1, 1).set_ylim(0, 1000)
    plt.scatter(list(range(len(p999s))), p999s)
    plt.ylabel("99.9% Latency (us)")

    plt.subplot(2, 1, 2)
    plt.scatter(list(range(len(p999s))), tputs)
    plt.ylabel("Throughput - Achieved RPS")


    plt.xlabel("Time")

    plt.legend()
    plt.savefig(outfile)

def scatter_trace(points, outfile):

    plt.clf()

    if not points or not points[0]:
        return

    first_data_point = points[0][0]

    tps = filter(lambda (a, b): b != -1, points)
    dropped = filter(lambda (a,b): b == -1, points)

    xs = [(tm[0] - first_data_point) // 1000 for tm in tps]
    xd = [(tm[0] - first_data_point) // 1000 for tm in dropped]
    ys = [tm[1] // 1000 for tm in tps]

    # max_l = max(ys)

    print len(tps), len(dropped)

    plt.scatter(xs, ys)
    plt.scatter(xd, [990 for i in range(len(xd))], c="orange", s=plt.rcParams['lines.markersize']*4)

    plt.ylim(0, 1000)

    plt.ylabel("Latency (us)")
    plt.xlabel("Time (us)")

    plt.savefig(outfile)


def graph_experiment(bycols, outfile):
    ## Tput-latency-perapp
    all_apps = set(bycols['app'])
    nlines = len(bycols['app'])

    notput = set(bycols['tput']) == set([None])
    nplots = 2 if notput else 3

    plt.clf()
    plt.subplot(nplots, 1, 1).set_ylim(0, 300)
    plt.ylabel("99.9% latency (us)")

    for app in all_apps:
        idxs = set(i for i in range(nlines) if bycols['app'][i] == app)
        xs = [bycols['achieved'][i] for i in range(nlines) if i in idxs]
        ys = [bycols['p999'][i] for i in range(nlines) if i in idxs]
        # xs = list(range(len(ys)))
        if sum(ys) == 0:
            continue
        plt.plot(xs, ys, label=app)


    # Be unnecessarily cautious here...
    assert nlines % len(all_apps) == 0
    actual_npoints = nlines / len(all_apps)
    achieved = [bycols['totalachieved'][i * actual_npoints : (i + 1) * actual_npoints] for i in range(len(all_apps))]
    assert all(a == achieved[0] for a in achieved)
    cpu = [bycols['totalcpu'][i * actual_npoints : (i + 1) * actual_npoints] for i in range(len(all_apps))]
    assert all(a == cpu[0] for a in cpu)
    tput = [bycols['tput'][i * actual_npoints : (i + 1) * actual_npoints] for i in range(len(all_apps))]
    assert all(a == tput[0] for a in tput)

    plt.subplot(nplots, 1, 2).set_ylim(0, 100)
    plt.ylabel("CPU Utilization (%)")
    plt.plot(achieved[0], cpu[0], label="utilization")

    if not notput:
        plt.subplot(nplots, 1, 3).set_ylim(0, 200)
        plt.ylabel("Background Throughput")
        plt.plot(achieved[0], tput[0], label="throughput")

    plt.xlabel("RPS")

    plt.legend()
    plt.savefig(outfile)


def print_res(res):
    for line in res:
        print ",".join([str(x) for x in line])

def do_it_all(dirname):

    parsed_stuff = parse_dir(dirname)

    stats = stat_results(parsed_stuff)

    bycol = rotate(stats)

    STAT_F = "{}/stats/".format(dirname)
    os.system("mkdir -p " + STAT_F)

    graph_experiment(bycol, STAT_F + "graphs.png")

    # for app in parsed_stuff[1]:
    #     if "constant" in dirname.lower():
    #         for i, dp in enumerate(app):
    #             if 'tracepoints' in dp:
    #                 scatter_trace(dp['tracepoints'], STAT_F + "trace-" + str(i) + ".png")
    #                 # lat_time_series(dp['tracepoints'], STAT_F + "ts-1s-" + str(i) + ".png")
    #                 # lat_time_series(dp['tracepoints'], STAT_F + "ts-0.5s-" + str(i) + ".png", 1e9/2)
    #                 # lat_time_series(dp['tracepoints'], STAT_F + "ts-2s-" + str(i) + ".png", 1e9*2)
    #     else:
    #         if not all('tracepoints' in dp for dp in app):
    #             continue
    #         flat_points = []
    #         for dp in app:
    #             flat_points += dp['tracepoints']
    #         scatter_trace(flat_points, STAT_F + "trace.png")
    #         lat_time_series(flat_points, STAT_F + "ts-50ms.png", 5e7)
    #         lat_time_series(flat_points, STAT_F + "ts-1s.png")
    #         lat_time_series(flat_points, STAT_F + "ts-0.5s.png", 1e9/2)
    #         lat_time_series(flat_points, STAT_F + "ts-2s.png", 1e9*2)


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
