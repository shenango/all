import sys, os

from heapq import merge
from multiprocessing import Pool

WARMUP=1e9

def readfile(f):
		with open(f) as ff:
			dat = ff.read().splitlines()
		dat = filter(lambda d: d.startswith("Trace: "), dat)
		dat = [t[len("Trace: "):].split() for t in dat]
		dat = [map(float, x.split(":")) for t in dat for x in t]
		x = sorted([(a,c) if c > 0 else (a, float("inf")) for a,b,c in dat if a > 1e8+WARMUP])
		return x

def readdir(dirname):
	files = ["{}/{}".format(dirname, f) for f in os.listdir(dirname) if f.endswith(".out")]

	p = Pool()
	sublists = p.map(readfile, files)
	p.close()
	p.join()

	return merge(*sublists)

def lat(l):
        PCT = 0.999
        w = sorted(l)
        return w[int(len(w)*PCT)-1] // 1e3

def time_downsample(pairs, ns_per_sample=10000000):

	print "Sampling latency at {:,} ns intervals".format(ns_per_sample)

	timestamps, latencies = zip(*pairs)

	print "Datapoints:", len(timestamps)
	x_out = []
	y_out = []
	z_out = []
	PCT = 0.999
	base = timestamps[0] + ns_per_sample
	while len(latencies) > 1000:
		print len(latencies)
		# count number of points in this interval
		i = 0
		l = []
		while i < len(timestamps) and timestamps[i] <= base:
			l.append(latencies[i])
			i += 1

		# extract the latencies for this window
		w = sorted(l)

		# append timestamp, latency, throughput
		x_out.append((base - ns_per_sample / 2) / 1e3) # microseconds
		y_out.append(w[int(i*PCT)-1] // 1e3) # microseconds
		z_out.append(1e9 * i / ns_per_sample) # pps

		timestamps = timestamps[i:]
		latencies = latencies[i:]
		base += ns_per_sample


	first_ts = x_out[0]
	x_out = map(lambda a: a - first_ts, x_out)
	# p = Pool()
	# y_out = p.map(lat, y_out_temp)
	# p.close()
	# p.join()
	return x_out, y_out, z_out


def write_dat(dirn, xs, ys, zs):
	system = "shenango" if "shenango" in dirn else "arachne" if "arachne" in dirn else "linux"
	with open(dirn + "/microburst.dat", "w") as f:
		f.write("time_us p999 tput system\n")
		for x, y, z in zip(xs, ys, zs):
			f.write("{} {} {} {}\n".format(x, y, z, system))


write_dat(sys.argv[1], *time_downsample(readdir(sys.argv[1])))
