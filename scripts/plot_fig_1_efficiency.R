#!/usr/bin/env Rscript
# This script can be run using:
# ./plot_fig_1_efficiency.R <simulation> <shenango_local_synthetic>

# use the ggplot2 library
library(ggplot2)
library(plyr)

# read in data
args <- commandArgs(trailingOnly=TRUE)
simulation <- read.csv(args[1])
shenango <- read.csv(args[2])

theme_set(theme_bw(base_size=12))

shenango$Requestspers <- shenango$achieved
shenango$Efficiency <- shenango$achieved / (100*1000) / (shenango$totalcpu/100*24-2)
shenango$system <- "Shenango, 5 μs interval"
shenango <- shenango[shenango$p999 <= 100,]
simulation$system <- "Simulated upper bound, 1 ms interval"

head(simulation)
head(shenango)

all <- rbind.fill(simulation, shenango)
colors=c("#33a02c", "black")
linetypes=c("solid", "11")

annotation_color="#888888"
ggplot(all, aes(x=Requestspers/(1000*1000), y=Efficiency, color=system, linetype=system)) +
	    geom_line() +
	    labs(x="Throughput (million requests/s)", y="Efficiency") +
	    scale_y_continuous(breaks=c(0, .25, .50, .75, 1.00),
	    labels=c("0%", "25%", "50%", "75%", "100%"),
	    limits=c(0, 1.00)) +
	    scale_color_manual(values=colors) +
	    scale_linetype_manual(values=linetypes) +
	    coord_cartesian(xlim=c(0, 0.7)) +
	    theme(legend.position=c(0.75, 0.2), legend.title = element_blank(),
	    legend.background=element_blank(), legend.key=element_blank()) +
	    annotate("text", x=0.0, y=0.2, label="1 core", colour=annotation_color, angle=70) +
	    annotate("text", x=0.07, y=0.45, label="2", colour=annotation_color, angle=56) +
	    annotate("text", x=0.17, y=0.65, label="3", colour=annotation_color, angle=45) +
	    annotate("text", x=0.27, y=0.75, label="4", colour=annotation_color, angle=38) +
	    annotate("text", x=0.38, y=0.82, label="5", colour=annotation_color, angle=36) +
	    annotate("text", x=0.48, y=0.86, label="6", colour=annotation_color, angle=33) +
	    annotate("text", x=0.58, y=0.89, label="7", colour=annotation_color, angle=31) +
	    annotate("text", x=0.68, y=0.9, label="8", colour=annotation_color, angle=29) +
	    annotate("text", x=0.78, y=0.92, label="9", colour=annotation_color, angle=28)

ggsave("fig_1_efficiency.pdf", width=6, height=2.5, device = cairo_pdf)
