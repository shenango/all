# shenango-all

This repository includes Shenango and all of the applications,
benchmarks, and systems evaluated in the [Shenango paper at NSDI
2019](https://www.usenix.org/system/files/nsdi19-ousterhout.pdf).
Using this repository, you can reproduce all of the results in the
paper.

## Installing prereqs
```
sudo apt install build-essential libnuma-dev clang autoconf autotools-dev m4 automake libevent-dev  libpcre++-dev libtool ragel libev-dev moreutils parallel
```
Install rust, and use the nightly toolchain. See http://rust-lang.org/ for details.


## Compiling
To build everything for Shenango, Linux, and Arachne:
```
git submodule update --init --recursive
./build_all.sh
```
To clean: `./clean_all.sh.`

For instructions on building ZygOS or Memcached for ZygOS, please see
[their repositories](https://github.com/ix-project). After building
ZygOS, the spin server can be built with:
```
make -C ./bench/servers spin-ix
```
We built and ran ZygOS on Ubuntu 16.04.


## Running

To run the experiments, first run the installation instructions above
on your server. On your clients, clone the Shenango repo in your home
directory and build it (the experiments will use the iokernel built
there). Next, on the server, modify `experiment.py` so that the IPs,
MACs, PCIe address, and interface name match those in your
deployment. Also enable the experiments that you would like to run in
`paper_experiments` in `experiment.py`. Then run the experiments:
```
python experiment.py
```


## Analyzing
To process the results for the load shift experiment:
```
python loadshift_process.py <results_directory>
```
To process the results for all other experiments:
```
python summary.py <results_directory>
```

To reproduce the figures in the paper, install R and the packages
ggplot2, plyr, and cowplot (e.g., with `install.packages()` in the R
prompt).  Then run the R scripts in the scripts directory. Each script
includes a description of its arguments.