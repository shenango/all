#!/usr/bin/env Rscript
# This script can be run using:
# ./plot_fig_4_synthetic.R <synthetic_data> <simulated>

# use the ggplot2 library
library(ggplot2)
library(cowplot)
library(plyr)

# read in data
args <- commandArgs(trailingOnly=TRUE)
all <- read.csv(args[1])
simulated <- read.csv(args[2], sep=" ")

theme_set(theme_bw(base_size=11))

all$label <- ifelse(all$system == "arachne", "Arachne",
	  ifelse(all$system == "shenango", "Shenango",
	  ifelse(all$system == "zygos", "ZygOS",
	  ifelse(all$system == "linux-floating", "Linux", "???"))))

all$hex_color <- ifelse(all$system == "arachne", "#6a3d9a",
	  ifelse(all$system == "shenango", "#33a02c",
	  ifelse(all$system == "zygos", "#1f78b4",
	  ifelse(all$system == "linux-floating", "#e31a1c", "???"))))

all$linetype <- ifelse(all$system == "arachne", "42",
	  ifelse(all$system == "shenango", "solid",
	  ifelse(all$system == "zygos", "a2",
	  ifelse(all$system == "linux-floating", "11", "???"))))

all$distribution <- as.character(all$distribution)
all$distribution <- ifelse(all$distribution == "bimodal1", "bimodal", all$distribution)

all$distribution <- factor(all$distribution, levels=c("constant", "exponential", "bimodal"))
tail(all)

# only retain data points with finite 99.9% latency
all <- all[all$p999 != "Inf",]
all$normalized <- all$achieved / (1.6*1000*1000)
all$totalcpu <- ifelse(all$totalcpu == "None", 0, all$totalcpu)
all <- all[all$background == "swaptions" | all$system == "zygos",]
x_max = 1.6
x_breaks=c(0, 0.4, 0.8, 1.2, 1.6)

simulated$label = "Theoretical M/G/16/FCFS"
simulated$hex_color = "#555555"
simulated$linetype = "solid"
simulated$achieved <- simulated$qps * 1000 * 1000
simulated$system = "simulation"

all <- rbind.fill(all, simulated)
all$label <- factor(all$label, c("Linux", "Arachne", "Shenango", "ZygOS", "Theoretical M/G/16/FCFS"), ordered=TRUE)

tail(all)


l_colors <- all$hex_color
names(l_colors) <- all$label
l_linetypes <- all$linetype
names(l_linetypes) <- all$label
plot_latency <- ggplot(all, aes(x=achieved/(1000*1000), y=p999, color=label, linetype=label)) +
	    geom_line() +
	    facet_grid(.~distribution) +
	    coord_cartesian(ylim=c(0, 300)) +
	    scale_x_continuous(lim=c(0, x_max), breaks=x_breaks) +
	    labs(y="99.9% Latency (μs)") +
	    theme(legend.position="top", legend.title = element_blank(),
	    axis.title.x=element_blank(), axis.title.y=element_text(hjust=0.3),
	    legend.margin=margin(c(-8, 0, -8, 0)), legend.text=element_text(size=11)) +
	    scale_linetype_manual(values=l_linetypes) +
	    scale_color_manual(values=l_colors)

summary(all$tput)
plot_tput <- ggplot(all, aes(x=achieved/(1000*1000), y=tput, color=label, linetype=label)) +
	    geom_line() +
	    facet_grid(. ~ distribution) +
	    scale_x_continuous(lim=c(0, x_max), breaks=x_breaks) +
	    scale_y_continuous(lim=c(0,120), breaks=c(0, 50, 100)) +
	    labs(x="Spin Server Offered Load (million requests/s)", y="Batch Ops/s") +
	    theme(legend.position="none", strip.background = element_blank(), strip.text.x = element_blank()) +
	    scale_linetype_manual(values=l_linetypes) +
	    scale_color_manual(values=l_colors)

plot_grid(plot_latency, plot_tput, ncol=1, align="v", axis="l", rel_heights=c(1,0.8))

ggsave("fig_4_synthetic.pdf", width=9, height=3.3, device = cairo_pdf)
