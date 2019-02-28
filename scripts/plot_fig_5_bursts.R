#!/usr/bin/env Rscript
# This script can be run using:
# ./plot_fig_5_bursts.R <data>

# use the ggplot2 library
library(ggplot2)
library(cowplot)

# read in data
args <- commandArgs(trailingOnly=TRUE)
all <- read.csv(args[1], sep=" ")

head(all)
theme_set(theme_bw(base_size=11))

all$label <- ifelse(all$system == "arachne", "Arachne", "Shenango") # both have background
all$hex_color <- ifelse(all$system == "arachne", "#6a3d9a", "#33a02c")
all$linetype <- ifelse(all$system == "arachne", "42", "solid")

all$label <- factor(all$label, c("Shenango", "Arachne"), ordered=TRUE)

l_colors <- all$hex_color
names(l_colors) <- all$label
l_linetypes <- all$linetype
names(l_linetypes) <- all$label

plot_latency <- ggplot(all, aes(x=time_us / (1000*1000), y=p999, color=label, linetype=label)) +
	    geom_line() +
	    labs(y="99.9% Latency (μs)") +
	    theme(legend.position="top", legend.title = element_blank(),
	    axis.title.x=element_blank(), legend.margin=margin(c(-8, 16, -8, 0)), legend.text=element_text(size=11)) +
	    coord_cartesian(ylim=c(0, 1000)) +
	    scale_linetype_manual(values=l_linetypes, guide = guide_legend(reverse = TRUE)) +
	    scale_color_manual(values=l_colors, guide = guide_legend(reverse = TRUE))

plot_achieved <- ggplot(all, aes(x=time_us / (1000*1000), y=tput / (1000*1000), color=label, linetype=label)) +
	      geom_line() +
	      labs(x="Time (s)", y="Throughput\n(million requests/s)") +
	      theme(legend.position="none", axis.title.y=element_text(vjust=-2)) +
	      coord_cartesian(ylim=c(0,5)) +
	      scale_linetype_manual(values=l_linetypes) +
	      scale_color_manual(values=l_colors)

plot_grid(plot_latency, plot_achieved, ncol=1, rel_heights=c(1.5, 1), align="v", axis="l")

ggsave("fig_5_bursts.pdf", width=4.5, height=2.8, device = cairo_pdf)
