#!/usr/bin/env Rscript
# This script can be run using:
# ./plot_fig_7_connections.R <conns_24> <all_1200>

# use the ggplot2 library
library(ggplot2)
library(cowplot)
library(plyr)

# read in data
args <- commandArgs(trailingOnly=TRUE)
conns_24 <- read.csv(args[1])
all_1200 <- read.csv(args[2]) # all synthetic data (1200 connections)

theme_set(theme_bw(base_size=11))

all_1200 <- all_1200[(all_1200$system == "shenango" | all_1200$system == "zygos") &
	 (all_1200$background == "swaptions" | all_1200$system == "zygos") &
	 all_1200$spin == "False",]

all <- rbind.fill(conns_24, all_1200)

all$label <- ifelse(all$system == "shenango" & all$nconns == 24, "Shenango, 24",
	  ifelse(all$system == "shenango", "Shenango, 1200",
	  ifelse(all$system == "zygos" & all$nconns == 24, "ZygOS, 24",
	  ifelse(all$system == "zygos", "ZygOS, 1200", "???"))))
all$label <- factor(all$label, c("ZygOS, 24", "ZygOS, 1200", "Shenango, 24", "Shenango, 1200"), ordered=TRUE)

all$hex_color <- ifelse(all$system == "shenango" & all$nconns == 24, "#66d35f",
	  ifelse(all$system == "shenango", "#33a02c",
	  ifelse(all$system == "zygos" & all$nconns == 24, "#6ab1eb",
	  ifelse(all$system == "zygos", "#1f78b4", "???"))))

all$linetype <- ifelse(all$system == "shenango" & all$nconns == 24, "22",
	  ifelse(all$system == "shenango", "solid",
	  ifelse(all$system == "zygos" & all$nconns == 24, "11",
	  ifelse(all$system == "zygos", "a2", "???"))))


# only retain data points with finite 99.9% latency
all <- all[all$p999 != "Inf",]

# clean up distribution names
all$distribution <- as.character(all$distribution)
all$distribution <- ifelse(all$distribution == "bimodal1", "bimodal", all$distribution)
all$distribution <- factor(all$distribution, levels=c("constant", "exponential", "bimodal"), ordered=TRUE)

tail(all)


x_max = 1.3
x_breaks = c(0, 0.4, 0.8, 1.2)



# only keep exponential distribution, not cycle counted
exp <- all[all$distribution == "exponential",]

y_axis_label = "99.9% Latency (μs)"
l_colors <- exp$hex_color
names(l_colors) <- exp$label
l_linetypes <- exp$linetype
names(l_linetypes) <- exp$label
ggplot(exp, aes(x=achieved/(1000*1000), y=p999, color=label, linetype=label)) +
	    geom_line() +
	    coord_cartesian(ylim=c(0, 300)) +
	    scale_x_continuous(lim=c(0, x_max), breaks=x_breaks) +
	    labs(y=y_axis_label, x="Spin Server Offered Load (million requests/s)") +
	    theme(legend.position="top", legend.title = element_blank(),
	    				 axis.title.y=element_text(hjust=1),
	    legend.margin=margin(c(-8, 0, -8, -40)), legend.text=element_text(size=9)) +
	    scale_linetype_manual(values=l_linetypes) +
	    scale_color_manual(values=l_colors)

ggsave("fig_7_connections.pdf", width=4.5, height=1.8, device = cairo_pdf)
