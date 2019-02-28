#!/usr/bin/env Rscript
# This script can be run using:
# ./plot_fig_6_latency.R <data>

# use the ggplot2 library
library(ggplot2)

# read in data
args <- commandArgs(trailingOnly=TRUE)
data <- read.csv(args[1], sep=" ")

data$config_label <- ifelse(data$config_name == "dpdk_only", "DPDK",
		  ifelse(data$config_name == "iok_runtime", "IOKernel + runtime",
		  ifelse(data$config_name == "wakeups_steering", "+ wakeup",
		  "+ preemption")))
data$system <- ifelse(data$runtime == "yes", "Shenango", "DPDK")
data$system <- factor(data$system, levels = c("Shenango", "DPDK"))

theme_set(theme_bw(base_size=14))

head(data)

#colors=c("#fef0d9", "#fdcc8a", "#fc8d59", "#d7301f")
colors=c("#999999", "#1b7837", "#7fbf7b", "#d9f0d3")
ggplot(data, aes(x=system, y=latency_us, fill=reorder(config_label, latency_us))) +
	     geom_bar(stat="identity", position="identity") +
	     coord_flip() +
	     scale_fill_manual(name="", values=colors) +
	     labs(x="", y="Round trip time (μs)")

ggsave("fig_6_latency.pdf", width=6, height=1.8, device = cairo_pdf)
