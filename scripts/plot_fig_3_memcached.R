#!/usr/bin/env Rscript
# This script can be run using:
# ./plot_fig_3_memcache.R <memcached_data>

# use the ggplot2 library
library(ggplot2)
library(cowplot)

# read in data
args <- commandArgs(trailingOnly=TRUE)
all <- read.csv(args[1])

theme_set(theme_bw(base_size=11))

all$label <- ifelse(all$system == "arachne", "Arachne",
	  ifelse(all$system == "shenango", "Shenango",
	  ifelse(all$system == "zygos", "ZygOS",
	  ifelse(all$system == "linux", "Linux", "???"))))

all$hex_color <- ifelse(all$system == "arachne", "#6a3d9a",
	  ifelse(all$system == "shenango", "#33a02c",
	  ifelse(all$system == "zygos", "#1f78b4",
	  ifelse(all$system == "linux", "#e31a1c", "???"))))

all$linetype <- ifelse(all$system == "arachne", "42",
	  ifelse(all$system == "shenango", "solid",
	  ifelse(all$system == "zygos", "a2",
	  ifelse(all$system == "linux", "11", "???"))))

all <- all[all$p999 != "Inf",]
all <- all[all$background == "swaptions" | all$system == "zygos",]
all$label <- factor(all$label, c("Linux", "Arachne", "Shenango", "ZygOS"), ordered=TRUE)

l_colors <- all$hex_color
names(l_colors) <- all$label
l_linetypes <- all$linetype
names(l_linetypes) <- all$label
x_max = 6.0
max(all$tput)
plot_p999 <- ggplot(all, aes(x=achieved/(1000*1000), y=p999, color=label, linetype=label)) +
	    geom_line() +
	    coord_cartesian(ylim=c(0, 400), xlim=c(0, x_max)) +
	    labs(x="Memcached Offered Load (million requests/s)", y="99.9% Latency (μs)") +
	    theme(legend.position="top", legend.title = element_blank(),
	    axis.title.x=element_blank(), legend.margin=margin(c(-8, 0, -8, 0)), legend.text=element_text(size=11)) +
	    scale_linetype_manual(values=l_linetypes) +
	    scale_color_manual(values=l_colors)

plot_median <- ggplot(all, aes(x=achieved/(1000*1000), y=p50, color=label, linetype=label)) +
	    geom_line() +
	    coord_cartesian(ylim=c(0, 70), xlim=c(0, x_max)) +
	    labs(x="Memcached Offered Load (million requests/s)", y="Median Latency (μs)") +
	    theme(legend.position="none", axis.title.x=element_blank()) +
	    scale_linetype_manual(values=l_linetypes) +
	    scale_color_manual(values=l_colors)

plot_tput <- ggplot(all, aes(x=achieved/(1000*1000), y=tput, color=label, linetype=label)) +
	    geom_line() +
	    coord_cartesian(xlim=c(0, x_max)) +
	    scale_y_continuous(lim=c(0,115), breaks=c(0, 25, 50, 75, 100)) +
	    theme(legend.position="none", axis.title.y=element_text(hjust=0.7)) +
	    labs(x="Memcached Offered Load (million requests/s)", y="Batch Ops/s") +
	    scale_linetype_manual(values=l_linetypes) +
	    scale_color_manual(values=l_colors)

plot_grid(plot_p999, plot_median, plot_tput, ncol=1, rel_heights=c(1,0.9,1),
		     align = "v", axis="l")

ggsave("fig_3_memcached.pdf", width=5, height=4.9, device = cairo_pdf)
