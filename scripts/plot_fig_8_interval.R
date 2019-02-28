#!/usr/bin/env Rscript
# This script can be run using:
# ./plot_fig_8_interval.R <all_synthetic> <data_25us> <data_50us> <data_100us>

# use the ggplot2 library
library(ggplot2)
library(plyr)

# read in data
args <- commandArgs(trailingOnly=TRUE)
d5 <- read.csv(args[1])
d25 <- read.csv(args[2])
d50 <- read.csv(args[3])
d100 <- read.csv(args[4])

theme_set(theme_bw(base_size=11))

d5$interval <- 5
d5 <- d5[d5$system == "shenango" &
   d5$distribution == "exponential" &
   d5$spin == "False" &
   d5$background == "swaptions",]
d25$interval <- 25
d50$interval <- 50
d100$interval <- 100

all <- rbind.fill(d5, d25, d50, d100)
all$interval <- factor(all$interval)
all$interval <- factor(all$interval, levels=rev(levels(all$interval)))
all <- all[all$p999 != "Inf",]
all <- all[all$offered >= 50000,]

y_axis_label = "99.9% Latency (μs)"
legend_label = "Interval (μs)"
colors=c('#74c476', '#41ab5d', '#238b45', '#005a32')
linetypes = c("22","72", "a2", "solid")


x_max = 1.3
x_breaks = c(0, 0.4, 0.8, 1.2)

ggplot(all, aes(x=achieved/(1000*1000), y=p999, color=interval, linetype=interval)) +
	    geom_line() +
	    coord_cartesian(ylim=c(0,500)) +
	    scale_x_continuous(lim=c(0, x_max), breaks=x_breaks) +
	    labs(y=y_axis_label, x="Spin Server Offered Load (million requests/s)") +
	    scale_color_manual(name=legend_label, values=colors) +
	    scale_linetype_manual(name=legend_label, values=linetypes) +
	    theme(legend.position="top", legend.background=element_blank(),
	    legend.direction="horizontal", legend.key=element_blank(),
	    legend.margin=margin(c(-4, 8, -8, 0)))

ggsave("fig_8_interval.pdf", width=4.5, height=1.8, device = cairo_pdf)
